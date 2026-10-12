import type { ApiEndpoint } from '../types';
import { waiver } from '../examples';

export const GATE_ENDPOINTS = [
  { id: 'runs_gate', method: 'GET', path: '/api/runs/{id}/gate/', group: 'Gate', summary: 'Kết quả từng điều kiện gate', connection: 'mock', responseStatus: 200, response: { run_id: 31, source_run_id: 31, source_reason: 'final_run', status: 'failed', conditions: [{ name: 'coverage', status: 'failed', observed: 0.92, threshold: 0.95 }] } },
  { id: 'waivers_create', method: 'POST', path: '/api/waivers/', group: 'Gate', summary: 'Đề nghị waiver điều kiện gate', connection: 'mock', responseStatus: 201, response: waiver },
  { id: 'waivers_approve', method: 'POST', path: '/api/waivers/{id}/approve/', group: 'Gate', summary: 'Duyệt hoặc từ chối waiver', connection: 'mock', responseStatus: 200, response: { ...waiver, approved_by: 7, status: 'approved' } },
] satisfies ApiEndpoint[];
