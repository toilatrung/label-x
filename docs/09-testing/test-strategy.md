---
id: labelx-test-strategy
title: Chiến lược kiểm thử toàn bộ giai đoạn LabelX
type: reference
domain: testing
module: repository
tags: [testing, ci, phases, acceptance]
priority: 2
---

# Chiến lược kiểm thử LabelX

## Phạm vi và nguồn chuẩn

Đầu ra theo yêu cầu người dùng: thiết kế CI/CD và kiểm thử mọi giai đoạn. Stack giữ [DEC-001](../../.agent/governance/decisions/DEC-001.md); quyết định nghiệp vụ giữ [architecture_review.html](../00-project/sources/architecture_review.html). [Roadmap T](../00-project/sources/QC_Engine_Review_Report.html#roadmap) A–F và [roadmap A](../00-project/sources/Quality_Control_Review_UX_Architecture.html#roadmap) P0–P6 chỉ được dùng ánh xạ giai đoạn kiểm thử, không tự tạo milestone/epic hoặc deadline.

SRS LaTeX M13 v1.0 là **bản đề xuất để duyệt** (00-frontmatter.tex). Test FR/AC/NFR trong ma trận là traceability tới bản đề xuất, không tự chốt TBD hay mở rộng scope. M13 có Ranking/Evaluation và chỉ hiển thị gate, không phát hành Dataset đầy đủ (FR-GTE-04). Hồ sơ intake Markdown của kit vẫn trống; không đổi trạng thái intake hoặc roadmap trong tác vụ này.

## Tình trạng hiện tại

Scaffold có Django/DRF, Celery, Next.js; chưa có adapter/engine/review/ranking nghiệp vụ. Chỉ SCF-01 đang bind test smoke OpenAPI có sẵn. Frontend chưa chọn test runner theo DEC-001; lint/typecheck/build không được báo thành UI test hay end-to-end test đã đạt.

Ma trận máy đọc: [test-matrix.json](test-matrix.json), 12 nhóm giai đoạn, 62 ca kiểm. Mỗi ca có yêu cầu nguồn, fixture, expected result và trạng thái implemented/planned. Ca planned không được skip thành pass. Test runner giai đoạn trả BLOCKED khi thiếu binding, fixture/reference/policy hoặc dependency evidence.

## Các tầng kiểm thử

1. Unit: tính toán thuần, biên rule/geometry/matching, canonical hash, counting/ranking/KPI.
2. Contract: adapter allowlist theo CVAT version, OpenAPI/frontend type, payload/status/version/provenance. Export POST chỉ được phép nếu contract đã xác minh là thao tác đọc; không blanket chặn mọi POST.
3. Integration: PostgreSQL thật, Celery worker và Redis thật khi kiểm async, Object Storage namespace tạm; atomicity/idempotency/audit/lease.
4. End-to-end: trình duyệt → queue/workspace → quyết định → CVAT giả lập revision → verify → final run/report. Driver frontend cần chọn trong task riêng; test direct API không thay browser test.
5. Evaluation: reference/held-out/model/score/policy đã khoá; accuracy engine riêng reviewer agreement. Không gọi model confidence là Ground Truth.
6. Fault/load/recovery: worker chết, storage/Redis lỗi, race lease, backup/restore và migration. Chỉ chạy namespace staging chuyên dụng; không thử phá dữ liệu thật từ pull request.

## Dữ liệu kiểm thử

Pull request dùng synthetic image/annotation, mock CVAT và Detector stub; không cần token thật, không gửi ảnh ra ngoài, không dùng held-out để chỉnh test cho dễ pass. Integration dùng PostgreSQL thay SQLite cho lock/constraint; eager Celery chỉ dùng unit, không chứng minh broker/worker hoạt động.

Live CVAT/model/reference chạy thủ công trên main ở runner riêng, có environment approval và dữ liệu read-only. Không publish ảnh/annotation/secret lên GitHub artifacts; chỉ metadata không nhạy cảm, checksum và report đã loại dữ liệu riêng. Fixture store sống ở hệ thống nội bộ.

## Điều kiện chuyển giai đoạn

Tất cả ca bắt buộc của nhóm phải được bind test executable và passed; không zero-test/all-skipped. Evidence cùng commit và có dependency phase passed. Reference có version, scope và provenance; policy số học không null/TBD và có quyết định phê duyệt trước benchmark. Ngưỡng Coverage/residual/agreement đã chốt chỉ là cấu hình pilot của ứng dụng, không thay kết quả nghiệm thu engine.

AC-08 phụ thuộc TBD-K1/K4; AC-09 phụ thuộc TBD-K2/K3/TBD-12. Chưa chốt thì ghi BLOCKED/insufficient data, không tự đặt recall, effort gain, latency hoặc coverage code tối thiểu. NFR latency đề xuất không tự thành SLA.

## Trách nhiệm và tách nhiệm vụ

Implementer viết test và cung cấp evidence; reviewer độc lập kiểm contract/oracle; Quality Assurance Lead quản lý reference/held-out/policy; Quality Control Admin vận hành runner; người đủ quyền khác requester duyệt CD/waiver/release. Không tự đánh dấu accepted QA hoặc task done từ một job CI.

## Ma trận truy vết

R-01: SNP/AGG/RNK; R-02: ENG/MAT/REV; R-03: RWK/REL; R-04: REF/MET/KPI/RPT; R-05: SNP/SEC/AUD; R-06: AGG/RNK/GTE; R-07: EFF/KPI. Từng ca chi tiết nằm trong JSON và [bản HTML](../../ci_cd_testing.html).

## Lệnh kiểm tra

```bash
node --test scripts/ci/tests/*.test.cjs
node scripts/ci/quality-gate.cjs validate-plan
node scripts/ci/render-plan.cjs --check
node scripts/ci/quality-gate.cjs run --phase scaffold
```

Lệnh run cần uv/Python và PostgreSQL cho pytest. Giai đoạn chưa có code/test trả nonzero BLOCKED là kết quả đúng, không phải đã có lỗi nghiệp vụ. Hướng dẫn workflow tại [CI/CD](../08-devops/ci-cd.md).
