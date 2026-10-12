import type { ApiEndpoint } from '../types';

export const BENCHMARK_ENDPOINTS = [
  { id: 'benchmarks_list', method: 'GET', path: '/api/benchmarks/', group: 'Benchmark', summary: 'Danh sách phiên bản Ground Truth Benchmark', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [{ id: 9, name: 'Benchmark v1.2', snapshot_id: 18, frame_count: 200, status: 'locked', locked_at: '2026-10-10T08:00:00Z' }] } },
  { id: 'benchmarks_create', method: 'POST', path: '/api/benchmarks/', group: 'Benchmark', summary: 'Tạo phiên bản benchmark', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 10, name: 'Benchmark v1.3', snapshot_id: 18, frame_count: 0, status: 'draft', created_by: 7 } },
  { id: 'benchmarks_import_cvat', method: 'POST', path: '/api/benchmarks/import-cvat/', group: 'Benchmark', summary: 'Nhập Ground Truth từ CVAT', connection: 'mock', origin: 'design', responseStatus: 202, response: { import_id: 22, benchmark_id: 10, cvat_task_ids: [19], status: 'queued' } },
] satisfies ApiEndpoint[];
