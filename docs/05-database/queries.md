---
id: database-queries
title: Truy vấn quan trọng
type: reference
domain: database
module: quality-control
tags: [database, queries, lease, ranking, coverage]
priority: 2
---
# Truy vấn quan trọng

Tên bảng và cột theo [schema.md](schema.md). Tham số được đánh dấu `:ten`. Trong mã, các truy vấn này viết bằng Django ORM (`select_for_update(skip_locked=True)`, `bulk_create(ignore_conflicts=True)`…) hoặc `RawSQL` khi ORM không diễn đạt được.

## Q1 — Cấp lease frame kế tiếp (`POST /api/queues/{name}/next`)

Yêu cầu:

- Không có hai reviewer giữ cùng một **frame** trong một run, kể cả khi frame có mặt ở cả hai queue `risk` và `random` (FR-REV-03, NFR-15). Lease được khoá theo `(run_id, frame_id)`, không theo `review_item`.
- Bỏ qua frame mà reviewer là assignee tại snapshot (FR-REV-03).
- Thiếu identity mapping thì từ chối (fail closed), không ngầm cho qua (FR-SEC-02, 03).
- Mỗi reviewer chỉ giữ một lease (RK-05).
- PostgreSQL là nguồn chuẩn của lease (SRS `tab:modules`).

```sql
BEGIN;
-- 0a. Fail closed: reviewer phải có identity mapping
SELECT 1 FROM identity_mapping WHERE user_id = :reviewer_id;
--     không có dòng → ROLLBACK, 403 IDENTITY_MAPPING_MISSING (lỗi cấu hình, báo QC Admin)

-- 0b. Đã có lease còn hạn thì trả lại chính lease đó (idempotent)
SELECT l.* FROM review_lease l
 WHERE l.holder_user_id = :reviewer_id AND l.status = 'active' AND l.expires_at > now();

-- 1. Chọn và khoá một review_item
SELECT ri.id, ri.frame_id
  FROM review_item ri
  JOIN frame f         ON f.id = ri.frame_id
  JOIN snapshot_job sj ON sj.snapshot_id = f.snapshot_id AND sj.cvat_job_id = f.cvat_job_id
 WHERE ri.run_id = :run_id
   AND ri.queue  = :queue                                   -- 'risk' | 'random'
   AND ri.state IN ('unreviewed', 'in_review')
   -- chặn self-review; job có assignee CVAT nhưng chưa map identity thì KHÔNG cấp (fail closed)
   AND (sj.assignee_cvat_user_id IS NULL
        OR (sj.assignee_user_id IS NOT NULL AND sj.assignee_user_id <> :reviewer_id))
   -- frame chưa có lease còn hạn ở BẤT KỲ queue nào
   AND NOT EXISTS (SELECT 1 FROM review_lease l
                    WHERE l.run_id = ri.run_id AND l.frame_id = ri.frame_id
                      AND l.status = 'active' AND l.expires_at > now())
 ORDER BY ri.rank
 LIMIT 1
 FOR UPDATE OF ri SKIP LOCKED;

-- 2. Thu hồi lease đã hết hạn của frame này (ở mọi queue)
UPDATE review_lease SET status = 'expired'
 WHERE run_id = :run_id AND frame_id = :frame_id AND status = 'active' AND expires_at <= now();

-- 3. Cấp lease theo frame; xung đột thì frame vừa bị reviewer khác lấy qua queue khác
INSERT INTO review_lease (run_id, frame_id, review_item_id, holder_user_id, acquired_at, expires_at, status)
VALUES (:run_id, :frame_id, :item_id, :reviewer_id, now(), now() + :lease_ttl, 'active')   -- :lease_ttl = TBD-09
ON CONFLICT (run_id, frame_id) WHERE status = 'active' DO NOTHING
RETURNING id;
--    không có dòng trả về → lặp lại bước 1 (frame kế tiếp), giới hạn số vòng
UPDATE review_item SET state = 'in_review', lease_id = :new_lease_id WHERE id = :item_id;
INSERT INTO audit_log (...) VALUES (...);                   -- cùng transaction
COMMIT;
```

