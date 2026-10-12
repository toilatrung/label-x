import type { ApiEndpoint } from '../types';

export const DATASETS_ENDPOINTS = [
  { id: 'datasets_list', method: 'GET', path: '/api/datasets/', group: 'Datasets', summary: 'Dataset trong scope người gọi', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ id: 12, name: 'BDD100K Pilot', cvat_project_id: 5, guideline_version: 'bdd100k-v1' }] } },
  { id: 'datasets_tasks', method: 'GET', path: '/api/datasets/{id}/tasks/', group: 'Datasets', summary: 'Cây task và job CVAT', connection: 'backend', responseStatus: 200, response: [{ id: 19, name: 'pilot-daytime', jobs: [{ id: 44, assignee_id: 28, frame_count: 240 }] }] },
] satisfies ApiEndpoint[];
