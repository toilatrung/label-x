import type { ApiEndpoint } from '../types';

export const RELEASES_ENDPOINTS = [
  { id: 'releases_list', method: 'GET', path: '/api/releases/', group: 'Releases', summary: 'Danh sách các lần phát hành', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, results: [{ id: 13, version: 'v1.3', dataset_id: 12, snapshot_id: 18, run_id: 31, status: 'released', released_at: '2026-10-11T09:00:00Z' }] } },
  { id: 'release_manifest', method: 'GET', path: '/api/releases/{id}/manifest/', group: 'Releases', summary: 'Manifest phát hành có provenance', connection: 'mock', origin: 'design', responseStatus: 200, response: { release_id: 13, version: 'v1.3', snapshot: { id: 18, revision: 'sha256:91c4…8fa2' }, run_id: 31, config_version_id: 4, guideline_version: 'bdd100k-v1', artifacts: [] } },
  { id: 'release_approve', method: 'POST', path: '/api/releases/{id}/approve/', group: 'Releases', summary: 'Phê duyệt phát hành', connection: 'mock', origin: 'design', responseStatus: 200, response: { id: 13, version: 'v1.3', status: 'approved', approved_by: 7, approved_at: '2026-10-12T07:00:00Z' } },
] satisfies ApiEndpoint[];
