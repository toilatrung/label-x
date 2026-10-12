import type { ApiEndpoint } from '../types';

export const BENCHMARK_ENDPOINTS = [
  { id: 'benchmarks_list', method: 'GET', path: '/api/benchmarks/', group: 'Benchmark', summary: 'Danh sách phiên bản Ground Truth Benchmark', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [
    { id: 12, name: 'Benchmark v1.2', dataset_name: 'Road Vision Urban', snapshot_id: 14, taxonomy_version: 'v3', frame_count: 200, object_count: 1184, honeypot_count: 30, expert: 'Chi Lâm', coverage: 0.76, status: 'locked', locked_at: '2026-09-28T10:15:00Z' },
    { id: 11, name: 'Benchmark v1.1', dataset_name: 'Road Vision Urban', snapshot_id: 11, taxonomy_version: 'v2', frame_count: 150, expert: 'Chi Lâm', status: 'superseded', locked_at: '2026-08-14T10:15:00Z' },
    { id: 13, name: 'Benchmark v1.3', dataset_name: 'Road Vision Urban', snapshot_id: 14, taxonomy_version: 'v3', frame_count: 240, expert: null, status: 'in_review', locked_at: null },
  ] } },
  { id: 'benchmarks_create', method: 'POST', path: '/api/benchmarks/', group: 'Benchmark', summary: 'Tạo phiên bản benchmark', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 10, name: 'Benchmark v1.3', snapshot_id: 18, frame_count: 0, status: 'draft', created_by: 7 } },
  { id: 'benchmarks_import_cvat', method: 'POST', path: '/api/benchmarks/import-cvat/', group: 'Benchmark', summary: 'Nhập Ground Truth từ CVAT', connection: 'mock', origin: 'design', responseStatus: 202, response: { import_id: 22, benchmark_id: 10, cvat_task_ids: [19], status: 'queued' } },
] satisfies ApiEndpoint[];
