# Kế hoạch ổn định engines và tiến độ có chuyển động

Ngày: 2026-10-15. Trạng thái: đã triển khai trong worktree riêng; xem [hành vi và hướng dẫn rollout](../07-development/engine-resilience.md).

- Repo gốc: `/mnt/h/label-x`; base local `develop` tại `fdd195a`.
- Worktree: `/tmp/labelx-engine-resilience-loading`.
- Branch: `plan/engine-resilience-loading`.
- Bản sửa cookie nằm ở checkout/branch riêng; kế hoạch này không tự gộp bản sửa đó.
- Kế hoạch đã được thực hiện theo yêu cầu tiếp theo của người dùng. Bản sửa nằm trong worktree riêng; chưa rollout runtime hay retry run đang có.

## 1. Mục tiêu và bằng chứng

Run 11 cho thấy GPU `/health` trả 200 nhưng `/infer` xen kẽ 503/200. Sau các lượt retry, detector đã hoàn tất 588/588 frame. VLM qua ShopAIKey có 503 xen kẽ 200; một candidate hết 3 lần thử, fail-fast đánh dấu lỗi toàn bộ phần còn lại. Kết quả lúc kiểm tra: 6/163 candidate hoàn tất, 157 lỗi, tổng 11 lần gọi provider.

Giới hạn chẩn đoán: log server chưa lưu mã lỗi body GPU. Worker có hai nhánh 503 (`worker_busy`, `inference_unavailable`), nên chưa thể kết luận tất cả 503 là bận hay hết VRAM. Các lượt retry detector trong log chưa đủ để kết luận là tự động: code hiện tại trong `dispatch.py` bỏ qua retry khi `ORCHESTRATION_FAIL_FAST` bật, còn run có đường retry do người dùng yêu cầu.

Mục tiêu triển khai:

1. Điều phối phù hợp sức chứa GPU, lỗi tạm thời được chờ/retry có giới hạn.
2. Một candidate VLM lỗi không làm mất kết quả hợp lệ hay đánh dấu sai các candidate chưa gọi.
3. Run luôn có đường kết thúc rõ ràng; không retry vô hạn hoặc treo ở running.
4. Các thanh loading của thao tác đang chạy có chuyển động và thông tin cập nhật thật; trạng thái lỗi/chờ không bị che bằng animation.

## 2. Nguyên tắc thiết kế

- Giữ kết quả đã commit, unique key, idempotency, lease và fencing hiện có.
- Chỉ chủ lease hợp lệ được ghi kết quả; cancel hoặc hết deadline vẫn chặn kết quả trễ.
- Lỗi của candidate khác không được vô hiệu hóa kết quả đang chạy còn hợp lệ.
- Đếm riêng thành công, thất bại thực, chưa xử lý, chờ retry và huỷ; chờ không được coi là đạt.
- Số lần gửi provider và ngân sách phải bền vững trong DB, kể cả worker chết hoặc message giao lại.
- Không tự chuyển endpoint/model/provider: mỗi run tiếp tục dùng cấu hình đã ghim.
- Không log secret, header Authorization, ảnh/crop, prompt hoặc URL có chữ ký.

## 3. Các gói công việc theo thứ tự triển khai

### P1 — Chuẩn hoá lỗi và hợp đồng trạng thái

File chính: `runs/gpu_worker.py`, `engines/worker_adapter/client.py`, `vlm/client.py`, `vlm/runner.py`, `orchestration/models.py`, `runs/serializers.py`, `docs/04-api/openapi.yaml`.

- Giữ mã lỗi GPU đã kiểm tra qua allowlist: busy, inference unavailable, auth, timeout, transport, invalid response; giữ HTTP status và khả năng retry.
- VLM phân biệt 429/503/timeout, credential/quota và lỗi parse. Không retry mù lỗi cấu hình, auth hay payload cố định.
- Log có run ID, engine, unit/shard ID, attempt, thời lượng, mã lỗi an toàn và lịch retry.
- Xác định schema lưu trạng thái vận hành: phase, last activity, next retry, deadline, attempts thực, error code và các counters. Dùng migration bổ sung nếu cần; không ghi lại evidence cũ.
- API bổ sung trường tương thích ngược; frontend cũ vẫn đọc được. Phân biệt thời điểm client lấy dữ liệu thành công với thời điểm engine thực sự hoạt động.
- Phần chưa xử lý sau khi dừng vì provider phải có lý do riêng, không gắn `provider_error` như đã gọi và thất bại.

Nghiệm thu: tái hiện 503 busy và 503 inference trả hai mã riêng; lỗi VLM có provenance; dữ liệu run cũ vẫn đọc được và không chứa secret.

### P2 — Hàng đợi và retry Detector theo GPU Worker

File chính: `orchestration/dispatch.py`, `orchestration/fail_fast.py`, `runs/gpu_worker.py`, `engines/detector.py`, `src/detector_worker/labelx_detector/service.py`.

