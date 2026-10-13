import type { ApiEndpoint } from '../types';
import { waiver } from '../examples';

export const GATE_ENDPOINTS = [
  { id: 'runs_gate', method: 'GET', path: '/api/runs/{id}/gate/', group: 'Gate', summary: 'Kết quả từng điều kiện gate', connection: 'mock', responseStatus: 200, response: { run_id: 91, source_run_id: 91, source_reason: 'final_run', status: 'failed', summary: '2 đạt · 3 chưa đạt · 1 chờ phê duyệt', conditions: [
    { name: 'Toàn vẹn phiên bản', status: 'passed', result: 'Snapshot, taxonomy, guideline khớp nhau', observed: 1, threshold: 1, waiver_id: null },
    { name: 'Benchmark và kiểm tra mẫu', status: 'passed', result: 'Benchmark v1.2 đã đính kèm', observed: 1, threshold: 1, waiver_id: null },
    { name: 'Coverage', status: 'failed', result: '92.4% / ngưỡng 95%', observed: 0.924, threshold: 0.95, action: 'Chạy bổ sung hoặc xin waiver', waiver_id: null },
    { name: 'Lỗi nghiêm trọng', status: 'failed', result: '3 chưa đóng', observed: 3, threshold: 0, action: 'Sửa và xác minh', waiver_id: null },
    { name: 'Rework', status: 'failed', result: '12 yêu cầu bắt buộc chưa xác minh', observed: 12, threshold: 0, action: 'Mở Rework Tracking', waiver_id: null },
    { name: 'Phê duyệt', status: 'not_checked', result: 'Chưa gửi phê duyệt', observed: null, threshold: null, action: 'Sau khi các điều kiện trên đạt', waiver_id: null },
  ] } },
  { id: 'waivers_create', method: 'POST', path: '/api/waivers/', group: 'Gate', summary: 'Đề nghị waiver điều kiện gate', connection: 'mock', responseStatus: 201, response: waiver },
  { id: 'waivers_approve', method: 'POST', path: '/api/waivers/{id}/approve/', group: 'Gate', summary: 'Duyệt hoặc từ chối waiver', connection: 'mock', responseStatus: 200, response: { ...waiver, approved_by: 7, status: 'approved' } },
] satisfies ApiEndpoint[];
