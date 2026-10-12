// Dữ liệu minh họa cho hàng đợi kiểm tra, lấy từ docs/design/screens/review-data.js (ReviewQueues.dc.html).
// TODO(backend): thay bằng GET /api/runs/{id}/frames/ (đã nối ở vùng dữ liệu thật) khi có tìm kiếm, mức ưu tiên, loại cảnh báo, ảnh thu nhỏ, cảnh và thời gian ở API.
// TODO(backend): nút "Bắt đầu kiểm tra" từng ảnh cần POST /api/queues/{name}/next/ nhận đúng frame; hiện chỉ có nhận frame kế tiếp.

export interface SampleQueueFrame {
  name: string;
  id: string;
  frame: string;
  alert: 'Thiếu nhãn' | 'Hộp lệch' | 'Nhãn trùng';
  priority: 'Cao' | 'Trung bình';
  scene: string;
  time: string;
  image: string;
}

export const SAMPLE_QUEUE_FRAMES: readonly SampleQueueFrame[] = [
  { name: 'Ảnh 001', id: 'BDD100K-0001234', frame: '001234', alert: 'Thiếu nhãn', priority: 'Cao', scene: 'Đường phố', time: '10 thg 6, 2024 10:24', image: '/samples/frame-001.png' },
  { name: 'Ảnh 002', id: 'BDD100K-0005678', frame: '005678', alert: 'Hộp lệch', priority: 'Trung bình', scene: 'Người đi bộ', time: '10 thg 6, 2024 09:17', image: '/samples/frame-002.png' },
  { name: 'Ảnh 003', id: 'BDD100K-0009012', frame: '009012', alert: 'Nhãn trùng', priority: 'Trung bình', scene: 'Biển báo', time: '10 thg 6, 2024 08:03', image: '/samples/frame-003.png' },
];

export const ALL = 'Tất cả';
export const PRIORITY_OPTIONS = [ALL, 'Cao', 'Trung bình'] as const;
export const ALERT_OPTIONS = [ALL, 'Thiếu nhãn', 'Hộp lệch', 'Nhãn trùng'] as const;
