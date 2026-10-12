import type { ApiEndpoint } from '../types';

export const CALIBRATION_ENDPOINTS = [
  { id: 'calibration_reviewers', method: 'GET', path: '/api/calibration/reviewers/', group: 'Calibration', summary: 'Kết quả hiệu chỉnh reviewer', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [{ user_id: 12, full_name: 'Bình Hồ', completed: 40, assigned: 45, agreement: 0.941, status: 'in_progress' }] } },
  { id: 'calibration_models', method: 'GET', path: '/api/calibration/models/', group: 'Calibration', summary: 'Kết quả hiệu chỉnh model và engine', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [{ model_id: 5, name: 'Detector v2.3', precision: 0.875, recall: 0.81, status: 'completed' }] } },
  { id: 'calibration_assignments_create', method: 'POST', path: '/api/calibration/assignments/', group: 'Calibration', summary: 'Giao bài hiệu chỉnh', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 66, benchmark_id: 9, assignee_user_id: 12, frame_count: 45, due_at: '2026-10-18T00:00:00Z', status: 'assigned' } },
] satisfies ApiEndpoint[];
