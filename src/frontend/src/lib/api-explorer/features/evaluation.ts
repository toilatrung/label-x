import type { ApiEndpoint } from '../types';
import { reference, evaluation } from '../examples';

export const EVALUATION_ENDPOINTS = [
  { id: 'references_list', method: 'GET', path: '/api/references/', group: 'Evaluation', summary: 'Reference của Dataset, lọc theo status, mới nhất trước', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ ...reference, status: 'locked' }] } },
  { id: 'references_create', method: 'POST', path: '/api/references/', group: 'Evaluation', summary: 'Tạo phiên reference và nhập GT', connection: 'mock', responseStatus: 201, response: reference },
  { id: 'references_lock', method: 'POST', path: '/api/references/{id}/lock/', group: 'Evaluation', summary: 'Khoá reference và provenance', connection: 'mock', responseStatus: 200, response: { ...reference, status: 'locked', locked_by: 15, locked_at: '2026-10-12T05:00:00Z' } },
  { id: 'effort_events_create', method: 'POST', path: '/api/effort-events/', group: 'Evaluation', summary: 'Ghi batch effort event', connection: 'backend', responseStatus: 202, response: { accepted: 3, duplicates: 0 } },
  { id: 'evaluations_list', method: 'GET', path: '/api/evaluations/', group: 'Evaluation', summary: 'KPI evaluation của Dataset, lọc theo run, mới nhất trước', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [evaluation] } },
  { id: 'evaluations_create', method: 'POST', path: '/api/evaluations/', group: 'Evaluation', summary: 'Chạy đánh giá KPI', connection: 'mock', responseStatus: 202, response: evaluation },
  { id: 'evaluations_retrieve', method: 'GET', path: '/api/evaluations/{id}/', group: 'Evaluation', summary: 'Kết quả KPI và provenance', connection: 'mock', responseStatus: 200, response: { ...evaluation, status: 'completed', leakage_check: 'passed', metrics: { 'KPI-1': { status: 'computed', value: 0.91, sample_size: 220, denominator: 240, method: 'score-v0' } } } },
  { id: 'evaluation_performance', method: 'GET', path: '/api/evaluation/performance/', group: 'Evaluation', summary: 'Tổng hợp hiệu năng theo luồng lấy mẫu', connection: 'mock', origin: 'design', responseStatus: 200, response: { run_id: 91, display_run_id: 'QC-091', benchmark_id: 12, metrics: { reviewer_agreement: 0.941, reviewer_agreement_denominator: 135, candidate_precision: 0.875, residual_error_rate: 0.04, benchmark_coverage: 0.76 }, streams: [
    { name: 'Kiểm tra ngẫu nhiên', stream: 'random', sample_size: 100, confirmed_errors: 4, rate: 0.04, purpose: 'Ước lượng chất lượng toàn dataset' },
    { name: 'Lấy mẫu theo rủi ro', stream: 'risk', sample_size: 100, confirmed_errors: 35, rate: 0.35, purpose: 'Tìm lỗi · không suy ra tỷ lệ chung' },
    { name: 'Benchmark', stream: 'benchmark', sample_size: 200, confirmed_errors: 24, rate: 0.12, purpose: 'Đo reviewer và mô hình' },
  ] } },
] satisfies ApiEndpoint[];
