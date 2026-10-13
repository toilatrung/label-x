import type { ApiEndpoint } from '../types';

export const DATASETS_ENDPOINTS = [
  { id: 'datasets_list', method: 'GET', path: '/api/datasets/', group: 'Datasets', summary: 'Dataset trong scope người gọi', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [
    { id: 14, name: 'Road Vision Urban', version: 'v1.4', cvat_project_id: 31, guideline_version: 'v1.2', taxonomy_version: 'v3', task_count: 3, job_count: 7, frame_count: 12500, latest_run: { id: 91, display_id: 'QC-091', status: 'partial', started_at: '2026-10-04T06:58:00Z', coverage: 0.924, open_issues: 192, gate: 'blocked' } },
    { id: 13, name: 'Road Vision Urban', version: 'v1.3', cvat_project_id: 31, guideline_version: 'v1.2', taxonomy_version: 'v3', read_only: true, task_count: 2, job_count: 3, frame_count: 11800, latest_run: { id: 77, display_id: 'QC-077', status: 'checked', started_at: '2026-09-10T08:30:00Z', coverage: 0.972, open_issues: 0, gate: 'released' } },
    { id: 9, name: 'Road Vision Highway', version: 'v0.9', cvat_project_id: 34, guideline_version: 'v1.2', taxonomy_version: 'v3', task_count: 2, job_count: 3, frame_count: 5600, latest_run: { id: 85, display_id: 'QC-085', status: 'checked', started_at: '2026-09-30T14:20:00Z', coverage: 0.989, open_issues: 6, gate: 'ready_for_approval' } },
    { id: 3, name: 'Parking Lot', version: 'v0.3', cvat_project_id: 37, guideline_version: 'v1.1', taxonomy_version: 'v2', task_count: 1, job_count: 2, frame_count: 3000, latest_run: null },
  ] } },
  { id: 'datasets_tasks', method: 'GET', path: '/api/datasets/{id}/tasks/', group: 'Datasets', summary: 'Cây task và job CVAT', connection: 'backend', responseStatus: 200, response: [
    { id: 118, name: 'Urban day', coverage: 0.98, candidate_count: 65, confirmed_count: 21, gate: 'passed', jobs: [{ id: 2270, assignee_id: 28, frame_count: 200 }, { id: 2271, assignee_id: 29, frame_count: 200 }, { id: 2272, assignee_id: 30, frame_count: 200 }] },
    { id: 119, name: 'Urban night', coverage: 0.867, candidate_count: 208, confirmed_count: 69, gate: 'blocked', jobs: [{ id: 2273, assignee_id: 28, frame_count: 3000 }, { id: 2274, assignee_id: 29, frame_count: 3000 }] },
    { id: 120, name: 'Urban rain', coverage: 0.976, candidate_count: 111, confirmed_count: 36, gate: 'partial', jobs: [{ id: 2275, assignee_id: 30, frame_count: 2950 }, { id: 2276, assignee_id: 31, frame_count: 2950 }] },
  ] },
] satisfies ApiEndpoint[];
