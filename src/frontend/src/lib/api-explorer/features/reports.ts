import type { ApiEndpoint } from '../types';

export const REPORTS_ENDPOINTS = [
  { id: 'reports_retrieve', method: 'GET', path: '/api/reports/{id}/', group: 'Reports', summary: 'Xuất báo cáo hiệu quả', connection: 'mock', responseStatus: 200, response: { id: 21, input_snapshot_id: 18, reference_id: 9, source_run_id: 31, source_reason: 'final_run', score_version: 'score-v0', metrics: { 'KPI-1': { value: 0.91, status: 'computed' } }, risk_queue: { reviewed: 120 }, random_queue: { reviewed: 100 }, engine_coverage: [] } },
  { id: 'run_report', method: 'GET', path: '/api/runs/{id}/report/', group: 'Reports', summary: 'Báo cáo chất lượng theo QC Run', connection: 'mock', origin: 'design', responseStatus: 200, response: { run_id: 91, display_run_id: 'QC-091', snapshot_id: 14, created_at: '2026-10-04T06:58:00Z', metrics: { frame_count: 12500, object_count: 48912, task_count: 3, job_count: 7, coverage: 0.924, coverage_threshold: 0.95, raw_candidate_count: 512, candidate_count: 384, confirmed_error_count: 126, open_issue_count: 12, open_critical_issues: 3, rework_total: 86, rework_resolved: 74, rework_completion: 0.86 }, confirmed_errors: { label: 48, geometry: 33, missing_object: 25, duplicate_overlap: 14, attribute_track: 6 }, confused_pairs: [{ pair: 'car → truck', count: 19 }, { pair: 'bus → truck', count: 11 }, { pair: 'motorbike → bicycle', count: 7 }], class_metrics: [
    { name: 'car', kind: 'Bounding box', iou: 0.88, precision: 0.912, recall: 0.887, errors: 41 },
    { name: 'pedestrian', kind: 'Bounding box', iou: 0.82, precision: 0.84, recall: 0.803, errors: 28 },
    { name: 'truck', kind: 'Bounding box', iou: 0.74, precision: 0.784, recall: 0.721, errors: 36 },
    { name: 'lane marking', kind: 'Polyline', iou: null, precision: null, recall: null, errors: 21 },
  ], root_causes: [
    { cause: 'Guideline chưa nêu rõ xe buýt mini chở hàng', count: 19, action: 'Phê duyệt GAP-012' },
    { cause: 'Cảnh ban đêm thiếu ánh sáng (Task T-119)', count: 23, action: 'Tăng tỷ lệ review cho Task T-119' },
    { cause: 'Annotator mới chưa quen quy tắc hình học G-014', count: 14, action: 'Giao bài hiệu chỉnh' },
  ] } },
  { id: 'run_report_export', method: 'POST', path: '/api/runs/{id}/report/export/', group: 'Reports', summary: 'Xuất file báo cáo theo định dạng', connection: 'mock', origin: 'design', responseStatus: 202, response: { export_id: 55, run_id: 31, format: 'pdf', status: 'queued', download_url: null } },
] satisfies ApiEndpoint[];