Ghi chú:

- `SKIP LOCKED` giúp các reviewer đồng thời không phải chờ nhau. Khoá dòng chỉ bảo vệ từng `review_item`; ràng buộc theo frame giữa hai queue do partial unique index `(run_id, frame_id) WHERE status='active'` bảo đảm (bước 3).
- Job không có assignee trên CVAT (`assignee_cvat_user_id` NULL) thì không có căn cứ self-review, và vẫn được cấp. Việc này có chấp nhận được trong pilot hay không **cần QA Lead xác nhận**.
- Kiểm tra fail-closed cũng được lặp lại khi lưu quyết định, phân xử và verify (Q2).

## Q2 — Kiểm lease khi lưu quyết định (FR-REV-14)

```sql
SELECT l.id FROM review_lease l
  JOIN issue i ON i.run_id = l.run_id AND i.frame_id = l.frame_id
 WHERE l.id = :lease_id AND i.id = :issue_id AND l.holder_user_id = :actor_id
   AND l.status = 'active' AND l.expires_at > now()
 FOR UPDATE OF l;
-- không có dòng → 409 LEASE_CONFLICT
-- actor không có identity mapping, hoặc job có assignee CVAT chưa map → 403 IDENTITY_MAPPING_MISSING (fail closed)
-- assignee tại snapshot = actor → 403 SELF_REVIEW_FORBIDDEN
```

## Q3 — Ranking có phân trang (`GET /api/runs/{id}/ranking`)

```sql
SELECT fr.frame_id, fr.rank, fr.score, fr.missing_evidence,
       count(*) FILTER (WHERE i.family = 'E1') AS e1,
       count(*) FILTER (WHERE i.family = 'E2') AS e2,
       count(*) FILTER (WHERE i.family = 'E3') AS e3
  FROM frame_risk fr
  LEFT JOIN issue i ON i.run_id = fr.run_id AND i.frame_id = fr.frame_id
 WHERE fr.run_id = :run_id AND fr.score_version_id = :score_version_id
   AND fr.rank > :cursor_rank                    -- cursor pagination
 GROUP BY fr.frame_id, fr.rank, fr.score, fr.missing_evidence
 ORDER BY fr.rank
 LIMIT 50;
```

Tính và lưu ranking (`ranking.score_run`):

- Tính `s(f) = Σ n_i·q_i + h(f)` cho **mọi** frame (FR-RNK-01).
- Phá hoà tất định (FR-RNK-04):

```sql
SELECT frame_id, row_number() OVER (
         ORDER BY score DESC, sha256(convert_to(frame_key || :seed, 'UTF8'))) AS rank
  FROM tmp_scores;
```

## Q4 — Coverage ledger theo engine (`GET /api/runs/{id}/ledger`, gate)

```sql
SELECT engine,
       count(*) FILTER (WHERE applicability = 'eligible')                        AS eligible,
       count(*) FILTER (WHERE applicability = 'eligible' AND status = 'completed') AS completed,
       count(*) FILTER (WHERE applicability = 'eligible' AND status = 'failed')    AS failed,
       count(*) FILTER (WHERE applicability = 'eligible' AND status = 'not_checked') AS not_checked,
       count(*) FILTER (WHERE applicability = 'not_triggered')                   AS not_triggered,
       round(100.0 * count(*) FILTER (WHERE applicability = 'eligible' AND status = 'completed')
             / NULLIF(count(*) FILTER (WHERE applicability = 'eligible'), 0), 2) AS coverage_pct
  FROM ledger_entry
 WHERE run_id = :run_id
 GROUP BY engine;
```

- Mẫu số giữ cả đơn vị `failed` (B-04; FR-AGG-04). `not_triggered` không nằm trong mẫu số (SRS `tab:enginestates`).
- `coverage_pct` NULL (không có đơn vị eligible) thì hiển thị Not checked, **không** hiển thị 0% hay đạt (FR-RPT-03).
- Gate coverage: mọi engine có `engine_result.required = true` phải ≥ 95% trên run cuối (FR-GTE-01).

