---
id: database-schema
title: Schema PostgreSQL LabelX QC
type: reference
domain: database
module: quality-control
tags: [database, postgresql, schema, idempotency, audit]
priority: 1
---
# Schema PostgreSQL

## 1. Nguồn và quy ước

- Schema dựa trên ERD khái niệm của SRS (`fig:erd` trong [03-data-errors.tex](../label-x_system-requirement-specification/sections/03-data-errors.tex)) và A §22 (Domain Data Model). Chỉ lấy phần của A khớp SRS; xem mục 7.
- Bảng được tạo bằng Django model. Tên bảng ở đây là **tên logic** (đề xuất `db_table`). Mỗi bảng thuộc một app trong [system-design.md](../02-architecture/system-design.md) mục 3.
- Khoá chính dùng `BigAutoField` (`DEFAULT_AUTO_FIELD`). Thời gian là `timestamptz`. `jsonb` chỉ dùng cho dữ liệu có cấu trúc thay đổi theo version (features, contributions, payload cấu hình).
- Toạ độ box là `double precision` theo pixel ảnh gốc (`x1, y1, x2, y2`) (SRS §9.4).
- Bản ghi bất biến (candidate, evidence, decision, audit) không có API sửa. Audit còn bị chặn ở mức DB (mục 5).

## 2. Dữ liệu nguồn và snapshot

| Bảng | Cột chính | Khoá và ràng buộc | Yêu cầu |
|---|---|---|---|
| `dataset` | `id`, `cvat_project_id`, `name`, `version_label`, `taxonomy_version`, `guideline_version` | UNIQUE `(cvat_project_id, version_label)` | H "Dataset = CVAT Project + Version" |
| `snapshot` | `id`, `dataset_id`, `parent_snapshot_id` NULL, `scope` jsonb, `status` (`pending`, `exporting`, `locked`, `failed`), `failure_reason`, `revision_hash`, `taxonomy_version`, `guideline_version`, `seed`, `out_of_scope_shapes`, `created_by`, `created_at`, `locked_at`, `purpose` (`review`, `rework_incremental`, `final`) | FK `parent_snapshot_id` → `snapshot`; CHECK `status<>'locked' OR revision_hash IS NOT NULL` | FR-SNP-03…07 |
| `snapshot_job` | `snapshot_id`, `cvat_task_id`, `cvat_job_id`, `job_hash`, `updated_date_first`, `updated_date_verify`, `assignee_cvat_user_id`, `assignee_user_id` NULL, `export_status` | UNIQUE `(snapshot_id, cvat_job_id)` — khoá idempotent của `export_job` | FR-SNP-04, 05; B-12 |
| `frame` | `id`, `snapshot_id`, `cvat_job_id`, `cvat_frame_index`, `frame_key`, `image_key`, `image_sha256`, `width`, `height`, `weather`, `scene`, `timeofday`, `source_video` | UNIQUE `(snapshot_id, frame_key)`; UNIQUE `(snapshot_id, cvat_job_id, cvat_frame_index)` | FR-SNP-05; split theo video (FR-EVL-05) |
| `annotation` | `id`, `frame_id`, `cvat_shape_id`, `label`, `x1`, `y1`, `x2`, `y2`, `attributes` jsonb | UNIQUE `(frame_id, cvat_shape_id)` | ERD Annotation |
| `identity_mapping` | `user_id`, `cvat_user_id`, `cvat_username` | UNIQUE `user_id`; UNIQUE `cvat_user_id` | FR-SEC-02 |
| `role_assignment` | `user_id`, `role` (`annotator`, `reviewer`, `qa_lead`, `qc_admin`, `super_admin`, `product_owner`, `data_owner`; hai vai trò cuối theo SRS ch.6, đoạn dưới `tab:rbac`), `dataset_id` NULL (NULL = toàn hệ thống, chỉ cho SA) | UNIQUE `(user_id, role, dataset_id)` | FR-SEC-01 |

Lineage revision: snapshot đã khoá thì bất biến. Mọi thay đổi annotation tạo dòng `snapshot` mới, có `parent_snapshot_id` (FR-SNP-06). Không có cột "revision" riêng: revision chính là `snapshot.revision_hash` và `snapshot_job.job_hash`.

## 3. Cấu hình, run và ledger

