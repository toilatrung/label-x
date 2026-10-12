import type { ApiEndpoint } from '../types';
import { rework } from '../examples';

export const REWORK_ENDPOINTS = [
  { id: 'rework_create', method: 'POST', path: '/api/rework/', group: 'Rework', summary: 'Tạo yêu cầu sửa', connection: 'backend', responseStatus: 201, response: rework },
  { id: 'rework_submitted', method: 'POST', path: '/api/rework/{id}/submitted/', group: 'Rework', summary: 'Ghi nhận annotator đã sửa', connection: 'backend', responseStatus: 202, response: { ...rework, status: 'recheck_pending', submitted_revision: 'sha256:3aa7…992e' } },
  { id: 'rework_verify', method: 'POST', path: '/api/rework/{id}/verify/', group: 'Rework', summary: 'Xác minh kết quả sửa lỗi', connection: 'backend', responseStatus: 200, response: { ...rework, status: 'resolved', submitted_revision: 'sha256:3aa7…992e' } },
  { id: 'rework_list', method: 'GET', path: '/api/rework/', group: 'Rework', summary: 'Danh sách yêu cầu sửa theo scope', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, counts: { fix_pending: 12, recheck_pending: 4, resolved: 74 }, results: [rework] } },
  { id: 'rework_retrieve', method: 'GET', path: '/api/rework/{id}/', group: 'Rework', summary: 'Chi tiết yêu cầu sửa', connection: 'mock', origin: 'design', responseStatus: 200, response: rework },
] satisfies ApiEndpoint[];