Cờ thiếu bằng chứng của frame (FR-RNK-06):

```sql
UPDATE frame_risk fr SET missing_evidence = true
 WHERE fr.run_id = :run_id AND EXISTS (
   SELECT 1 FROM ledger_entry le JOIN engine_result er
          ON er.run_id = le.run_id AND er.engine = le.engine AND er.required
    WHERE le.run_id = fr.run_id AND le.frame_id = fr.frame_id
      AND le.applicability = 'eligible' AND le.status IN ('failed', 'not_checked', 'pending'));
```

## Q5 — Ghi kết quả shard idempotent (FR-AGG-02, 06)

```sql
BEGIN;
SELECT status FROM work_unit WHERE id = :wu FOR UPDATE;        -- 'completed' → COMMIT, kết thúc
INSERT INTO candidate (...) VALUES (...) ON CONFLICT (run_id, fingerprint) DO NOTHING;
INSERT INTO evidence  (...) VALUES (...) ON CONFLICT (candidate_id, type, payload_sha256) DO NOTHING;
INSERT INTO ledger_entry (...) VALUES (...)
  ON CONFLICT (run_id, engine, unit_type, unit_ref) DO UPDATE SET status = EXCLUDED.status, reason = EXCLUDED.reason;
UPDATE work_unit SET status = 'completed', finished_at = now() WHERE id = :wu;
COMMIT;
```

Blob evidence được upload **trước** BEGIN (NFR-06; [object-storage.md](../11-integrations/object-storage.md)).

## Q6 — Gộp issue (FR-AGG-03)

```sql
INSERT INTO issue (run_id, snapshot_id, frame_id, family, anchor, n_i, dedup_key, policy_version, origin, state)
SELECT ... FROM candidate c WHERE c.run_id = :run_id
ON CONFLICT (run_id, dedup_key) DO NOTHING;

INSERT INTO issue_candidate (issue_id, candidate_id)
SELECT i.id, c.id FROM candidate c JOIN issue i ON i.run_id = c.run_id AND i.dedup_key = c.dedup_key
 WHERE c.run_id = :run_id
ON CONFLICT (candidate_id) DO NOTHING;
```

## Q7 — Điều kiện "Đã review xong" (FR-REV-13)

```sql
SELECT count(*) FROM issue i
 WHERE i.run_id = :run_id AND i.frame_id = :frame_id
   AND i.state IN ('pending_review', 'in_review');   -- > 0 → 409
```

## Q8 — Gate: lỗi nghiêm trọng chưa đóng và rework chưa verify (FR-GTE-01)

Gate chỉ tính trên **một** run: run cuối (`is_final`) khi run đó thoả FR-RWK-08 (Completed, coverage engine bắt buộc đạt). Nếu chưa có run như vậy thì dùng run gốc, và báo cáo phải ghi rõ lý do (FR-RPT-06). Không gộp issue từ các snapshot lịch sử khác của dataset.

```sql
WITH g AS (
  SELECT id, coalesce(origin_run_id, id) AS origin_id
    FROM qc_run WHERE id = :gate_run_id            -- run cuối, hoặc run gốc theo FR-RPT-06
)
SELECT
  (SELECT count(*) FROM issue i, g
    WHERE i.run_id = g.id
      AND i.severity = 'critical' AND i.state NOT IN ('closed', 'rejected'))   AS critical_open,
  (SELECT count(*) FROM rework_request rr JOIN issue i ON i.id = rr.issue_id, g
    WHERE i.run_id IN (g.id, g.origin_id)          -- vòng review của đúng scope này
      AND i.state <> 'closed')                                                 AS rework_unverified;
```

Ghi chú:

- `origin_run_id` của run cuối trỏ tới run gốc của cùng scope (`dataset_id`, `scope_hash`). Các run re-check nằm trong `rework_recheck` và không được tính riêng.
- Giá trị `severity` theo lớp và kích thước được định nghĩa ở **TBD-07**. Trong lúc chưa có định nghĩa, điều kiện này là `insufficient_data`, tức chưa đạt (FR-GTE-02).
