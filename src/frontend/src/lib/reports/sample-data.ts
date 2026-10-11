// Dữ liệu minh họa lấy từ docs/design/screens/{QualityReport,QualityGate,ReleaseHistory}.dc.html (bộ số liệu chuẩn của labelx-design).
// TODO(backend): thay toàn bộ bằng API khi có endpoint; chưa có trong contract: GET /api/runs/{id}/report/, GET /api/releases/, GET /api/releases/{id}/manifest/, POST /api/runs/{id}/report/export/, POST /api/releases/{id}/approve/.
// TODO(backend): rbac-matrix chỉ cho Annotator xem báo cáo ở mức giới hạn; khi nối API, backend phải lọc phần dữ liệu theo vai trò (giao diện minh họa hiện hiển thị đầy đủ cho mọi vai trò).
// Đã có trong contract nhưng chưa nối: GET /api/runs/{id}/gate/ (runs_gate), POST /api/waivers/ (waivers_create).

export type BadgeTone = 'success' | 'danger' | 'warning' | 'info' | '';

export const REPORT_SCOPE = 'Road Vision Urban v1.4 · Quality Control Run #QC-091 · tạo ngày 04/10/2026';

export const REPORT_METRICS = [
  { key: 'frames', label: 'Frame trong phạm vi', value: '12,500', note: '3 task · 7 job', tone: '' },
  { key: 'coverage', label: 'Coverage', value: '92.4%', note: 'Ngưỡng yêu cầu 95%', tone: 'is-warn' },
  { key: 'open', label: 'Lỗi đã xác nhận chưa đóng', value: '12', note: 'Trong đó 3 nghiêm trọng', tone: 'is-bad' },
  { key: 'rework', label: 'Rework hoàn thành', value: '86.0%', note: '74 / 86 yêu cầu', tone: '' },
] as const;

export const ERROR_TYPES = [
  { label: 'Sai nhãn', count: 48, width: 100 },
  { label: 'Hình học', count: 33, width: 69 },
  { label: 'Thiếu object', count: 25, width: 52 },
  { label: 'Trùng / chồng lấn', count: 14, width: 29 },
  { label: 'Thuộc tính / Track', count: 6, width: 13 },
] as const;

export const CONFUSED_PAIRS = [
  { pair: 'car → truck', count: 19 },
  { pair: 'bus → truck', count: 11 },
  { pair: 'motorbike → bicycle', count: 7 },
] as const;

export const CLASS_ROWS = [
  { name: 'car', kind: 'Bounding box', iou: '0.88', precision: '91.2%', recall: '88.7%', errors: 41, warn: false },
  { name: 'pedestrian', kind: 'Bounding box', iou: '0.82', precision: '84.0%', recall: '80.3%', errors: 28, warn: false },
  { name: 'truck', kind: 'Bounding box', iou: '0.74', precision: '78.4%', recall: '72.1%', errors: 36, warn: true },
  { name: 'lane marking', kind: 'Polyline', iou: null, precision: null, recall: null, errors: 21, warn: false },
] as const;

export const ROOT_CAUSES = [
  { cause: 'Guideline chưa nêu rõ xe buýt mini chở hàng', count: 19, action: 'Phê duyệt GAP-012' },
  { cause: 'Cảnh ban đêm thiếu ánh sáng (Task T-119)', count: 23, action: 'Tăng tỷ lệ review cho Task T-119' },
  { cause: 'Annotator mới chưa quen quy tắc hình học G-014', count: 14, action: 'Giao bài hiệu chỉnh' },
] as const;

export const EXPORT_FORMATS = [
  { key: 'pdf', label: 'PDF', note: 'Bản đọc, kèm biểu đồ' },
  { key: 'csv', label: 'CSV', note: 'Bảng số liệu' },
  { key: 'json', label: 'JSON', note: 'Gói báo cáo kèm manifest' },
] as const;

export const GATE_CONDITIONS: ReadonlyArray<{
  name: string; result: string; resultTone?: 'is-warn' | 'is-bad'; resultStrong?: string; resultTail?: string;
  badge: { tone: BadgeTone; label: string }; action: string | null; link?: { href: string; label: string };
}> = [
  { name: 'Toàn vẹn phiên bản', result: 'Snapshot, taxonomy, guideline khớp nhau', badge: { tone: 'success', label: 'Đạt' }, action: null },
  { name: 'Benchmark và kiểm tra mẫu', result: 'Benchmark v1.2 đã đính kèm', badge: { tone: 'success', label: 'Đạt' }, action: null },
  { name: 'Coverage', result: '', resultTone: 'is-warn', resultStrong: '92.4%', resultTail: ' / ngưỡng 95%', badge: { tone: 'danger', label: 'Chưa đạt' }, action: 'Chạy bổ sung hoặc xin waiver' },
  { name: 'Lỗi nghiêm trọng', result: '', resultTone: 'is-bad', resultStrong: '3', resultTail: ' chưa đóng', badge: { tone: 'danger', label: 'Chưa đạt' }, action: 'Sửa và xác minh' },
  { name: 'Rework', result: '12 yêu cầu bắt buộc chưa xác minh', badge: { tone: 'danger', label: 'Chưa đạt' }, action: null, link: { href: '/review/rework', label: 'Mở Rework Tracking' } },
  { name: 'Phê duyệt', result: 'Chưa gửi phê duyệt', badge: { tone: '', label: 'Chờ' }, action: 'Sau khi các điều kiện trên đạt' },
];

export const GATE_SUMMARY = '2 đạt · 3 chưa đạt · 1 chờ phê duyệt';
export const WAIVER_CONDITIONS = ['Coverage', 'Lỗi nghiêm trọng', 'Rework'] as const;

export const RELEASES = [
  { version: 'Road Vision Urban v1.3', run: '#QC-077', frames: '11,800', approver: 'Chi Lâm', date: '2026-09-10', status: { tone: 'success', label: 'Released' }, selected: true },
  { version: 'Road Vision Urban v1.2', run: '#QC-061', frames: '10,400', approver: 'Chi Lâm', date: '2026-08-14', status: { tone: 'success', label: 'Released' }, selected: false },
  { version: 'Road Vision Urban v1.1', run: '#QC-044', frames: '9,000', approver: 'Minh Đức', date: '2026-07-02', status: { tone: 'success', label: 'Released' }, selected: false },
  { version: 'Road Vision Urban v1.4', run: '#QC-091', frames: '12,500', approver: null, date: null, status: { tone: 'danger', label: 'Blocked' }, selected: false },
] as const;

export const MANIFEST_TITLE = 'Manifest · v1.3';
export const MANIFEST: ReadonlyArray<{ k: string; v: string; mono?: boolean }> = [
  { k: 'Snapshot', v: 'SNP-011', mono: true },
  { k: 'Annotation revision', v: 'f02a6d', mono: true },
  { k: 'Taxonomy', v: 'v3' },
  { k: 'Guideline', v: 'v1.2' },
  { k: 'Cấu hình kiểm tra', v: 'v6' },
  { k: 'Benchmark', v: 'v1.1' },
  { k: 'Lỗi đã xác nhận', v: '98 · tất cả đã đóng' },
  { k: 'Báo cáo', v: 'RPT-077', mono: true },
  { k: 'Phê duyệt', v: 'Chi Lâm · 2026-09-10 16:42' },
];
