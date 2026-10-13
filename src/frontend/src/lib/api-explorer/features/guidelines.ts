import type { ApiEndpoint } from '../types';

export const GUIDELINES_ENDPOINTS = [
  { id: 'guidelines_rules_list', method: 'GET', path: '/api/guidelines/rules/', group: 'Guidelines', summary: 'Tra cứu danh sách rule', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ rule_id: 'GEO-001', version: 'bdd100k-v1', section: 'Geometry', content: 'Bounding box phải nằm trong ảnh.' }] } },
  { id: 'guidelines_mappings_list', method: 'GET', path: '/api/guidelines/mappings/', group: 'Guidelines', summary: 'Mapping nhóm lỗi tới rule', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ family: 'geometry', label: 'car', rule_ids: ['GEO-001'] }] } },
  { id: 'guidelines_rules_retrieve', method: 'GET', path: '/api/guidelines/rules/{rule_id}/', group: 'Guidelines', summary: 'Chi tiết rule theo version', connection: 'backend', responseStatus: 200, response: { rule_id: 'GEO-001', version: 'bdd100k-v1', section: 'Geometry', content: 'Bounding box phải nằm trong ảnh.' } },
  { id: 'guideline_versions_list', method: 'GET', path: '/api/guidelines/versions/', group: 'Guidelines', summary: 'Danh sách phiên bản guideline và phạm vi áp dụng', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [
    { version: 'v1.2', taxonomy_version: 'v3', dataset_scope: 'Road Vision Urban v1.3 – v1.4', effective_at: '2026-08-20', status: 'active' },
    { version: 'v1.3', taxonomy_version: 'v3', dataset_scope: 'Chưa áp dụng', effective_at: null, status: 'pending_approval' },
    { version: 'v1.1', taxonomy_version: 'v2', dataset_scope: 'Road Vision Urban v1.1 – v1.2', effective_at: '2026-06-01', status: 'superseded' },
  ] } },
] satisfies ApiEndpoint[];
