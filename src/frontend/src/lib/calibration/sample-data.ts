// Dữ liệu minh họa lấy từ docs/design/screens/{PerformanceEvaluation,Benchmark,AuditSampling,Calibration}.dc.html.
// TODO(backend): thay bằng API khi có endpoint (chưa có trong contract): GET /api/benchmarks/, POST /api/benchmarks/, POST /api/benchmarks/import-cvat/,
// GET /api/audit-samples/ (random | risk), POST /api/audit-samples/, GET /api/calibration/reviewers/, GET /api/calibration/models/, POST /api/calibration/assignments/.

// Performance Evaluation: G-3 (thống nhất reviewer), G-4 (lỗi còn sót) và luồng ngẫu nhiên/rủi ro đã nối API (GET /api/evaluations/{id}/, GET /api/reports/{id}/).
// Phần dưới đây chưa có trong contract nên giữ minh họa kèm NotConnectedNotice.
export const PERF_SAMPLE_METRICS = {
  precision: { label: 'Độ chính xác của candidate', value: '87.5%', note: 'Candidate được xác nhận là lỗi thật' },
  coverage: { label: 'Benchmark coverage', value: '76.0%', note: 'Phần dataset có Ground Truth', progress: 76 },
} as const;

export const PERF_BENCHMARK_STREAM = { name: 'Benchmark', n: '200', errors: '24', rate: '12.0%', use: 'Đo reviewer và mô hình' } as const;

export const ACTIVE_CALIBRATIONS: ReadonlyArray<{ name: string; progress?: { label: string; pct: number }; sub?: string }> = [
  { name: 'Reviewer Bình Hồ', progress: { label: '40 / 45', pct: 89 } },
  { name: 'Reviewer An Nguyễn', progress: { label: '43 / 45', pct: 96 } },
  { name: 'Mô hình độc lập', sub: 'Đánh giá candidate bị thiếu' },
  { name: 'Geometry engine', sub: 'Đánh giá ngưỡng' },
];

export const BENCHMARKS = [
  { version: 'Benchmark v1.2', scope: 'Road Vision Urban · Taxonomy v3', frames: '200', expert: 'Chi Lâm', status: { tone: 'success', label: 'Đã khoá' }, selected: true },
  { version: 'Benchmark v1.1', scope: 'Road Vision Urban · Taxonomy v2', frames: '150', expert: 'Chi Lâm', status: { tone: '', label: 'Đã thay thế' }, selected: false },
  { version: 'Benchmark v1.3', scope: 'Road Vision Urban · Taxonomy v3', frames: '240', expert: 'Chưa phân công', status: { tone: 'info', label: 'Đang duyệt' }, selected: false },
] as const;

export const BENCHMARK_DETAIL: ReadonlyArray<[string, string]> = [
  ['Benchmark coverage', '76.0% dataset'],
  ['Frame chuẩn', '200 frame · 1,184 object'],
  ['Frame bẫy (honeypot)', '30 frame ẩn cho reviewer'],
  ['Taxonomy', 'v3'],
  ['Khoá lúc', '2026-09-28 10:15'],
];

export const RANDOM_AUDIT_FIELDS: ReadonlyArray<{ k: string; v: string; mono?: boolean; warn?: boolean }> = [
  { k: 'Mã hạt giống (seed)', v: '20261004', mono: true },
  { k: 'Số frame', v: '100 / 12,500' },
  { k: 'Cách chọn', v: 'Ngẫu nhiên đều, không phụ thuộc cảnh báo' },
  { k: 'Tỷ lệ lỗi còn sót', v: '4.0% · 4 lỗi trong 100 frame', warn: true },
];

export const RANDOM_AUDIT_ROWS = [
  { frame: 'Frame 01204', job: 'T-119 · Job 2273', status: { tone: '', label: 'Chờ review' }, result: null },
  { frame: 'Frame 01877', job: 'T-119 · Job 2274', status: { tone: 'info', label: 'Đang review' }, result: null },
  { frame: 'Frame 02310', job: 'T-120 · Job 2275', status: { tone: 'success', label: 'Đã review' }, result: 'Không có lỗi' },
  { frame: 'Frame 02955', job: 'T-120 · Job 2275', status: { tone: 'success', label: 'Đã review' }, result: '1 lỗi · thiếu object' },
] as const;

export const RISK_ROWS = [
  { name: 'Mô hình bất đồng với annotation', n: '40', errors: '17', rate: '42.5%' },
  { name: 'Lớp khó (xe tải, xe buýt)', n: '25', errors: '9', rate: '36.0%' },
  { name: 'Vật thể nhỏ hoặc bị che', n: '20', errors: '6', rate: '30.0%' },
  { name: 'Camera / cảnh ban đêm', n: '15', errors: '3', rate: '20.0%' },
] as const;

export const REVIEWER_ROWS = [
  { name: 'Bình Hồ', agree: '40 / 45 (88.9%)', missed: '6.7%', missedWarn: true, falseAlarm: '4.4%', last: '2026-10-03 · Benchmark v1.2' },
  { name: 'An Nguyễn', agree: '43 / 45 (95.6%)', missed: '0.0%', missedWarn: false, falseAlarm: '2.2%', last: '2026-10-03 · Benchmark v1.2' },
  { name: 'Chi Lâm', agree: '44 / 45 (97.8%)', missed: '0.0%', missedWarn: false, falseAlarm: '2.2%', last: '2026-10-02 · Benchmark v1.2' },
] as const;

export const MODEL_ROWS = [
  { name: 'car', threshold: '0.60', precision: '91.2%', recall: '88.7%', warn: false, status: { tone: 'success', label: 'Đủ Ground Truth' } },
  { name: 'truck', threshold: '0.60', precision: '78.4%', recall: '72.1%', warn: true, status: { tone: 'success', label: 'Đủ Ground Truth' } },
  { name: 'pedestrian', threshold: '0.55', precision: '84.0%', recall: '80.3%', warn: false, status: { tone: 'success', label: 'Đủ Ground Truth' } },
  { name: 'motorbike', threshold: '0.55', precision: null, recall: null, warn: false, status: { tone: 'warning', label: 'Không đủ mẫu để đánh giá' } },
] as const;
