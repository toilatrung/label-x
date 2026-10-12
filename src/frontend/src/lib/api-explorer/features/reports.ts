import type { ApiEndpoint } from '../types';

export const REPORTS_ENDPOINTS = [
  { id: 'reports_retrieve', method: 'GET', path: '/api/reports/{id}/', group: 'Reports', summary: 'Xuất báo cáo hiệu quả', connection: 'mock', responseStatus: 200, response: { id: 21, input_snapshot_id: 18, reference_id: 9, source_run_id: 31, source_reason: 'final_run', score_version: 'score-v0', metrics: { 'KPI-1': { value: 0.91, status: 'computed' } }, risk_queue: { reviewed: 120 }, random_queue: { reviewed: 100 }, engine_coverage: [] } },
  { id: 'run_report', method: 'GET', path: '/api/runs/{id}/report/', group: 'Reports', summary: 'Báo cáo chất lượng theo QC Run', connection: 'mock', origin: 'design', responseStatus: 200, response: { run_id: 31, snapshot_id: 18, metrics: { coverage: 0.924, open_critical_issues: 3, rework_completion: 0.86 }, confirmed_errors: { label: 48, geometry: 33, missing_object: 25 } } },
  { id: 'run_report_export', method: 'POST', path: '/api/runs/{id}/report/export/', group: 'Reports', summary: 'Xuất file báo cáo theo định dạng', connection: 'mock', origin: 'design', responseStatus: 202, response: { export_id: 55, run_id: 31, format: 'pdf', status: 'queued', download_url: null } },
] satisfies ApiEndpoint[];
