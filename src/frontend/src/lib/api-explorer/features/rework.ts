import type { ApiEndpoint } from '../types';
import { rework } from '../examples';

export const REWORK_ENDPOINTS = [
  { id: 'rework_create', method: 'POST', path: '/api/rework/', group: 'Rework', summary: 'Tạo yêu cầu sửa', connection: 'backend', responseStatus: 201, response: rework },
  { id: 'rework_submitted', method: 'POST', path: '/api/rework/{id}/submitted/', group: 'Rework', summary: 'Ghi nhận annotator đã sửa', connection: 'backend', responseStatus: 202, response: { ...rework, status: 'recheck_pending', submitted_revision: 'sha256:3aa7…992e' } },
  { id: 'rework_verify', method: 'POST', path: '/api/rework/{id}/verify/', group: 'Rework', summary: 'Xác minh kết quả sửa lỗi', connection: 'backend', responseStatus: 200, response: { ...rework, status: 'resolved', submitted_revision: 'sha256:3aa7…992e' } },
  { id: 'rework_list', method: 'GET', path: '/api/rework/', group: 'Rework', summary: 'Danh sách yêu cầu sửa theo scope', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, counts: { total: 86, fix_pending: 5, recheck_pending: 7, resolved: 74, reopened: 0 }, results: [
    { ...rework, id: 212, code: 'RW-0212', issue_code: 'QC-00061', frame_id: 104, object_id: 12, action: 'Đổi nhãn car → truck', annotator_name: 'Bình Hồ', due_at: '2026-10-06', severity: 'critical', status: 'fix_pending' },
    { ...rework, id: 213, code: 'RW-0213', issue_code: 'QC-00064', frame_id: 118, object_id: 8, action: 'Xoá bản ghi trùng #08', annotator_name: 'Bình Hồ', due_at: '2026-10-06', severity: 'medium', status: 'fix_pending' },
    { ...rework, id: 215, code: 'RW-0215', issue_code: 'QC-00067', frame_id: 131, object_id: null, action: 'Thêm bounding box cho xe máy bị thiếu', annotator_name: 'An Nguyễn', due_at: '2026-10-07', severity: 'critical', status: 'fix_pending' },
    { ...rework, id: 216, code: 'RW-0216', issue_code: 'QC-00075', frame_id: 160, object_id: 3, action: 'Chỉnh lại biên polygon', annotator_name: 'Chi Lâm', due_at: '2026-10-07', severity: 'minor', status: 'fix_pending' },
    { ...rework, id: 219, code: 'RW-0219', issue_code: 'QC-00081', frame_id: 188, object_id: 15, action: 'Bổ sung thuộc tính occluded', annotator_name: 'Chi Lâm', due_at: '2026-10-08', severity: 'minor', status: 'fix_pending' },
    { ...rework, id: 198, code: 'RW-0198', issue_code: 'QC-00044', frame_id: 71, object_id: 2, action: 'Đã đổi nhãn bus → truck', annotator_name: 'An Nguyễn', due_at: '2026-10-05', severity: 'critical', status: 'recheck_pending' },
    { ...rework, id: 201, code: 'RW-0201', issue_code: 'QC-00049', frame_id: 82, object_id: 9, action: 'Đã chỉnh bounding box', annotator_name: 'Bình Hồ', due_at: '2026-10-05', severity: 'medium', status: 'recheck_pending' },
    { ...rework, id: 203, code: 'RW-0203', issue_code: 'QC-00052', frame_id: 90, object_id: 11, action: 'Đã xoá bản ghi trùng', annotator_name: 'Chi Lâm', due_at: '2026-10-05', severity: 'medium', status: 'recheck_pending' },
    { ...rework, id: 204, code: 'RW-0204', issue_code: 'QC-00055', frame_id: 95, object_id: null, action: 'Đã thêm object bị thiếu', annotator_name: 'An Nguyễn', due_at: '2026-10-05', severity: 'critical', status: 'recheck_pending' },
    { ...rework, id: 207, code: 'RW-0207', issue_code: 'QC-00058', frame_id: 99, object_id: 4, action: 'Đã chỉnh biên polygon', annotator_name: 'Bình Hồ', due_at: '2026-10-06', severity: 'minor', status: 'recheck_pending' },
    { ...rework, id: 150, code: 'RW-0150', issue_code: 'QC-00012', frame_id: 20, object_id: 3, action: 'Đã đổi nhãn van → car', annotator_name: 'Chi Lâm', due_at: '2026-10-02', severity: 'medium', status: 'resolved' },
    { ...rework, id: 151, code: 'RW-0151', issue_code: 'QC-00013', frame_id: 22, object_id: 7, action: 'Đã chỉnh bounding box', annotator_name: 'Chi Lâm', due_at: '2026-10-02', severity: 'minor', status: 'resolved' },
    { ...rework, id: 153, code: 'RW-0153', issue_code: 'QC-00017', frame_id: 31, object_id: null, action: 'Đã thêm người đi bộ bị thiếu', annotator_name: 'An Nguyễn', due_at: '2026-10-02', severity: 'critical', status: 'resolved' },
    { ...rework, id: 158, code: 'RW-0158', issue_code: 'QC-00021', frame_id: 40, object_id: 5, action: 'Đã xoá bản ghi trùng', annotator_name: 'Bình Hồ', due_at: '2026-10-03', severity: 'medium', status: 'resolved' },
    { ...rework, id: 161, code: 'RW-0161', issue_code: 'QC-00026', frame_id: 49, object_id: 10, action: 'Đã bổ sung thuộc tính', annotator_name: 'Bình Hồ', due_at: '2026-10-03', severity: 'minor', status: 'resolved' },
  ] } },
  { id: 'rework_retrieve', method: 'GET', path: '/api/rework/{id}/', group: 'Rework', summary: 'Chi tiết yêu cầu sửa', connection: 'backend', responseStatus: 200, response: rework },
  { id: 'rework_current_revision', method: 'GET', path: '/api/rework/{id}/current-revision/', group: 'Rework', summary: 'Đọc revision CVAT hiện tại của job rework', connection: 'backend', responseStatus: 200, response: { rework_id: 212, cvat_job_id: 2272, revision_sha256: '3aa7baf46bf91ae8786a6629833544f2777c8e4fe769c587bcb0c91e29cf992e', original_revision: '91c4b74fa09211213d44ab35ce7a2db399ea595ab6ef912077245c4f04418fa2', unchanged: false, rework_status: 'fix_pending', read_at: '2026-10-12T05:15:00Z' } },
] satisfies ApiEndpoint[];
