import type { ApiEndpoint } from '../types';
import { run } from '../examples';

export const RUNS_ENDPOINTS = [
  { id: 'runs_list', method: 'GET', path: '/api/runs/', group: 'Runs', summary: 'Lịch sử QC Run', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [run] } },
  { id: 'runs_create', method: 'POST', path: '/api/runs/', group: 'Runs', summary: 'Tạo QC Run', connection: 'backend', responseStatus: 201, response: { ...run, status: 'queued', is_final: false } },
  { id: 'runs_retrieve', method: 'GET', path: '/api/runs/{id}/', group: 'Runs', summary: 'Chi tiết và trạng thái run', connection: 'backend', responseStatus: 200, response: run },
  { id: 'runs_cancel', method: 'POST', path: '/api/runs/{id}/cancel/', group: 'Runs', summary: 'Huỷ run đang chạy', connection: 'backend', responseStatus: 200, response: { ...run, status: 'cancelled', is_final: false } },
  { id: 'runs_retry_failed', method: 'POST', path: '/api/runs/{id}/retry-failed/', group: 'Runs', summary: 'Chạy lại các shard bị lỗi', connection: 'backend', responseStatus: 202, response: { ...run, status: 'running', is_final: false } },
  { id: 'runs_ledger', method: 'GET', path: '/api/runs/{id}/ledger/', group: 'Runs', summary: 'Coverage ledger theo engine', connection: 'backend', responseStatus: 200, response: [{ engine: 'geometry', status: 'succeeded', total_units: 240, checked_units: 240, failed_units: 0 }] },
  { id: 'runs_shards', method: 'GET', path: '/api/runs/{id}/shards/', group: 'Runs', summary: 'Trạng thái các shard', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ id: 88, engine: 'geometry', status: 'succeeded', attempt: 1 }] } },
  { id: 'runs_candidates', method: 'GET', path: '/api/runs/{id}/candidates/', group: 'Runs', summary: 'Candidate và evidence của run', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ id: 501, frame_id: 3301, engine: 'geometry', family: 'out_of_bounds', score: 0.94, evidence: { object_id: 117 } }] } },
  { id: 'runs_ranking', method: 'GET', path: '/api/runs/{id}/ranking/', group: 'Runs', summary: 'Ranking frame theo risk score', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, source: 'risk', content_hash: 'sha256:bb21…401a', ranking_hash: 'sha256:119e…73af', results: [{ frame_id: 3301, rank: 1, score: 0.94 }] } },
  { id: 'runs_lineage', method: 'GET', path: '/api/runs/{id}/lineage/', group: 'Runs', summary: 'Lineage re-check và nguồn run cuối', connection: 'mock', origin: 'design', responseStatus: 200, response: { run_id: 34, origin_run_id: 31, selected_final_run_id: 34, reason: 'rework_verified', chain: [{ run_id: 31, kind: 'origin' }, { run_id: 34, kind: 'recheck' }] } },
] satisfies ApiEndpoint[];