- Giới hạn mặc định một inference đang chạy trên mỗi endpoint GPU vật lý; nhiều revision cấu hình cùng trỏ một endpoint phải dùng chung giới hạn.
- Cơ chế giữ lượt phải chia sẻ giữa các process/worker/run, có token sở hữu, thời hạn và phục hồi khi worker chết. Không dùng lock trong RAM của một process để điều phối toàn hệ thống.
- Shard chưa có lượt vẫn ở trạng thái chờ tài nguyên; không giữ transaction DB hoặc Celery process ngủ lâu để chờ.
- Worker vẫn bảo vệ GPU bằng lock cuối cùng. `worker_busy` là áp lực hàng đợi, không lập tức làm cả engine thất bại.
- Retry các lỗi tạm thời bằng lịch có backoff/jitter, tôn trọng `Retry-After` hợp lệ và giới hạn deadline. Số lần bận/chờ tách khỏi số inference thực và cũng phải có giới hạn chờ.
- Sửa nhánh fail-fast để không bỏ qua cơ chế phục hồi lỗi tạm thời. Lỗi cố định hoặc hết giới hạn mới được chốt; giữ kết quả các shard thành công.
- Thời hạn giữ lượt phải phù hợp timeout inference. Nếu không chứng minh được request trước đã kết thúc thì không tự mở thêm inference; timeout client không có nghĩa worker đã dừng.

Nghiệm thu: hai shard/hai run cùng endpoint không tranh GPU; worker chết không giữ chỗ vĩnh viễn; 503 tạm thời phục hồi mà không cần bấm retry thủ công; không commit trùng.

### P3 — Phục hồi VLM theo candidate và provider

File chính: `vlm/runner.py`, `orchestration/vlm_stage.py`, `orchestration/fail_fast.py`, `orchestration/runsync.py`, `runs/vlm_read.py`.

- Bỏ việc một candidate thất bại kéo toàn bộ pending/running VLM sang failed.
- Giữ retry có giới hạn theo candidate, dùng lịch bền vững thay cho giữ worker ngủ lâu. Bảo toàn max attempts và budget của cấu hình đã publish.
- Giới hạn số request đồng thời theo connection/provider dùng chung giữa nhiều run; ban đầu chạy thận trọng một request đồng thời, điều chỉnh sau smoke có số liệu.
- Khi provider lỗi tạm thời liên tiếp, tạm ngưng gửi và chỉ cho một request thăm dò sau thời gian chờ. Phục hồi thì tiếp tục hàng đợi; hết deadline thì kết thúc partial với phần chưa xử lý được ghi đúng lý do.
- Có deadline tổng cho stage và thời gian chờ tối đa, độc lập với budget; scheduler phục hồi được lịch chờ sau restart.
- 401/403 hoặc cấu hình sai dừng gửi và báo nguyên nhân để vận hành sửa. Lỗi parse/crop chỉ tác động candidate tương ứng.
- Request đang bay trả 200 được ghi nếu lease còn hợp lệ; vẫn tôn trọng cancel/deadline và revision đã ghim.
- Manual retry chỉ xử lý phần được chọn; không chạy lại candidate đã hoàn tất, không tự kích hoạt engine khác.

Nghiệm thu: chuỗi 200 → 503 → 200 giữ đủ kết quả hợp lệ; một candidate hết retry không đổi toàn bộ hàng đợi thành lỗi; provider hỏng kéo dài kết thúc partial đúng hạn; budget không tăng trùng.

### P4 — Tiến độ thật và loading có chuyển động

File chính: `components/execution/AnalysisProgress.tsx`, `styles/labelx.css`, `lib/execution/api.ts`, các màn Analysis và các điểm dùng `.lx-progress`/`role=progressbar`.

- Lập danh sách mọi thanh tiến độ và trạng thái loading đang dùng. Ưu tiên thanh tổng Analysis, từng engine và thao tác dài; áp dụng cùng component/quy tắc cho các thanh loading còn lại.
- Tách loading của thao tác khỏi thanh số liệu tĩnh. Ví dụ benchmark coverage đã hoàn tất là số liệu, không chạy animation vô hạn.
- Có tổng và số lượng thực: giữ phần trăm thực, thêm vệt sáng/sọc chuyển động trên phần đã xử lý; phần trăm không tự tăng bằng timer.
- Chưa biết tổng hoặc đang chuẩn bị: thanh indeterminate di chuyển trên track, không hiển thị phần trăm giả. Trạng thái chạy ở 0% vẫn có dấu hiệu hoạt động rõ.
- Chờ GPU/retry/provider: hiệu ứng nhẹ cùng câu giải thích cụ thể và thời điểm thử lại nếu backend cung cấp. Không dùng cùng câu “đang chạy” cho mọi trạng thái.
- Hiển thị số đã xử lý/tổng, số lỗi thực, số chưa xử lý, thời điểm tiến triển gần nhất và trạng thái kết nối lấy tiến độ.
- Poll thành công không đồng nghĩa engine còn sống. Dùng phase/deadline/hoạt động backend để nhận biết chờ hợp lệ; nếu quá hạn hoặc dữ liệu cũ thì báo rõ thay vì chỉ tiếp tục animation.
- Khi poll lỗi: giữ số liệu cuối cùng, ghi “chưa cập nhật được” và giảm/dừng chuyển động biểu thị hoạt động. Có thao tác lấy lại trạng thái; không tự tạo run mới.
- Completed/partial/failed/cancelled: dừng animation; 100% chỉ biểu thị quá trình đã kết thúc, luôn kèm nhãn kết quả một phần/lỗi khi cần.
- Hỗ trợ `prefers-reduced-motion`, `aria-valuenow` chỉ khi xác định được tiến độ, `aria-valuetext`, thông báo `aria-live` có tiết chế. Tránh thông báo đếm ngược mỗi giây cho screen reader.
- Animation CSS ưu tiên transform/opacity; tránh timer React cho chuyển động và tránh ảnh hưởng pan/zoom/review workspace.
- Đọc hướng dẫn Next.js cục bộ theo `src/frontend/AGENTS.md` trước khi viết frontend.

