/**
 * Dữ liệu minh họa của ReworkTracking, lấy từ docs/design/screens/ReworkTracking.dc.html.
 * TODO(backend): GET /api/rework/ (danh sách và số đếm theo trạng thái).
 */
export type ReworkTabKey = 'todo' | 'verify' | 'closed';
export type ReworkSeverity = 'danger' | 'warning' | '';

export interface ReworkRow {
  id: string; issue: string; where: string; action: string; who: string; due: string;
  severity: string; severityTone: ReworkSeverity;
}

export const REWORK_TABS: { key: ReworkTabKey; label: string; count: number; tip: string }[] = [
  { key: 'todo', label: 'Chờ sửa', count: 5, tip: 'Xem yêu cầu' },
  { key: 'verify', label: 'Chờ xác minh', count: 7, tip: 'Xác minh revision mới' },
  { key: 'closed', label: 'Đã đóng', count: 74, tip: 'Xem lịch sử yêu cầu' },
];

const row = (id: string, issue: string, where: string, action: string, who: string, due: string, severity: string, severityTone: ReworkSeverity): ReworkRow =>
  ({ id, issue, where, action, who, due, severity, severityTone });
const CRIT = ['Nghiêm trọng', 'danger'] as const;
const MID = ['Trung bình', 'warning'] as const;
const LOW = ['Nhẹ', ''] as const;

export const REWORK_ROWS: Record<ReworkTabKey, ReworkRow[]> = {
  todo: [
    row('RW-0212', 'QC-00061', 'Frame 00104 · #12', 'Đổi nhãn car → truck', 'Bình Hồ', '2026-10-06', ...CRIT),
    row('RW-0213', 'QC-00064', 'Frame 00118 · #08', 'Xoá bản ghi trùng #08', 'Bình Hồ', '2026-10-06', ...MID),
    row('RW-0215', 'QC-00067', 'Frame 00131 · —', 'Thêm bounding box cho xe máy bị thiếu', 'An Nguyễn', '2026-10-07', ...CRIT),
    row('RW-0216', 'QC-00075', 'Frame 00160 · #03', 'Chỉnh lại biên polygon', 'Chi Lâm', '2026-10-07', ...LOW),
    row('RW-0219', 'QC-00081', 'Frame 00188 · #15', 'Bổ sung thuộc tính occluded', 'Chi Lâm', '2026-10-08', ...LOW),
  ],
  verify: [
    row('RW-0198', 'QC-00044', 'Frame 00071 · #02', 'Đã đổi nhãn bus → truck', 'An Nguyễn', '2026-10-05', ...CRIT),
    row('RW-0201', 'QC-00049', 'Frame 00082 · #09', 'Đã chỉnh bounding box', 'Bình Hồ', '2026-10-05', ...MID),
    row('RW-0203', 'QC-00052', 'Frame 00090 · #11', 'Đã xoá bản ghi trùng', 'Chi Lâm', '2026-10-05', ...MID),
    row('RW-0204', 'QC-00055', 'Frame 00095 · —', 'Đã thêm object bị thiếu', 'An Nguyễn', '2026-10-05', ...CRIT),
    row('RW-0207', 'QC-00058', 'Frame 00099 · #04', 'Đã chỉnh biên polygon', 'Bình Hồ', '2026-10-06', ...LOW),
  ],
  closed: [
    row('RW-0150', 'QC-00012', 'Frame 00020 · #03', 'Đã đổi nhãn van → car', 'Chi Lâm', '2026-10-02', ...MID),
    row('RW-0151', 'QC-00013', 'Frame 00022 · #07', 'Đã chỉnh bounding box', 'Chi Lâm', '2026-10-02', ...LOW),
    row('RW-0153', 'QC-00017', 'Frame 00031 · —', 'Đã thêm người đi bộ bị thiếu', 'An Nguyễn', '2026-10-02', ...CRIT),
    row('RW-0158', 'QC-00021', 'Frame 00040 · #05', 'Đã xoá bản ghi trùng', 'Bình Hồ', '2026-10-03', ...MID),
    row('RW-0161', 'QC-00026', 'Frame 00049 · #10', 'Đã bổ sung thuộc tính', 'Bình Hồ', '2026-10-03', ...LOW),
  ],
};
