import type { ApiEndpoint } from '../types';

export const ESCALATIONS_ENDPOINTS = [
  { id: 'guideline_gaps_list', method: 'GET', path: '/api/guideline-gaps/', group: 'Escalations', summary: 'Danh sách khoảng trống guideline', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, count: 6, results: [
    { id: 12, code: 'GAP-012', issue_id: 98, status: 'proposed', title: 'Xe buýt mini chở hàng thuộc nhãn nào', proposed_rule: 'VEH-03', related_case_count: 4, status_label: 'Đề xuất sửa' },
    { id: 11, code: 'GAP-011', issue_id: 104, status: 'pending_approval', title: 'Vật bị che hơn 50% có cần gán nhãn', proposed_rule: 'G-014', related_case_count: 7, status_label: 'Chờ phê duyệt' },
    { id: 9, code: 'GAP-009', issue_id: 109, status: 'pending_approval', title: 'Biên polygon khi có bóng đổ', proposed_rule: 'G-009', related_case_count: 3, status_label: 'Chờ phê duyệt' },
    { id: 7, code: 'GAP-007', issue_id: 112, status: 'approved', title: 'Thuộc tính occluded cho người đi bộ', proposed_rule: 'A-003', related_case_count: 5, status_label: 'Đã phê duyệt · Guideline v1.3' },
    { id: 4, code: 'GAP-004', issue_id: 115, status: 'approved', title: 'Xe máy chở hai người', proposed_rule: 'VEH-02', related_case_count: 2, status_label: 'Đã phê duyệt · Guideline v1.3' },
  ] } },
  { id: 'guideline_gaps_create', method: 'POST', path: '/api/guideline-gaps/', group: 'Escalations', summary: 'Tạo Guideline Gap từ phân xử', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 13, code: 'GAP-013', issue_id: 98, status: 'proposed', title: 'Xe buýt mini chở hàng thuộc nhãn nào', proposed_rule: 'VEH-03', reason: 'Reviewer bất đồng giữa bus và truck.', related_case_count: 0, status_label: 'Đề xuất sửa' } },
] satisfies ApiEndpoint[];
