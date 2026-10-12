import type { ApiEndpoint } from '../types';

export const RELEASES_ENDPOINTS = [
  { id: 'releases_list', method: 'GET', path: '/api/releases/', group: 'Releases', summary: 'Danh sách các lần phát hành', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, results: [
    { id: 13, dataset_name: 'Road Vision Urban', version: 'v1.3', dataset_id: 13, snapshot_id: 11, run_id: 77, display_run_id: 'QC-077', frame_count: 11800, approver: 'Chi Lâm', status: 'released', released_at: '2026-09-10T16:42:00Z' },
    { id: 12, dataset_name: 'Road Vision Urban', version: 'v1.2', dataset_id: 12, snapshot_id: 10, run_id: 61, display_run_id: 'QC-061', frame_count: 10400, approver: 'Chi Lâm', status: 'released', released_at: '2026-08-14T10:30:00Z' },
    { id: 11, dataset_name: 'Road Vision Urban', version: 'v1.1', dataset_id: 11, snapshot_id: 9, run_id: 44, display_run_id: 'QC-044', frame_count: 9000, approver: 'Minh Đức', status: 'released', released_at: '2026-07-02T09:00:00Z' },
    { id: 14, dataset_name: 'Road Vision Urban', version: 'v1.4', dataset_id: 14, snapshot_id: 14, run_id: 91, display_run_id: 'QC-091', frame_count: 12500, approver: null, status: 'blocked', released_at: null },
  ] } },
  { id: 'release_manifest', method: 'GET', path: '/api/releases/{id}/manifest/', group: 'Releases', summary: 'Manifest phát hành có provenance', connection: 'mock', origin: 'design', responseStatus: 200, response: { release_id: 13, version: 'v1.3', snapshot: { id: 11, display_id: 'SNP-011', revision: 'f02a6d' }, taxonomy_version: 'v3', run_id: 77, display_run_id: 'QC-077', config_version_id: 6, guideline_version: 'v1.2', benchmark_version: 'v1.1', confirmed_errors: 98, open_errors: 0, report_id: 'RPT-077', approved_by_name: 'Chi Lâm', approved_at: '2026-09-10T16:42:00Z', artifacts: [] } },
  { id: 'release_approve', method: 'POST', path: '/api/releases/{id}/approve/', group: 'Releases', summary: 'Phê duyệt phát hành', connection: 'mock', origin: 'design', responseStatus: 200, response: { id: 13, version: 'v1.3', status: 'approved', approved_by: 7, approved_at: '2026-10-12T07:00:00Z' } },
] satisfies ApiEndpoint[];