| Bảng | Cột chính | Khoá và ràng buộc | Yêu cầu |
|---|---|---|---|
| `config_version` | `id`, `payload` jsonb (engine bật/tắt, ngưỡng, `τ`, policy gộp), `status` (`draft`, `published`), `published_by`, `published_at` | Trigger hoặc logic service chặn UPDATE khi `published` | FR-ENG-01; A §22 |
| `model_artifact` | `id`, `name`, `version`, `checksum`, `class_mapping_version`, `class_mapping` jsonb, `artifact_key` | UNIQUE `(name, version)`; UNIQUE `checksum` | FR-ENG-05; SRS §9.4 |
| `qc_run` | `id`, `snapshot_id`, `config_version_id`, `model_artifact_id` NULL, `seed`, `engine_versions` jsonb, `status` (`queued`, `running`, `completed`, `partial`, `failed`, `cancelled`), `is_final`, `origin_run_id` NULL, `dataset_id`, `scope_hash` (SHA-256 của scope đã chuẩn hoá), `cancel_requested_at`, `next_step_enqueued_at`, `claimed_at`, `created_by`, `started_at`, `finished_at` | Partial UNIQUE `(dataset_id, scope_hash) WHERE is_final AND status IN ('queued','running')` — một scope chỉ có một run cuối đang chạy | FR-ENG-01; FR-RWK-06 |
| `engine_result` | `run_id`, `engine`, `status` (`running`, `checked`, `partial`, `failed`, `not_checked`), `reason` NULL, `eligible_units`, `completed_units`, `failed_units`, `not_checked_units`, `required` bool | UNIQUE `(run_id, engine)` | FR-AGG-04, 05; B-19 |
| `work_unit` | `id`, `run_id`, `engine`, `shard_key` (job + khoảng frame), `idempotency_key`, `status` (`pending`, `running`, `completed`, `failed`, `cancelled`), `attempt`, `last_error`, `started_at`, `finished_at` | UNIQUE `(run_id, idempotency_key)`; UNIQUE `(run_id, engine, shard_key)` | FR-AGG-02; R-01 |
| `ledger_entry` | `run_id`, `engine`, `unit_type` (`annotation`, `frame`, `pair`, `candidate`, `reference_frame`), `unit_ref`, `frame_id`, `applicability` (`eligible`, `not_applicable`, `not_triggered`), `status` (`completed`, `failed`, `not_checked`, `pending`), `reason`, `work_unit_id` | UNIQUE `(run_id, engine, unit_type, unit_ref)` | FR-AGG-04; B-04 |
| `prediction` | `work_unit_id`, `frame_id`, `x1..y2`, `label`, `confidence`, `model_artifact_id` | UNIQUE `(work_unit_id, frame_id, ordinal)` | NFR-04 (lưu để tái dùng) |

`idempotency_key = sha256(snapshot_id ‖ engine ‖ engine_version ‖ config_version_id ‖ model_checksum ‖ shard_key)`. Khoá này không chứa `run_id`, nên hai run trên cùng input sẽ có khoá trùng nhau. Vì vậy ràng buộc UNIQUE được đặt theo run: `(run_id, idempotency_key)`. Việc tái dùng kết quả giữa các run (cache) **chưa chốt**; R B-10 yêu cầu tách tái dùng khỏi attribution theo run.

## 4. Candidate, issue, ranking, review

