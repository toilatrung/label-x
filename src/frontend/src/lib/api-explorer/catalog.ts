export type ApiConnection = 'backend' | 'mock';
export type ApiMethod = 'GET' | 'POST' | 'PATCH';
export type ApiOrigin = 'openapi' | 'design';

export interface ApiEndpoint {
  id: string;
  method: ApiMethod;
  path: string;
  group: string;
  summary: string;
  connection: ApiConnection;
  origin?: ApiOrigin;
  responseStatus: number;
  response: unknown;
}

const session = {
  user: { id: 7, username: 'qa.lead', full_name: 'QA Lead' },
  roles: [{ role: 'qa_lead', dataset_id: 12 }],
  identity_mapping: { status: 'mapped', cvat_user_id: 41 },
};

const snapshot = {
  id: 18, dataset_id: 12, status: 'locked', revision_hash: 'sha256:91c4…8fa2',
  guideline_version: 'bdd100k-v1', taxonomy_version: '2026.10', out_of_scope_shapes: 3,
};

const configVersion = {
  id: 4, name: 'BDD100K baseline', status: 'published', engines: { geometry: { enabled: true } },
  thresholds: { risk: 0.72 }, models: {}, created_by: 7, created_at: '2026-10-12T02:15:00Z',
  published_at: '2026-10-12T02:20:00Z',
};

const run = {
  id: 31, snapshot_id: 18, config_version_id: 4, status: 'completed', is_final: true,
  created_at: '2026-10-12T03:00:00Z',
};

const issue = {
  id: 902, frame_id: 3301, origin: 'engine', family: 'geometry', severity: 'major',
  status: 'confirmed', description: 'Bounding box vượt biên ảnh', review_decisions: [],
};

const rework = {
  id: 73, issue_id: 902, annotator_user_id: 28, status: 'fix_pending',
  original_revision: 'sha256:91c4…8fa2', submitted_revision: null,
  due_at: '2026-10-15T10:00:00Z', cvat_deep_link: 'http://localhost:8080/tasks/19/jobs/44',
};

const reference = {
  id: 9, snapshot_id: 18, gt_checksum: 'sha256:5f2a…c811', mapping_version: 'bdd100k-v1',
  matching_threshold: 0.5, minimum_area: 16, algorithm_version: 'match-v1', status: 'draft',
  created_by: 7, locked_by: null, locked_at: null,
};

const evaluation = {
  id: 14, status: 'queued', snapshot_id: 18, run_id: 31, reference_id: 9,
  score_version: 'score-v0', parameters: { minimum_sample: 100 }, metrics: null,
  leakage_check: 'not_checked', created_by: 7, created_at: '2026-10-12T04:00:00Z',
};

const waiver = {
  id: 6, run_id: 31, condition: 'coverage', reason: 'Detector bảo trì',
  evidence: 'OPS-241', expires_at: '2026-10-20T00:00:00Z', requested_by: 12,
  approved_by: null, status: 'pending',
};

/**
 * Contract inventory from docs/04-api/openapi.yaml.
 * `backend` means a Django URL and matching HTTP handler exist on develop-fe.
 * `mock` means the operation is contract-only; its example is intentionally marked as mock data.
 */
