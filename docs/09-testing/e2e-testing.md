---
id: labelx-e2e-testing
title: End-to-end và pilot LabelX
type: reference
domain: testing
module: repository
tags: [e2e, browser, pilot, held-out]
priority: 2
---

# End-to-end và pilot

Đường kiểm: login đúng role/scope → snapshot → run → evidence/queue → claim → decision → sửa CVAT bằng deep link → revision mới → re-check → reviewer verify → final snapshot/run → report/gate. Trình duyệt thật phải kiểm context/mode/overlay/form lỗi/deep link; driver chưa chọn không được ghi E2E passed.

Reference/held-out: người lập chuẩn không nhìn ranking; split theo video; không giao train/calibration/guideline cases; policy và counting version khoá trước đo. KPI-1 kiểm Recall@20% đếm lỗi; KPI-2/KPI-2b gồm effort xử lý false alarm và re-check, kiểm residual/non-inferiority. Thiếu reference/threshold thì chưa nghiệm thu.

RAG, temporal, specialized classifier và full Dataset release là suite sau MVP/scope approval. VLM trong pilot M13 còn TBD-08: không tự bật/tắt từ kế hoạch test. Khi bật, kiểm cap 400 candidate/3 lần thử và abstain/timeout/coordinate validation.

Nguồn: [SRS evaluation](../label-x_system-requirement-specification/sections/07-evaluation.tex), [ma trận](test-matrix.json), [architecture review](../00-project/sources/architecture_review.html).
