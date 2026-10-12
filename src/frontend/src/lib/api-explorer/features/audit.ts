import type { ApiEndpoint } from '../types';

export const AUDIT_ENDPOINTS = [
  { id: 'audit_samples_list', method: 'GET', path: '/api/audit-samples/', group: 'Audit', summary: 'Danh sách mẫu audit theo random hoặc risk', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, stream: 'random', results: [{ id: 41, run_id: 31, frame_id: 3301, status: 'pending', seed: 104729 }] } },
  { id: 'audit_samples_create', method: 'POST', path: '/api/audit-samples/', group: 'Audit', summary: 'Tạo bộ mẫu audit mới', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 42, run_id: 31, stream: 'random', requested_size: 100, seed: 104729, status: 'ready' } },
] satisfies ApiEndpoint[];
