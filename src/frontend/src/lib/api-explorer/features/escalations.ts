import type { ApiEndpoint } from '../types';

export const ESCALATIONS_ENDPOINTS = [
  { id: 'guideline_gaps_list', method: 'GET', path: '/api/guideline-gaps/', group: 'Escalations', summary: 'Danh sách khoảng trống guideline', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, results: [{ id: 12, issue_id: 902, status: 'open', title: 'Phân biệt bus và truck', proposed_rule: 'VEH-08' }] } },
  { id: 'guideline_gaps_create', method: 'POST', path: '/api/guideline-gaps/', group: 'Escalations', summary: 'Tạo Guideline Gap từ phân xử', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 12, issue_id: 902, status: 'open', title: 'Phân biệt bus và truck', proposed_rule: 'VEH-08', created_by: 7 } },
] satisfies ApiEndpoint[];