| Bảng | Cột chính | Khoá và ràng buộc | Yêu cầu |
|---|---|---|---|
| `candidate` | `id`, `run_id`, `work_unit_id`, `engine`, `family` (`E1`, `E2`, `E3`, `structural`), `frame_id`, `annotation_id` NULL, `pred_x1..y2` NULL, `features` jsonb, `score`, `rule_id`, `dedup_key`, `fingerprint`, `created_at` | UNIQUE `(run_id, fingerprint)`; bất biến | FR-AGG-01; FR-ENG-07 |
| `evidence` | `id`, `candidate_id`, `type`, `payload_key`, `payload_sha256`, `pred_label`, `confidence`, `iou`, `ambiguous` jsonb, `rule_id` | UNIQUE `(candidate_id, type, payload_sha256)`; bất biến | FR-ENG-08; NFR-06 |
| `issue` | `id`, `run_id`, `snapshot_id`, `frame_id`, `family`, `anchor` jsonb, `n_i`, `dedup_key`, `policy_version`, `origin` (`candidate`, `reviewer`), `severity` NULL, `state`, `q_i`, `created_by` NULL | UNIQUE `(run_id, dedup_key)`; CHECK `state` thuộc tập trạng thái SRS | FR-AGG-03; FR-RNK-12; BR-08 |
| `issue_candidate` | `issue_id`, `candidate_id` | UNIQUE `candidate_id` (mỗi candidate thuộc đúng một issue) | ERD Candidate *..1 Issue |
| `score_version` | `id`, `name`, `params` jsonb, `calibration_report` jsonb, `locked_at` | Không sửa sau khi khoá | FR-RNK-02, 10, 11 |
| `frame_risk` | `run_id`, `score_version_id`, `frame_id`, `score`, `h_f`, `rank`, `contributions` jsonb, `missing_evidence` bool | UNIQUE `(run_id, score_version_id, frame_id)`; UNIQUE `(run_id, score_version_id, rank)` | FR-RNK-01…06 |
| `control_ranking` | `run_id`, `kind` (`random`, `count_desc`, `max_conf`), `seed`, `frame_id`, `rank` | UNIQUE `(run_id, kind, seed, frame_id)` | FR-RNK-08 |
| `review_item` | `id`, `run_id`, `frame_id`, `queue` (`risk`, `random`), `rank`, `state` (`unreviewed`, `in_review`, `reviewed`, `pending_issues`, `done`), `lease_id` NULL | UNIQUE `(run_id, queue, frame_id)` | FR-REV-01, 02; SRS `fig:framestate` |
| `review_lease` | `id`, `run_id`, `frame_id`, `review_item_id` (queue đã cấp lease), `holder_user_id`, `acquired_at`, `expires_at`, `status` (`active`, `released`, `expired`) | Partial UNIQUE `(run_id, frame_id) WHERE status='active'`: lease duy nhất **theo frame** trong một run, bất kể frame nằm ở queue `risk` hay `random`. Partial UNIQUE `(holder_user_id) WHERE status='active'`: mỗi reviewer một lease (RK-05) | FR-REV-03, 04; NFR-15 |
| `review_decision` | `id`, `issue_id`, `actor_id`, `lease_id`, `decision`, `family`, `severity`, `reason`, `rule_id`, `guideline_version`, `snapshot_revision`, `is_override`, `override_reason`, `idempotency_key`, `started_at`, `ended_at` | UNIQUE `(actor_id, idempotency_key)`; bất biến (quyết định mới là dòng mới) | FR-REV-08, 10 |
| `adjudication` | `id`, `issue_id`, `actor_id`, `escalated_by_id`, `outcome` (`confirm`, `reject`, `guideline_gap`), `rule_id`, `correct_label`, `reason` | CHECK `actor_id <> escalated_by_id` | FR-ESC-02, 03 |
| `decision_case` | `id`, `adjudication_id`, `rule_id`, `guideline_version`, `version` | UNIQUE `(adjudication_id, version)` | FR-ESC-04 |
| `rework_request` | `id`, `issue_id`, `assignee_user_id`, `instruction`, `severity`, `due_at`, `deep_link`, `base_snapshot_id`, `base_job_hash`, `fixed_snapshot_id` NULL, `status`, `attempt` | UNIQUE `(issue_id, attempt)` | FR-RWK-01…03 |
| `verification` | `id`, `rework_id`, `verifier_id`, `recheck_run_id`, `outcome` (`pass`, `fail`), `reason` | CHECK verifier khác annotator (kiểm ở service, vì cần join `rework_request.assignee_user_id`) | FR-RWK-05 |
| `rework_recheck` | `id`, `rework_id`, `snapshot_id` (snapshot gia tăng sau "Đã sửa"), `run_id` (run re-check), `status` | UNIQUE `(rework_id, snapshot_id)` — khoá idempotent của task `review.recheck_rework` | FR-RWK-03, 04 |
| `final_run_link` | `final_run_id`, `verification_id` | UNIQUE `(final_run_id, verification_id)` | FR-RWK-06 |

## 5. Guideline, đánh giá, gate, audit