export const API_ENDPOINTS: ApiEndpoint[] = [
  { id: 'auth_csrf', method: 'GET', path: '/api/auth/csrf/', group: 'Auth', summary: 'Đặt cookie CSRF', connection: 'backend', responseStatus: 204, response: null },
  { id: 'auth_login', method: 'POST', path: '/api/auth/login/', group: 'Auth', summary: 'Đăng nhập và tạo session', connection: 'backend', responseStatus: 200, response: session },
  { id: 'auth_logout', method: 'POST', path: '/api/auth/logout/', group: 'Auth', summary: 'Đăng xuất và huỷ session', connection: 'backend', responseStatus: 204, response: null },
  { id: 'auth_session', method: 'GET', path: '/api/auth/session/', group: 'Auth', summary: 'Lấy phiên đăng nhập hiện tại', connection: 'backend', responseStatus: 200, response: session },
  { id: 'auth_workflow_permissions', method: 'GET', path: '/api/auth/workflow-permissions/', group: 'Auth', summary: 'Ma trận phân quyền workflow', connection: 'backend', responseStatus: 200, response: { roles: ['annotator', 'reviewer', 'qa_lead', 'qc_admin', 'super_admin'], rules: { anti_self_review: true, separation_of_duties: true } } },

  { id: 'datasets_list', method: 'GET', path: '/api/datasets/', group: 'Datasets', summary: 'Dataset trong scope người gọi', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ id: 12, name: 'BDD100K Pilot', cvat_project_id: 5, guideline_version: 'bdd100k-v1' }] } },
  { id: 'datasets_tasks', method: 'GET', path: '/api/datasets/{id}/tasks/', group: 'Datasets', summary: 'Cây task và job CVAT', connection: 'backend', responseStatus: 200, response: [{ id: 19, name: 'pilot-daytime', jobs: [{ id: 44, assignee_id: 28, frame_count: 240 }] }] },

  { id: 'snapshots_list', method: 'GET', path: '/api/snapshots/', group: 'Snapshots', summary: 'Danh sách snapshot theo dataset', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [snapshot] } },
  { id: 'snapshots_create', method: 'POST', path: '/api/snapshots/', group: 'Snapshots', summary: 'Tạo snapshot bất biến', connection: 'backend', responseStatus: 202, response: { id: 18, status: 'pending', status_url: '/api/snapshots/18/' } },
  { id: 'snapshots_retrieve', method: 'GET', path: '/api/snapshots/{id}/', group: 'Snapshots', summary: 'Chi tiết và trạng thái snapshot', connection: 'backend', responseStatus: 200, response: snapshot },

  { id: 'config_versions_list', method: 'GET', path: '/api/config-versions/', group: 'Configuration', summary: 'Danh sách phiên bản cấu hình', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [configVersion] } },
  { id: 'config_versions_create', method: 'POST', path: '/api/config-versions/', group: 'Configuration', summary: 'Tạo phiên bản cấu hình nháp', connection: 'backend', responseStatus: 201, response: { ...configVersion, status: 'draft', published_at: null } },
  { id: 'config_versions_publish', method: 'POST', path: '/api/config-versions/{id}/publish/', group: 'Configuration', summary: 'Publish phiên bản cấu hình', connection: 'backend', responseStatus: 200, response: configVersion },

  { id: 'runs_list', method: 'GET', path: '/api/runs/', group: 'Runs', summary: 'Lịch sử QC Run', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [run] } },
  { id: 'runs_create', method: 'POST', path: '/api/runs/', group: 'Runs', summary: 'Tạo QC Run', connection: 'backend', responseStatus: 201, response: { ...run, status: 'queued', is_final: false } },
  { id: 'runs_retrieve', method: 'GET', path: '/api/runs/{id}/', group: 'Runs', summary: 'Chi tiết và trạng thái run', connection: 'backend', responseStatus: 200, response: run },
  { id: 'runs_cancel', method: 'POST', path: '/api/runs/{id}/cancel/', group: 'Runs', summary: 'Huỷ run đang chạy', connection: 'backend', responseStatus: 200, response: { ...run, status: 'cancelled', is_final: false } },
  { id: 'runs_retry_failed', method: 'POST', path: '/api/runs/{id}/retry-failed/', group: 'Runs', summary: 'Chạy lại các shard bị lỗi', connection: 'backend', responseStatus: 202, response: { ...run, status: 'running', is_final: false } },
  { id: 'runs_ledger', method: 'GET', path: '/api/runs/{id}/ledger/', group: 'Runs', summary: 'Coverage ledger theo engine', connection: 'backend', responseStatus: 200, response: [{ engine: 'geometry', status: 'succeeded', total_units: 240, checked_units: 240, failed_units: 0 }] },
  { id: 'runs_shards', method: 'GET', path: '/api/runs/{id}/shards/', group: 'Runs', summary: 'Trạng thái các shard', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ id: 88, engine: 'geometry', status: 'succeeded', attempt: 1 }] } },
  { id: 'runs_candidates', method: 'GET', path: '/api/runs/{id}/candidates/', group: 'Runs', summary: 'Candidate và evidence của run', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ id: 501, frame_id: 3301, engine: 'geometry', family: 'out_of_bounds', score: 0.94, evidence: { object_id: 117 } }] } },
  { id: 'runs_ranking', method: 'GET', path: '/api/runs/{id}/ranking/', group: 'Runs', summary: 'Ranking frame theo risk score', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, source: 'risk', content_hash: 'sha256:bb21…401a', ranking_hash: 'sha256:119e…73af', results: [{ frame_id: 3301, rank: 1, score: 0.94 }] } },
  { id: 'internal_metrics', method: 'GET', path: '/internal/metrics/', group: 'Operations', summary: 'Metrics vận hành dạng Prometheus', connection: 'backend', responseStatus: 200, response: 'labelx_run_shards_total{status="succeeded"} 240' },

  { id: 'guidelines_rules_list', method: 'GET', path: '/api/guidelines/rules/', group: 'Guidelines', summary: 'Tra cứu danh sách rule', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ rule_id: 'GEO-001', version: 'bdd100k-v1', section: 'Geometry', content: 'Bounding box phải nằm trong ảnh.' }] } },
  { id: 'guidelines_mappings_list', method: 'GET', path: '/api/guidelines/mappings/', group: 'Guidelines', summary: 'Mapping nhóm lỗi tới rule', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ family: 'geometry', label: 'car', rule_ids: ['GEO-001'] }] } },
  { id: 'guidelines_rules_retrieve', method: 'GET', path: '/api/guidelines/rules/{rule_id}/', group: 'Guidelines', summary: 'Chi tiết rule theo version', connection: 'backend', responseStatus: 200, response: { rule_id: 'GEO-001', version: 'bdd100k-v1', section: 'Geometry', content: 'Bounding box phải nằm trong ảnh.' } },

  { id: 'queues_next', method: 'POST', path: '/api/queues/{name}/next/', group: 'Review', summary: 'Cấp lease cho frame kế tiếp', connection: 'backend', responseStatus: 200, response: { lease: { id: 61, expires_at: '2026-10-12T04:15:00Z' }, frame: { id: 3301, rank: 1, status: 'in_review' } } },
  { id: 'leases_renew', method: 'POST', path: '/api/leases/{id}/renew/', group: 'Review', summary: 'Gia hạn lease đang giữ', connection: 'backend', responseStatus: 200, response: { id: 61, frame_id: 3301, holder_user_id: 12, expires_at: '2026-10-12T04:30:00Z' } },
  { id: 'frames_issues', method: 'GET', path: '/api/frames/{id}/issues/', group: 'Review', summary: 'Issue và evidence của frame', connection: 'backend', responseStatus: 200, response: { frame: { id: 3301, status: 'in_review' }, engines: [{ engine: 'geometry', status: 'succeeded' }], issues: [issue] } },
  { id: 'frames_complete', method: 'POST', path: '/api/frames/{id}/complete/', group: 'Review', summary: 'Hoàn tất review frame', connection: 'backend', responseStatus: 200, response: { id: 3301, status: 'reviewed', reviewed_at: '2026-10-12T04:22:00Z' } },
  { id: 'issues_create', method: 'POST', path: '/api/issues/', group: 'Review', summary: 'Tạo issue thủ công', connection: 'backend', responseStatus: 201, response: { ...issue, origin: 'reviewer', status: 'open' } },
  { id: 'issues_decide', method: 'POST', path: '/api/issues/{id}/decisions/', group: 'Review', summary: 'Lưu quyết định reviewer', connection: 'backend', responseStatus: 201, response: { id: 1102, issue_id: 902, action: 'confirm', actor_user_id: 12, revision: 'sha256:91c4…8fa2', family: 'geometry', severity: 'major', created_at: '2026-10-12T04:20:00Z' } },
  { id: 'issues_retrieve', method: 'GET', path: '/api/issues/{id}/', group: 'Review', summary: 'Chi tiết và lịch sử issue', connection: 'backend', responseStatus: 200, response: issue },
  { id: 'escalations_list', method: 'GET', path: '/api/escalations/', group: 'Review', summary: 'Issue đang chờ phân xử', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [{ ...issue, status: 'escalated' }] } },
  { id: 'issues_adjudicate', method: 'POST', path: '/api/issues/{id}/adjudications/', group: 'Review', summary: 'Phân xử issue đã chuyển cấp', connection: 'backend', responseStatus: 201, response: { id: 81, issue_id: 902, outcome: 'confirm', actor_user_id: 7, rule_id: 'GEO-001', reason: 'Evidence xác nhận lỗi', case_version: 'v1', created_at: '2026-10-12T04:30:00Z' } },

  { id: 'rework_create', method: 'POST', path: '/api/rework/', group: 'Rework', summary: 'Tạo yêu cầu sửa', connection: 'backend', responseStatus: 201, response: rework },
  { id: 'rework_submitted', method: 'POST', path: '/api/rework/{id}/submitted/', group: 'Rework', summary: 'Ghi nhận annotator đã sửa', connection: 'backend', responseStatus: 202, response: { ...rework, status: 'recheck_pending', submitted_revision: 'sha256:3aa7…992e' } },
  { id: 'rework_verify', method: 'POST', path: '/api/rework/{id}/verify/', group: 'Rework', summary: 'Xác minh kết quả sửa lỗi', connection: 'backend', responseStatus: 200, response: { ...rework, status: 'resolved', submitted_revision: 'sha256:3aa7…992e' } },

  { id: 'references_create', method: 'POST', path: '/api/references/', group: 'Evaluation', summary: 'Tạo phiên reference và nhập GT', connection: 'mock', responseStatus: 201, response: reference },
  { id: 'references_lock', method: 'POST', path: '/api/references/{id}/lock/', group: 'Evaluation', summary: 'Khoá reference và provenance', connection: 'mock', responseStatus: 200, response: { ...reference, status: 'locked', locked_by: 15, locked_at: '2026-10-12T05:00:00Z' } },
  { id: 'effort_events_create', method: 'POST', path: '/api/effort-events/', group: 'Evaluation', summary: 'Ghi batch effort event', connection: 'backend', responseStatus: 202, response: { accepted: 3, duplicates: 0 } },
  { id: 'evaluations_create', method: 'POST', path: '/api/evaluations/', group: 'Evaluation', summary: 'Chạy đánh giá KPI', connection: 'mock', responseStatus: 202, response: evaluation },
  { id: 'evaluations_retrieve', method: 'GET', path: '/api/evaluations/{id}/', group: 'Evaluation', summary: 'Kết quả KPI và provenance', connection: 'mock', responseStatus: 200, response: { ...evaluation, status: 'completed', leakage_check: 'passed', metrics: { 'KPI-1': { status: 'computed', value: 0.91, sample_size: 220, denominator: 240, method: 'score-v0' } } } },

  { id: 'runs_gate', method: 'GET', path: '/api/runs/{id}/gate/', group: 'Gate', summary: 'Kết quả từng điều kiện gate', connection: 'mock', responseStatus: 200, response: { run_id: 31, source_run_id: 31, source_reason: 'final_run', status: 'failed', conditions: [{ name: 'coverage', status: 'failed', observed: 0.92, threshold: 0.95 }] } },
  { id: 'waivers_create', method: 'POST', path: '/api/waivers/', group: 'Gate', summary: 'Đề nghị waiver điều kiện gate', connection: 'mock', responseStatus: 201, response: waiver },
  { id: 'waivers_approve', method: 'POST', path: '/api/waivers/{id}/approve/', group: 'Gate', summary: 'Duyệt hoặc từ chối waiver', connection: 'mock', responseStatus: 200, response: { ...waiver, approved_by: 7, status: 'approved' } },
  { id: 'reports_retrieve', method: 'GET', path: '/api/reports/{id}/', group: 'Reports', summary: 'Xuất báo cáo hiệu quả', connection: 'mock', responseStatus: 200, response: { id: 21, input_snapshot_id: 18, reference_id: 9, source_run_id: 31, source_reason: 'final_run', score_version: 'score-v0', metrics: { 'KPI-1': { value: 0.91, status: 'computed' } }, risk_queue: { reviewed: 120 }, random_queue: { reviewed: 100 }, engine_coverage: [] } },

  // Design-driven operations. These are intentionally kept separate from the approved OpenAPI baseline.
  { id: 'decision_cases_list', method: 'GET', path: '/api/decision-cases/', group: 'Review', summary: 'Tra cứu Decision Case đã phân xử', connection: 'backend', origin: 'design', responseStatus: 200, response: [{ id: 81, issue_id: 902, outcome: 'confirm', actor_user_id: 7, rule_id: 'GEO-001', reason: 'Evidence xác nhận lỗi', case_version: 'v1', created_at: '2026-10-12T04:30:00Z' }] },
  { id: 'decision_cases_retrieve', method: 'GET', path: '/api/decision-cases/{id}/', group: 'Review', summary: 'Chi tiết Decision Case theo phiên bản', connection: 'backend', origin: 'design', responseStatus: 200, response: { id: 81, issue_id: 902, outcome: 'confirm', actor_user_id: 7, rule_id: 'GEO-001', reason: 'Evidence xác nhận lỗi', case_version: 'v1', created_at: '2026-10-12T04:30:00Z' } },
  { id: 'queues_list', method: 'GET', path: '/api/queues/{name}/', group: 'Review', summary: 'Danh sách frame trong hàng đợi review', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, results: [{ frame_id: 3301, rank: 1, score: 0.94, priority: 'high', family: 'geometry', review_state: 'pending', holder: null }] } },
  { id: 'frames_workspace', method: 'GET', path: '/api/frames/{id}/workspace/', group: 'Review', summary: 'Media và overlay đầy đủ của Review Workspace', connection: 'mock', origin: 'design', responseStatus: 200, response: { frame: { id: 3301, image_url: '/media/frames/3301.jpg', width: 1280, height: 720 }, revision: 'sha256:91c4…8fa2', annotations: [{ id: 117, label: 'car', bbox: [120, 180, 240, 160] }], predictions: [] } },
  { id: 'rework_list', method: 'GET', path: '/api/rework/', group: 'Rework', summary: 'Danh sách yêu cầu sửa theo scope', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, counts: { fix_pending: 12, recheck_pending: 4, resolved: 74 }, results: [rework] } },
  { id: 'rework_retrieve', method: 'GET', path: '/api/rework/{id}/', group: 'Rework', summary: 'Chi tiết yêu cầu sửa', connection: 'mock', origin: 'design', responseStatus: 200, response: rework },
  { id: 'runs_lineage', method: 'GET', path: '/api/runs/{id}/lineage/', group: 'Runs', summary: 'Lineage re-check và nguồn run cuối', connection: 'mock', origin: 'design', responseStatus: 200, response: { run_id: 34, origin_run_id: 31, selected_final_run_id: 34, reason: 'rework_verified', chain: [{ run_id: 31, kind: 'origin' }, { run_id: 34, kind: 'recheck' }] } },
  { id: 'review_policies_retrieve', method: 'GET', path: '/api/config/review-policies/', group: 'Configuration', summary: 'Chính sách lease và effort đã duyệt', connection: 'mock', origin: 'design', responseStatus: 200, response: { version: 'review-policy-v1', lease_seconds: 900, renew_before_seconds: 180, idle_timeout_seconds: 120, effective_at: '2026-10-12T00:00:00Z' } },
  { id: 'issues_similar_cases', method: 'GET', path: '/api/issues/{id}/similar-cases/', group: 'Review', summary: 'Case tương tự đã phân xử', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [{ decision_case_id: 81, issue_id: 744, similarity: 0.91, outcome: 'confirm', rule_id: 'GEO-001' }] } },

  { id: 'guideline_gaps_list', method: 'GET', path: '/api/guideline-gaps/', group: 'Escalations', summary: 'Danh sách khoảng trống guideline', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, results: [{ id: 12, issue_id: 902, status: 'open', title: 'Phân biệt bus và truck', proposed_rule: 'VEH-08' }] } },
  { id: 'guideline_gaps_create', method: 'POST', path: '/api/guideline-gaps/', group: 'Escalations', summary: 'Tạo Guideline Gap từ phân xử', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 12, issue_id: 902, status: 'open', title: 'Phân biệt bus và truck', proposed_rule: 'VEH-08', created_by: 7 } },

  { id: 'workflow_rule_update', method: 'PATCH', path: '/api/auth/workflow-permissions/rules/{rule}/', group: 'Configuration', summary: 'Bật hoặc tắt quy tắc workflow', connection: 'mock', origin: 'design', responseStatus: 200, response: { rule: 'anti_self_review', enforced: true, updated_by: 7, updated_at: '2026-10-12T06:00:00Z' } },
  { id: 'models_list', method: 'GET', path: '/api/models/', group: 'Configuration', summary: 'Danh sách model và artifact version', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [{ id: 5, name: 'Detector', version: 'v2.3', role: 'object_detection', taxonomy_version: 'v3', confidence_threshold: 0.6, status: 'active' }] } },
  { id: 'models_update', method: 'PATCH', path: '/api/models/{id}/', group: 'Configuration', summary: 'Cập nhật cấu hình model', connection: 'mock', origin: 'design', responseStatus: 200, response: { id: 5, name: 'Detector', version: 'v2.3', confidence_threshold: 0.65, status: 'active', updated_by: 7 } },
  { id: 'guideline_versions_list', method: 'GET', path: '/api/guidelines/versions/', group: 'Guidelines', summary: 'Danh sách phiên bản guideline và phạm vi áp dụng', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [{ version: 'v1.2', taxonomy_version: 'v3', dataset_ids: [12], effective_at: '2026-08-20', status: 'active' }] } },
  { id: 'config_version_rules', method: 'GET', path: '/api/config-versions/{id}/rules/', group: 'Configuration', summary: 'Rule, ngưỡng gate và chính sách lấy mẫu', connection: 'mock', origin: 'design', responseStatus: 200, response: { config_version_id: 4, rules: [{ id: 'G-014', enabled: true, severity: 'major', minimum_area: 24 }], gate_thresholds: { coverage: 0.95, agreement: 0.9 }, sampling: { random_rate: 0.08, risk_rate: 0.15 } } },

  { id: 'evaluation_performance', method: 'GET', path: '/api/evaluation/performance/', group: 'Evaluation', summary: 'Tổng hợp hiệu năng theo luồng lấy mẫu', connection: 'mock', origin: 'design', responseStatus: 200, response: { run_id: 31, benchmark_id: 9, metrics: { reviewer_agreement: 0.941, candidate_precision: 0.875, residual_error_rate: 0.04, benchmark_coverage: 0.76 }, streams: [{ name: 'random', sample_size: 100, confirmed_errors: 4 }] } },
  { id: 'benchmarks_list', method: 'GET', path: '/api/benchmarks/', group: 'Benchmark', summary: 'Danh sách phiên bản Ground Truth Benchmark', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [{ id: 9, name: 'Benchmark v1.2', snapshot_id: 18, frame_count: 200, status: 'locked', locked_at: '2026-10-10T08:00:00Z' }] } },
  { id: 'benchmarks_create', method: 'POST', path: '/api/benchmarks/', group: 'Benchmark', summary: 'Tạo phiên bản benchmark', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 10, name: 'Benchmark v1.3', snapshot_id: 18, frame_count: 0, status: 'draft', created_by: 7 } },
  { id: 'benchmarks_import_cvat', method: 'POST', path: '/api/benchmarks/import-cvat/', group: 'Benchmark', summary: 'Nhập Ground Truth từ CVAT', connection: 'mock', origin: 'design', responseStatus: 202, response: { import_id: 22, benchmark_id: 10, cvat_task_ids: [19], status: 'queued' } },
  { id: 'audit_samples_list', method: 'GET', path: '/api/audit-samples/', group: 'Audit', summary: 'Danh sách mẫu audit theo random hoặc risk', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, stream: 'random', results: [{ id: 41, run_id: 31, frame_id: 3301, status: 'pending', seed: 104729 }] } },
  { id: 'audit_samples_create', method: 'POST', path: '/api/audit-samples/', group: 'Audit', summary: 'Tạo bộ mẫu audit mới', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 42, run_id: 31, stream: 'random', requested_size: 100, seed: 104729, status: 'ready' } },
  { id: 'calibration_reviewers', method: 'GET', path: '/api/calibration/reviewers/', group: 'Calibration', summary: 'Kết quả hiệu chỉnh reviewer', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [{ user_id: 12, full_name: 'Bình Hồ', completed: 40, assigned: 45, agreement: 0.941, status: 'in_progress' }] } },
  { id: 'calibration_models', method: 'GET', path: '/api/calibration/models/', group: 'Calibration', summary: 'Kết quả hiệu chỉnh model và engine', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [{ model_id: 5, name: 'Detector v2.3', precision: 0.875, recall: 0.81, status: 'completed' }] } },
  { id: 'calibration_assignments_create', method: 'POST', path: '/api/calibration/assignments/', group: 'Calibration', summary: 'Giao bài hiệu chỉnh', connection: 'mock', origin: 'design', responseStatus: 201, response: { id: 66, benchmark_id: 9, assignee_user_id: 12, frame_count: 45, due_at: '2026-10-18T00:00:00Z', status: 'assigned' } },

  { id: 'releases_list', method: 'GET', path: '/api/releases/', group: 'Releases', summary: 'Danh sách các lần phát hành', connection: 'mock', origin: 'design', responseStatus: 200, response: { next: null, previous: null, results: [{ id: 13, version: 'v1.3', dataset_id: 12, snapshot_id: 18, run_id: 31, status: 'released', released_at: '2026-10-11T09:00:00Z' }] } },
  { id: 'release_manifest', method: 'GET', path: '/api/releases/{id}/manifest/', group: 'Releases', summary: 'Manifest phát hành có provenance', connection: 'mock', origin: 'design', responseStatus: 200, response: { release_id: 13, version: 'v1.3', snapshot: { id: 18, revision: 'sha256:91c4…8fa2' }, run_id: 31, config_version_id: 4, guideline_version: 'bdd100k-v1', artifacts: [] } },
  { id: 'release_approve', method: 'POST', path: '/api/releases/{id}/approve/', group: 'Releases', summary: 'Phê duyệt phát hành', connection: 'mock', origin: 'design', responseStatus: 200, response: { id: 13, version: 'v1.3', status: 'approved', approved_by: 7, approved_at: '2026-10-12T07:00:00Z' } },
  { id: 'run_report', method: 'GET', path: '/api/runs/{id}/report/', group: 'Reports', summary: 'Báo cáo chất lượng theo QC Run', connection: 'mock', origin: 'design', responseStatus: 200, response: { run_id: 31, snapshot_id: 18, metrics: { coverage: 0.924, open_critical_issues: 3, rework_completion: 0.86 }, confirmed_errors: { label: 48, geometry: 33, missing_object: 25 } } },
  { id: 'run_report_export', method: 'POST', path: '/api/runs/{id}/report/export/', group: 'Reports', summary: 'Xuất file báo cáo theo định dạng', connection: 'mock', origin: 'design', responseStatus: 202, response: { export_id: 55, run_id: 31, format: 'pdf', status: 'queued', download_url: null } },
];
