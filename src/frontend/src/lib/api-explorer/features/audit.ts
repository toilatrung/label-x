import type { ApiEndpoint } from '../types';

export const AUDIT_ENDPOINTS = [
  { id: 'audit_samples_list', method: 'GET', path: '/api/audit-samples/', group: 'Audit', summary: 'Danh sách mẫu audit theo random hoặc risk', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, run_id: 91, seed: 20261004, population_size: 12500, stream: 'random', selection_method: 'Ngẫu nhiên đều, không phụ thuộc cảnh báo', sample_size: 100, confirmed_errors: 4, residual_error_rate: 0.04, results: [
    { id: 41, frame_id: 1204, task_id: 119, job_id: 2273, status: 'pending', result: null },
    { id: 42, frame_id: 1877, task_id: 119, job_id: 2274, status: 'in_review', result: null },
    { id: 43, frame_id: 2310, task_id: 120, job_id: 2275, status: 'reviewed', result: 'Không có lỗi' },
    { id: 44, frame_id: 2955, task_id: 120, job_id: 2275, status: 'reviewed', result: '1 lỗi · thiếu object' },
  ], risk_groups: [
    { name: 'Mô hình bất đồng với annotation', sample_size: 40, confirmed_errors: 17, rate: 0.425 },
    { name: 'Lớp khó (xe tải, xe buýt)', sample_size: 25, confirmed_errors: 9, rate: 0.36 },
    { name: 'Vật thể nhỏ hoặc bị che', sample_size: 20, confirmed_errors: 6, rate: 0.30 },
    { name: 'Camera / cảnh ban đêm', sample_size: 15, confirmed_errors: 3, rate: 0.20 },
  ] } },
  { id: 'audit_samples_create', method: 'POST', path: '/api/audit-samples/', group: 'Audit', summary: 'Tạo bộ mẫu audit mới', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 45, run_id: 91, stream: 'random', requested_size: 100, seed: 20261004, status: 'ready' } },
] satisfies ApiEndpoint[];
