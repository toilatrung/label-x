import type { ApiEndpoint } from '../types';
import { issue } from '../examples';
import { CASES } from '@/lib/mock/escalations';
import type { components } from '@/lib/api/contract';

const decisionCases = CASES.rows.map((row, index) => ({
  id: [40, 34, 21, 17, 9][index], issue_id: 98 + index, outcome: index === 4 ? 'reject' : 'confirm',
  actor_user_id: 7, rule_id: row.c, correct_label: ['truck', 'car', 'truck', null, null][index],
  reason: `${row.b} · ${row.d}`, case_version: row.e, created_at: '2026-10-04T07:00:00Z',
} satisfies components['schemas']['DecisionCase']));

export const REVIEW_ENDPOINTS = [
  { id: 'queues_next', method: 'POST', path: '/api/queues/{name}/next/', group: 'Review', summary: 'Cấp lease cho frame kế tiếp', connection: 'backend', responseStatus: 200, response: { lease: { id: 61, expires_at: '2026-10-12T04:15:00Z' }, frame: { id: 3301, rank: 1, status: 'in_review' } } },
  { id: 'leases_renew', method: 'POST', path: '/api/leases/{id}/renew/', group: 'Review', summary: 'Gia hạn lease đang giữ', connection: 'backend', responseStatus: 200, response: { id: 61, frame_id: 3301, holder_user_id: 12, expires_at: '2026-10-12T04:30:00Z' } },
  { id: 'frames_issues', method: 'GET', path: '/api/frames/{id}/issues/', group: 'Review', summary: 'Issue và evidence của frame', connection: 'backend', responseStatus: 200, response: { frame: { id: 3301, review_state: 'in_review' }, engines: [{ engine: 'detector', status: 'checked' }], issues: [issue] } },
  { id: 'frames_complete', method: 'POST', path: '/api/frames/{id}/complete/', group: 'Review', summary: 'Hoàn tất review frame', connection: 'backend', responseStatus: 200, response: { id: 3301, status: 'reviewed', reviewed_at: '2026-10-12T04:22:00Z' } },
  { id: 'issues_create', method: 'POST', path: '/api/issues/', group: 'Review', summary: 'Tạo issue thủ công', connection: 'backend', responseStatus: 201, response: { ...issue, origin: 'reviewer', state: 'pending_review', anchor: { kind: 'manual_region', objects: [], bbox: { x1: 120, y1: 180, x2: 360, y2: 340 }, policy_version: 'pilot-1' } } },
  { id: 'issues_decide', method: 'POST', path: '/api/issues/{id}/decisions/', group: 'Review', summary: 'Lưu quyết định reviewer', connection: 'backend', responseStatus: 201, response: { id: 1102, issue_id: 902, action: 'confirm', actor_user_id: 12, revision: 'a91f3c', family: 'E2', severity: 'medium', created_at: '2026-10-12T04:20:00Z' } },
  { id: 'issues_retrieve', method: 'GET', path: '/api/issues/{id}/', group: 'Review', summary: 'Chi tiết và lịch sử issue', connection: 'backend', responseStatus: 200, response: issue },
  { id: 'escalations_list', method: 'GET', path: '/api/escalations/', group: 'Review', summary: 'Issue đang chờ phân xử', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ ...issue, state: 'escalated' }] } },
  { id: 'issues_adjudicate', method: 'POST', path: '/api/issues/{id}/adjudications/', group: 'Review', summary: 'Phân xử issue đã chuyển cấp', connection: 'backend', responseStatus: 201, response: { id: 81, issue_id: 902, outcome: 'confirm', actor_user_id: 7, rule_id: 'VEH-03', correct_label: 'truck', reason: 'Xe buýt mini chở hàng; đối chiếu Guideline v1.2.', case_version: 'v1', created_at: '2026-10-12T04:30:00Z' } },
  { id: 'decision_cases_list', method: 'GET', path: '/api/decision-cases/', group: 'Review', summary: 'Tra cứu Decision Case đã phân xử', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: decisionCases } },
  { id: 'decision_cases_retrieve', method: 'GET', path: '/api/decision-cases/{id}/', group: 'Review', summary: 'Chi tiết Decision Case theo phiên bản', connection: 'backend', responseStatus: 200, response: { ...decisionCases[0], history: [{ id: 40, case_version: 'Guideline v1.2', outcome: 'confirm', actor_user_id: 7, created_at: '2026-10-04T07:00:00Z' }] } },
  { id: 'queues_list', method: 'GET', path: '/api/queues/{name}/', group: 'Review', summary: 'Danh sách frame trong hàng đợi review', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, results: [
    { frame_id: 1234, external_id: 'BDD100K-0001234', name: 'Ảnh 001', rank: 1, score: 0.94, priority: 'high', family: 'Thiếu nhãn', scene: 'Đường phố', captured_at: '2024-06-10T10:24:00Z', review_state: 'unreviewed', holder: null, image_url: '/samples/frame-001.png' },
    { frame_id: 5678, external_id: 'BDD100K-0005678', name: 'Ảnh 002', rank: 2, score: 0.82, priority: 'normal', family: 'Hộp lệch', scene: 'Người đi bộ', captured_at: '2024-06-10T09:17:00Z', review_state: 'unreviewed', holder: null, image_url: '/samples/frame-002.png' },
    { frame_id: 9012, external_id: 'BDD100K-0009012', name: 'Ảnh 003', rank: 3, score: 0.76, priority: 'normal', family: 'Nhãn trùng', scene: 'Biển báo', captured_at: '2024-06-10T08:03:00Z', review_state: 'unreviewed', holder: null, image_url: '/samples/frame-003.png' },
  ] } },
  { id: 'frames_workspace', method: 'GET', path: '/api/frames/{id}/workspace/', group: 'Review', summary: 'Media và overlay đầy đủ của Review Workspace', connection: 'mock', origin: 'design', responseStatus: 200, response: { frame: { id: 3301, image_url: '/media/frames/3301.jpg', width: 1280, height: 720 }, revision: 'sha256:91c4…8fa2', annotations: [{ id: 117, label: 'car', bbox: [120, 180, 240, 160] }], predictions: [] } },
  { id: 'issues_similar_cases', method: 'GET', path: '/api/issues/{id}/similar-cases/', group: 'Review', summary: 'Case tương tự đã phân xử', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [{ decision_case_id: 81, issue_id: 744, similarity: 0.91, outcome: 'confirm', rule_id: 'GEO-001' }] } },
] satisfies ApiEndpoint[];
