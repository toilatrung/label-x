/**
 * Dữ liệu minh họa của Escalations, lấy từ docs/design/screens/Escalations.dc.html.
 * TODO(backend): GET /api/guideline-gaps/, GET /api/decision-cases/, GET /api/escalations/ (hàng chờ phân xử).
 */
export type EscalationsTabKey = 'gaps' | 'cases' | 'adj';
export type Tone = 'info' | 'warning' | 'success' | '';

export const ESCALATION_TABS: { key: EscalationsTabKey; label: string; count: number }[] = [
  { key: 'gaps', label: 'Guideline Gaps', count: 6 },
  { key: 'cases', label: 'Decision Cases', count: 38 },
  { key: 'adj', label: 'Adjudication', count: 18 },
];

export const LIST_TIP = 'Phân xử các case liên quan';

export interface ListRow { a: string; b: string; c: string; d: string; e: string; tone: Tone }

export const GAPS = {
  cols: ['Mã', 'Nội dung còn thiếu', 'Quy tắc', 'Case liên quan', 'Trạng thái'],
  rows: [
    { a: 'GAP-012', b: 'Xe buýt mini chở hàng thuộc nhãn nào', c: 'VEH-03', d: '4 case', e: 'Đề xuất sửa', tone: 'info' },
    { a: 'GAP-011', b: 'Vật bị che hơn 50% có cần gán nhãn', c: 'G-014', d: '7 case', e: 'Chờ phê duyệt', tone: 'warning' },
    { a: 'GAP-009', b: 'Biên polygon khi có bóng đổ', c: 'G-009', d: '3 case', e: 'Chờ phê duyệt', tone: 'warning' },
    { a: 'GAP-007', b: 'Thuộc tính occluded cho người đi bộ', c: 'A-003', d: '5 case', e: 'Đã phê duyệt · Guideline v1.3', tone: 'success' },
    { a: 'GAP-004', b: 'Xe máy chở hai người', c: 'VEH-02', d: '2 case', e: 'Đã phê duyệt · Guideline v1.3', tone: 'success' },
  ] as ListRow[],
};

export const CASES = {
  cols: ['Mã', 'Tình huống', 'Quy tắc', 'Quyết định', 'Phiên bản'],
  rows: [
    { a: 'CASE-040', b: 'Xe bán tải có nắp thùng', c: 'VEH-03', d: 'Gán nhãn truck', e: 'Guideline v1.2', tone: '' },
    { a: 'CASE-034', b: 'Xe van chở người', c: 'VEH-03', d: 'Gán nhãn car', e: 'Guideline v1.2', tone: '' },
    { a: 'CASE-021', b: 'Xe bán tải thùng hở', c: 'VEH-03', d: 'Gán nhãn truck', e: 'Guideline v1.2', tone: '' },
    { a: 'CASE-017', b: 'Người đi bộ bị che bởi cột điện', c: 'G-014', d: 'Vẫn gán nhãn nếu thấy trên 30%', e: 'Guideline v1.2', tone: '' },
    { a: 'CASE-009', b: 'Xe đạp dựng sát tường', c: 'VEH-01', d: 'Không gán nhãn', e: 'Guideline v1.1', tone: '' },
  ] as ListRow[],
};

export const PENDING = [
  { id: 'QC-00098', badge: 'Chuyển cấp trên', title: 'Sai nhãn · Frame 00212 · #04', sub: 'Reviewer bất đồng · quy tắc VEH-03' },
  { id: 'QC-00104', badge: 'Chưa chắc chắn', title: 'Hình học · Frame 00255 · #09', sub: 'Quy tắc G-014 chưa nói rõ về vật bị che' },
  { id: 'QC-00112', badge: 'Chưa chắc chắn', title: 'Thuộc tính · Frame 00310 · #14', sub: 'Quy tắc A-003' },
  { id: 'QC-00115', badge: 'Chuyển cấp trên', title: 'Sai nhãn · Frame 00366 · #02', sub: 'Quy tắc VEH-03' },
];