Nghiệm thu: người dùng nhận biết đang chạy, chờ tài nguyên, chờ retry, mất cập nhật và đã kết thúc. Reduced-motion vẫn truyền đủ thông tin; không có phần trăm giả hoặc animation chạy mãi trên kết quả cuối.

## 4. Kiểm thử bắt buộc

| Nhóm | Kịch bản | Kết quả cần đạt |
| --- | --- | --- |
| GPU | Hai run gửi tới cùng GPU; busy rồi 200 | Có xếp hàng, không fail cả engine, không inference trùng |
| GPU | Auth sai, inference lỗi, network timeout | Mã lỗi riêng, retry đúng loại, giới hạn rõ |
| Recovery | Worker chết, message trùng, lease hết hạn | Khôi phục chờ đúng, không ghi trùng hoặc ghi bằng owner cũ |
| VLM | 503 xen kẽ 200; một candidate hết lượt | Kết quả thành công được giữ, phần chưa gọi không thành lỗi giả |
| VLM | Provider hỏng lâu, quota/auth sai | Ngừng gửi thích hợp và chốt partial đúng hạn |
| VLM | Cancel hoặc fail một candidate khi request khác đang bay | Tôn trọng cancel; lỗi candidate khác không làm mất kết quả hợp lệ |
| API | Run cũ, retry một engine, budget và counters | Tương thích ngược; không tăng đếm trùng |
| UI | 0%, chưa biết tổng, running, chờ retry, mất poll, terminal | Animation và nhãn đúng trạng thái, số liệu không giả |
| UI | Reduced-motion, bàn phím, screen reader | Thông tin truy cập được, không gây thông báo liên tục |

Backend chạy PostgreSQL test DB riêng vì migration dự án dùng PostgreSQL; không dùng SQLite để kết luận suite đạt. Dùng fake provider/worker để kiểm chứng race, deadline và lỗi có kiểm soát trước khi gọi model thật. Không tạo thêm Celery consumer/beat trỏ broker đang test: test runtime phải có queue/broker riêng.

Smoke thật sau unit/integration tests: một batch nhỏ Detector và một candidate VLM bằng cấu hình đã chọn; sau đó tăng tải có giới hạn. Việc chuyển provider hoặc chạy lại toàn bộ dataset là bước riêng. Ghi lại HTTP status, latency, attempts, số kết quả và budget thực.

## 5. Chia PR và bàn giao

1. PR hợp đồng trạng thái và chẩn đoán lỗi (P1); migration bổ sung, giữ tương thích.
2. PR điều phối/retry Detector (P2), có test concurrency và phục hồi lease.
3. PR phục hồi VLM (P3), có test budget, fail-fast, cancel và kết quả đang bay.
4. PR progress/loading (P4), theo API P1; có thể triển khai cùng thời gian P2/P3 sau khi thống nhất hợp đồng.
5. Kiểm thử tích hợp và smoke; ghi hướng dẫn cấu hình, log đối soát, rollout/rollback.

Mỗi PR phải qua kiểm thử liên quan rồi mới mở rộng chạy suite theo CI. Trước triển khai runtime, xác nhận revision thực của API/Celery/GPU Worker: instance cookie test trước đó đã dùng worker từ checkout chính qua broker chung, nên không xem đó là môi trường engines tách biệt.

Rollout: kiểm tra migration và cấu hình; áp dụng điều phối mới cho run mới trước; không sửa kết quả run cũ tự động. Nếu cần thay GPU Worker thì triển khai riêng, kiểm tra model/hash/device và tương thích client. Rollback không xoá dữ liệu/evidence hoặc rollback migration phá dữ liệu; các run đang giữ lease cần được drain/settle trước khi thay scheduler.

Hoàn thành khi: lỗi tạm thời phục hồi được, provider hỏng kéo dài không treo run, kết quả hợp lệ không mất, UI thể hiện trung thực trạng thái và chuyển động, main worktree không bị chỉnh sửa bởi công việc triển khai này.
