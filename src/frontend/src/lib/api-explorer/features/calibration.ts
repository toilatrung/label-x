import type { ApiEndpoint } from '../types';

export const CALIBRATION_ENDPOINTS = [
  { id: 'calibration_reviewers', method: 'GET', path: '/api/calibration/reviewers/', group: 'Calibration', summary: 'Kết quả hiệu chỉnh reviewer', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [
    { user_id: 12, full_name: 'Bình Hồ', completed: 40, assigned: 45, agreement: 0.889, missed_rate: 0.067, false_alarm_rate: 0.044, last_calibration_at: '2026-10-03', benchmark: 'Benchmark v1.2', status: 'in_progress' },
    { user_id: 13, full_name: 'An Nguyễn', completed: 43, assigned: 45, agreement: 0.956, missed_rate: 0, false_alarm_rate: 0.022, last_calibration_at: '2026-10-03', benchmark: 'Benchmark v1.2', status: 'in_progress' },
    { user_id: 14, full_name: 'Chi Lâm', completed: 44, assigned: 45, agreement: 0.978, missed_rate: 0, false_alarm_rate: 0.022, last_calibration_at: '2026-10-02', benchmark: 'Benchmark v1.2', status: 'completed' },
  ] } },
  { id: 'calibration_models', method: 'GET', path: '/api/calibration/models/', group: 'Calibration', summary: 'Kết quả hiệu chỉnh model và engine', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [
    { model_id: 5, name: 'car', threshold: 0.60, precision: 0.912, recall: 0.887, status: 'completed' },
    { model_id: 5, name: 'truck', threshold: 0.60, precision: 0.784, recall: 0.721, status: 'completed', warning: true },
    { model_id: 5, name: 'pedestrian', threshold: 0.55, precision: 0.84, recall: 0.803, status: 'completed' },
    { model_id: 5, name: 'motorbike', threshold: 0.55, precision: null, recall: null, status: 'insufficient_sample' },
  ] } },
  { id: 'calibration_assignments_create', method: 'POST', path: '/api/calibration/assignments/', group: 'Calibration', summary: 'Giao bài hiệu chỉnh', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 66, benchmark_id: 9, assignee_user_id: 12, frame_count: 45, due_at: '2026-10-18T00:00:00Z', status: 'assigned' } },
] satisfies ApiEndpoint[];
