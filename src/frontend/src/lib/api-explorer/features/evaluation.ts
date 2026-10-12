import type { ApiEndpoint } from '../types';
import { reference, evaluation } from '../examples';

export const EVALUATION_ENDPOINTS = [
  { id: 'references_create', method: 'POST', path: '/api/references/', group: 'Evaluation', summary: 'Tạo phiên reference và nhập GT', connection: 'mock', responseStatus: 201, response: reference },
  { id: 'references_lock', method: 'POST', path: '/api/references/{id}/lock/', group: 'Evaluation', summary: 'Khoá reference và provenance', connection: 'mock', responseStatus: 200, response: { ...reference, status: 'locked', locked_by: 15, locked_at: '2026-10-12T05:00:00Z' } },
  { id: 'effort_events_create', method: 'POST', path: '/api/effort-events/', group: 'Evaluation', summary: 'Ghi batch effort event', connection: 'backend', responseStatus: 202, response: { accepted: 3, duplicates: 0 } },
  { id: 'evaluations_create', method: 'POST', path: '/api/evaluations/', group: 'Evaluation', summary: 'Chạy đánh giá KPI', connection: 'mock', responseStatus: 202, response: evaluation },
  { id: 'evaluations_retrieve', method: 'GET', path: '/api/evaluations/{id}/', group: 'Evaluation', summary: 'Kết quả KPI và provenance', connection: 'mock', responseStatus: 200, response: { ...evaluation, status: 'completed', leakage_check: 'passed', metrics: { 'KPI-1': { status: 'computed', value: 0.91, sample_size: 220, denominator: 240, method: 'score-v0' } } } },
  { id: 'evaluation_performance', method: 'GET', path: '/api/evaluation/performance/', group: 'Evaluation', summary: 'Tổng hợp hiệu năng theo luồng lấy mẫu', connection: 'mock', origin: 'design', responseStatus: 200, response: { run_id: 31, benchmark_id: 9, metrics: { reviewer_agreement: 0.941, candidate_precision: 0.875, residual_error_rate: 0.04, benchmark_coverage: 0.76 }, streams: [{ name: 'random', sample_size: 100, confirmed_errors: 4 }] } },
] satisfies ApiEndpoint[];