| Bảng | Cột chính | Khoá và ràng buộc | Yêu cầu |
|---|---|---|---|
| `guideline_version` | `id`, `version`, `approved_at`, `source_ref` | UNIQUE `version` | FR-GDL-01 |
| `guideline_rule` | `guideline_version_id`, `rule_id`, `section`, `excerpt` | UNIQUE `(guideline_version_id, rule_id)` | FR-GDL-01 |
| `rule_mapping` | `mapping_version`, `family`, `label`, `label_pair`, `rule_id` | UNIQUE `(mapping_version, family, label, label_pair)` | FR-GDL-02 |
| `guideline_gap` | `id`, `rule_id`, `description`, `status`, `resolved_in_version` | — | FR-ESC-05 |
| `reference` | `id`, `snapshot_id`, `version`, `status` (`draft`, `locked`), `tau_m`, `a_min`, `matching_algo_version`, `locked_by`, `locked_at`, `split` (`calibration`, `held_out`) | UNIQUE `(snapshot_id, version)` | FR-EVL-04; BR-13 |
| `gt_object` | `reference_id`, `slot` (1, 2, `merged`), `frame_id`, `x1..y2`, `label`, `ignored`, `annotator_id` | — | FR-EVL-01; BR-11 |
| `ref_error` | `reference_id`, `family`, `gt_object_id` NULL, `annotation_id` NULL, `mapping_version` | CHECK đúng một trong hai FK khác NULL theo family (BR-01) | FR-EVL-03 |
| `evaluation_run` | `id`, `kind` (`kpi1`, `kpi2`, `metric`), `run_id`, `reference_id`, `score_version_id`, `experiment_id`, `params` jsonb, `leakage_check` jsonb, `results` jsonb, `status`, `created_by` | — | FR-EVL-05, 14; B-05 |
| `experiment` | `id`, `design` jsonb, `delta`, `stop_rule`, `locked_at` | — | FR-EVL-11 |
| `effort_event` | `id`, `actor_id`, `arm`, `frame_id`, `activity`, `active_ms`, `client_event_id`, `occurred_at` | UNIQUE `(actor_id, client_event_id)` | FR-EVL-06 |
| `gate_check` | `id`, `run_id`, `condition` (`coverage`, `critical_open`, `rework_verified`, `residual`, `reviewer_agreement`), `status` (`passed`, `failed`, `insufficient_data`, `waived`), `value`, `threshold`, `sample_size`, `evaluated_at` | UNIQUE `(run_id, condition, evaluated_at)` | FR-GTE-01, 02 |
| `waiver` | `id`, `gate_check_id`, `requested_by`, `approved_by` NULL, `reason`, `evidence_key`, `expires_at`, `status` (`requested`, `approved`, `rejected`, `expired`) | CHECK `approved_by IS NULL OR approved_by <> requested_by`; NOT NULL `reason`, `evidence_key`, `expires_at` | FR-GTE-03; B-11 |
| `report_export` | `id`, `run_id`, `format`, `object_key`, `sha256`, `versions` jsonb | UNIQUE `sha256` | FR-RPT-05 |
| `idempotency_record` | `user_id`, `key`, `method`, `path`, `request_hash`, `status_code`, `response_body`, `created_at` | UNIQUE `(user_id, key)` | [rest-api.md](../04-api/rest-api.md) mục 3 |
| `audit_log` | `id` bigserial, `at`, `actor_id`, `actor_role`, `action`, `object_type`, `object_id`, `before` jsonb, `after` jsonb, `revision`, `reason`, `is_override`, `request_id` | **Append-only** | FR-SEC-05; NFR-08 |

### Append-only cho `audit_log`

- Ứng dụng chỉ có thao tác INSERT. Không có model method hay API nào để sửa hoặc xoá (A ADR-06; NFR-08).
- Mức DB:
  - `REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM labelx_app`.
  - Thêm trigger `BEFORE UPDATE OR DELETE … RAISE EXCEPTION`.
  - Hai lệnh trên được tạo bằng migration `RunSQL` (xem [migrations.md](migrations.md)).
- Audit được ghi trong cùng transaction với thao tác. Settings đặt `ATOMIC_REQUESTS=True`; service gọi `audit.record()` trước khi kết thúc view.
- Nối hash chain (A ADR-06 gợi ý) **chưa chốt**.
- Thời hạn lưu: **TBD-15**. Không có job xoá audit.

## 6. Index chính

| Index | Mục đích |
|---|---|
| `review_item (run_id, queue, state, rank)` | Cấp lease theo thứ tự rank ([queries.md](queries.md) Q1) |
| `review_lease (status, expires_at)` | Dọn lease hết hạn |
| `review_lease (run_id, frame_id) WHERE status='active'` | Kiểm frame đã có lease ở queue khác (Q1) |
| `ledger_entry (run_id, engine, applicability, status)` | Tính coverage (Q4) |
| `frame_risk (run_id, score_version_id, rank)` | Phân trang ranking (Q3) |
| `candidate (run_id, dedup_key)` | Gộp issue |
| `issue (run_id, frame_id, state)` | Kiểm FR-REV-13, gate critical |
| `audit_log (object_type, object_id, at)`, `audit_log (actor_id, at)` | FR-SEC-07 |

## 7. Khác biệt so với A §22

| A | Schema này | Lý do |
|---|---|---|
| `DatasetVersion`, `SampleManifest`, `FrameAuditRecord` | Dùng `dataset.version_label`, `review_item(queue='random')` và `effort_event` | SRS ERD không có các bảng riêng này |
| `IssueLease` theo issue | `review_lease` theo frame trong run | FR-REV-03 |
| `Issue.version` (If-Match) | Không có | Không áp dụng If-Match ([rest-api.md](../04-api/rest-api.md) mục 3) |
| `Release`, `ReleaseManifest`, `QualityReport`–`GateEvaluation` | Chỉ có `gate_check`, `waiver`, `report_export` | FR-GTE-04 |
| pgvector guideline index | Không có | B-13; FR-GDL-04 |
| Trạng thái Known Defect, Superseded | Không có | SRS `tab:transitions` |
