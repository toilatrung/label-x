---
id: labelx-unit-testing
title: Unit testing LabelX
type: reference
domain: testing
module: repository
tags: [unit, fixtures, reproducibility]
priority: 2
---

# Unit testing

Test phép tính thuần không gọi CVAT/GPU thật. Ưu tiên oracle độc lập: chuẩn hoá hash, geometry biên, matching cardinality trước IoU, dedup, counting E1/E2/E3, tie theo seed, ceil(kN), zero denominator và waiver clock. Không viết test chỉ lặp lại code implementation.

Fixture cố định, version hoá; thêm property/metamorphic checks cho reorder không đổi hash, retry không đổi số issue, geometry/class đổi có đổi hash. Dùng pytest đã có. Không thêm framework frontend khi chưa có quyết định; ghi ca browser là planned.

Nguồn: [ma trận](test-matrix.json), [SRS functional](../label-x_system-requirement-specification/sections/06-functional.tex), [SRS evaluation](../label-x_system-requirement-specification/sections/07-evaluation.tex). Test thống kê không tự đặt threshold mới.
