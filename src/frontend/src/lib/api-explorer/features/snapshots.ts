import type { ApiEndpoint } from '../types';
import { run, snapshot } from '../examples';

export const SNAPSHOTS_ENDPOINTS = [
  { id: 'snapshots_list', method: 'GET', path: '/api/snapshots/', group: 'Snapshots', summary: 'Danh sách snapshot theo dataset', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [snapshot] } },
  { id: 'snapshots_create', method: 'POST', path: '/api/snapshots/', group: 'Snapshots', summary: 'Tạo snapshot bất biến', connection: 'backend', responseStatus: 202, response: { id: 18, status: 'pending', status_url: '/api/snapshots/18/' } },
  { id: 'snapshots_retrieve', method: 'GET', path: '/api/snapshots/{id}/', group: 'Snapshots', summary: 'Chi tiết và trạng thái snapshot', connection: 'backend', responseStatus: 200, response: snapshot },
  { id: 'snapshots_runs', method: 'GET', path: '/api/snapshots/{id}/runs/', group: 'Snapshots', summary: 'QC Run đã chạy trên snapshot, mới nhất trước', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [run] } },
] satisfies ApiEndpoint[];
