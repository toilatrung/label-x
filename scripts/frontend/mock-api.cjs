#!/usr/bin/env node
/*
 * API giả lập CHỈ để dev/kiểm tra giao diện LabelX (không dùng cho production, không nằm trong bundle).
 *
 * Next ở chế độ mock auth luôn gọi API cùng origin với giao diện (src/lib/auth/config.ts) và tắt
 * rewrite /api, nên server này đứng TRƯỚC Next trên cổng công khai:
 *   - /api/auth/* (csrf, login, logout, session, mock-users): chuyển nguyên cho Next (đã có mock auth).
 *   - Các /api/* còn lại: trả JSON giả đúng hình dạng docs/04-api/openapi.yaml.
 *   - Mọi đường dẫn khác (trang, /_next, HMR websocket): chuyển cho Next dev.
 * Dữ liệu theo bộ số liệu chuẩn: 12,500 frame (3 task: 600 + 6,000 + 5,900), coverage 92.4%,
 * 384 candidate, 126 lỗi đã xác nhận. Ghi (POST) trả thành công giả, không lưu trạng thái.
 *
 *   node mock-api.cjs --target http://127.0.0.1:3101 [--port 3100] [--host 127.0.0.1]
 */
'use strict';
const http = require('node:http');
const net = require('node:net');

function arg(name, fallback) {
  const i = process.argv.indexOf(name);
  return i > -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
if (process.argv.includes('-h') || process.argv.includes('--help')) {
  console.log(require('node:fs').readFileSync(__filename, 'utf8').split('*/')[0].replace(/^#!.*\n/, '').replace(/^\/\*\n?/, '').replace(/^ \* ?/gm, '').trim());
  process.exit(0);
}
const PORT = Number(arg('--port', process.env.MOCK_API_PORT || 3100));
const HOST = arg('--host', '127.0.0.1');
const TARGET = new URL(arg('--target', process.env.MOCK_API_TARGET || 'http://127.0.0.1:3101'));

// ---------------------------------------------------------------- dữ liệu
const T0 = '2026-10-08T07:30:00Z';
const hash = (seed) => seed.repeat(8).slice(0, 64);
const FRAMES = 12500;

const datasets = [
  { id: 1, name: 'Urban Driving 2026Q3', cvat_project_id: 7, taxonomy_version: 'tax-3.2', guideline_version: 'gl-2.1' },
  { id: 2, name: 'Highway Night 2026Q3', cvat_project_id: 9, taxonomy_version: 'tax-3.2', guideline_version: 'gl-2.1' },
];

const tasksByDataset = {
  1: [
    { cvat_task_id: 118, name: 'Urban day', jobs: [[501, 101, 200], [502, 102, 200], [503, null, 200]] },
    { cvat_task_id: 119, name: 'Urban night', jobs: [[504, 103, 3000], [505, 104, 3000]] },
    { cvat_task_id: 120, name: 'Urban rain', jobs: [[506, 105, 2900], [507, 101, 3000]] },
  ],
  2: [{ cvat_task_id: 130, name: 'Highway night A', jobs: [[510, 102, 1500], [511, null, 1500]] }],
};
const tasks = (id) => (tasksByDataset[id] || []).map((t) => ({
  cvat_task_id: t.cvat_task_id, name: t.name,
  jobs: t.jobs.map(([cvat_job_id, assignee_cvat_user_id, frame_count]) => (
    { cvat_job_id, assignee_cvat_user_id, frame_count, updated_date: T0 })),
}));

function snapshot(id, dataset_id, status, parent, extra = {}) {
  const jobs = (tasksByDataset[dataset_id] || []).flatMap((t) => t.jobs.map(([cvat_job_id, assignee]) => ({
    cvat_job_id, cvat_task_id: t.cvat_task_id, job_hash: hash(String(cvat_job_id)), assignee_user_id: assignee,
    cvat_url: `http://localhost:8080/tasks/${t.cvat_task_id}/jobs/${cvat_job_id}`,
    frames: [0, 1, 2].map((n) => ({ frame_index: n, file_name: `frame_${String(n).padStart(6, '0')}.jpg`, width: 1920, height: 1080,
      cvat_url: `http://localhost:8080/tasks/${t.cvat_task_id}/jobs/${cvat_job_id}?frame=${n}` })),
  })));
  return { id, dataset_id, status, failure_reason: null, revision_hash: status === 'locked' ? hash('ab' + id) : null,
    parent_snapshot_id: parent, jobs, taxonomy_version: 'tax-3.2', guideline_version: 'gl-2.1', out_of_scope_shapes: 12,
    drift_jobs: [], created_by: 2, created_at: T0, locked_at: status === 'locked' ? '2026-10-08T07:42:00Z' : null, ...extra };
}
const snapshots = [
  snapshot(14, 1, 'locked', 13),
  snapshot(13, 1, 'locked', 12),
  snapshot(12, 1, 'failed', null, { failure_reason: 'drift_detected', drift_jobs: [503] }),
  snapshot(15, 2, 'locked', null),
];

const engineParams = {
  schema: { taxonomy_version: 'tax-3.2', required_attributes: true },
  geometry: { tolerance_px: 2, min_area_px: 16 },
  duplicate: { iou_threshold: 0.9, same_class: true },
  detector: { model_version: 'det-v4.1', confidence_threshold: 0.6 },
  metric: { benchmark: 'bench-2026Q3', ground_truth: 'gt-2026Q3' },
  vlm: { model_version: 'vlm-0.9', max_candidates: 200 },
};
const engineCfg = (enabled = true) => Object.fromEntries(Object.entries(engineParams).map(([k, params]) =>
  [k, { engine: k, version: '1.0.0', enabled: enabled || k !== 'vlm', params }]));
const configs = [
  { id: 8, name: 'cfg-2026.10.1', status: 'published', engines: engineCfg(), thresholds: { coverage_min: 0.95 }, models: {}, created_by: 3, created_at: T0, published_at: '2026-10-08T08:00:00Z' },
  { id: 7, name: 'cfg-2026.09.2', status: 'published', engines: engineCfg(false), thresholds: { coverage_min: 0.9 }, models: {}, created_by: 3, created_at: '2026-09-20T07:00:00Z', published_at: '2026-09-20T08:00:00Z' },
  { id: 9, name: 'cfg-2026.10.2-draft', status: 'draft', engines: engineCfg(), thresholds: { coverage_min: 0.95 }, models: {}, created_by: 3, created_at: '2026-10-10T07:00:00Z', published_at: null },
];

const ENGINES = ['schema', 'geometry', 'duplicate', 'detector', 'metric', 'vlm'];
function run(id, snapshot_id, status, config_version_id = 8) {
  const done = status === 'completed' || status === 'partial';
  return { id, snapshot_id, config_version_id, seed: 20261008 + id, status, is_final: done, origin_run_id: null,
    score_version: 'score-1.2', model_artifact: { name: 'det', version: 'v4.1', checksum: hash('cd') },
    engines: ENGINES.map((engine) => ({ engine,
      status: status === 'running' ? 'running' : engine === 'vlm' ? 'not_checked' : engine === 'detector' && status === 'partial' ? 'partial' : 'checked',
      reason: engine === 'vlm' ? 'disabled' : null, failed_units: engine === 'detector' && status === 'partial' ? 7 : 0 })),
    created_by: 2, created_at: T0, finished_at: done ? '2026-10-08T09:10:00Z' : null };
}
const runs = [run(12, 14, 'completed'), run(13, 13, 'partial'), run(14, 14, 'running')];

const ledger = ENGINES.map((engine) => {
  const vlm = engine === 'vlm';
  const eligible = vlm ? 0 : engine === 'metric' ? 11800 : FRAMES;
  const failed = engine === 'detector' ? 7 : 0;
  const completed = vlm ? 0 : engine === 'detector' ? Math.round(FRAMES * 0.924) : eligible - failed;
  return { engine, status: vlm ? 'not_checked' : engine === 'detector' ? 'partial' : 'checked', required: engine !== 'vlm',
    unit: engine === 'geometry' || engine === 'duplicate' ? 'shape' : 'frame', total: FRAMES, eligible, excluded: FRAMES - eligible,
    applicability_version: 'app-1.0', completed, failed, pending: 0, not_checked: eligible - completed - failed,
    not_checked_reasons: vlm ? { disabled: FRAMES } : engine === 'metric' ? { not_applicable: 700 } : {},
    coverage: vlm ? null : Math.round((completed / eligible) * 1000) / 1000 };
});
const shards = Array.from({ length: 12 }, (_, i) => ({ id: 100 + i, engine: ENGINES[i % 5], shard_key: `shard-${i}`, shard_index: i,
  status: i === 5 ? 'failed' : 'completed', attempt: i === 5 ? 2 : 1, last_error: i === 5 ? 'timeout sau 300 giây' : '',
  started_at: T0, finished_at: '2026-10-08T08:30:00Z' }));

const FAMILIES = ['E1', 'E2', 'E3', 'structural'];
const frameKey = (i) => ({ cvat_task_id: 118 + (i % 3), frame_number: 40 + i * 7 });
const bbox = (i) => ({ x1: 120 + i * 30, y1: 200 + i * 12, x2: 360 + i * 30, y2: 420 + i * 12 });
const candidates = Array.from({ length: 24 }, (_, i) => ({ engine: ENGINES[i % 5], engine_version: '1.0.0', family: FAMILIES[i % 4],
  severity: ['critical', 'medium', 'minor'][i % 3], frame: frameKey(i),
  anchor: { kind: 'annotation', objects: [{ namespace: 'cvat_shape', id: String(9000 + i) }], bbox: bbox(i), policy_version: 'pol-1.0' },
  evidence: { engine: ENGINES[i % 5], rule_id: 'VEH-02', expected: 'car', actual: 'truck', confidence: 0.82, iou: 0.91 } }));

const ranking = Array.from({ length: 20 }, (_, i) => ({ frame_id: 500 + i, frame_key: frameKey(i), rank: i + 1, score: Math.round((0.97 - i * 0.04) * 100) / 100,
  baseline_score: 0.5, score_version: 'score-1.2', queue: 'risk', source: 'risk', review_state: i < 3 ? 'reviewed' : i === 3 ? 'in_review' : 'unreviewed',
  missing_evidence: i === 9, issue_counts: { E1: 1 + (i % 2), E2: i % 3 }, explanation: { detector: 0.6, geometry: 0.3 }, lease_holder_user_id: i === 3 ? 4 : null }));
const randomRanking = Array.from({ length: 8 }, (_, i) => ({ ...ranking[i + 10], rank: i + 1, queue: 'random', source: 'random_audit' }));

const issue = (id, i, state = 'pending_review') => ({ id, family: FAMILIES[i % 3], origin: 'engine', state,
  anchor: { kind: 'annotation', objects: [{ namespace: 'cvat_shape', id: String(9000 + i) }], bbox: bbox(i), policy_version: 'pol-1.0' },
  n_i: 1, q_i: 0.8, severity: ['critical', 'medium', 'minor'][i % 3], rule_ids: ['VEH-02'],
  evidence: [{ engine: ENGINES[i % 5], rule_id: 'VEH-02', expected: 'car', actual: 'truck', confidence: 0.82, iou: 0.91 }], links: [], review_decisions: [] });
const frameIssues = (id) => ({ frame: frameSummary(id), guideline_version: 'gl-2.1',
  engines: run(12, 14, 'completed').engines, issues: [issue(id * 10 + 1, 0), issue(id * 10 + 2, 1), issue(id * 10 + 3, 2, 'confirmed')] });
const escalated = Array.from({ length: 6 }, (_, i) => issue(40 + i, i, 'escalated'));

const frameSummary = (id) => ({ id, run_id: 12, frame_key: frameKey(id % 20), cvat_job_id: 501, rank: id - 499, review_state: 'in_review', missing_evidence: false,
  image_url: `/_mock/frame/${id}.svg`, width: 1920, height: 1080, cvat_deep_link: `http://localhost:8080/tasks/118/jobs/501?frame=${id}` });

const rules = [
  ['VEH-01', 'Phương tiện', 'Gán nhãn car cho xe con, truck cho xe tải từ 3,5 tấn.'],
  ['VEH-02', 'Phương tiện', 'Xe bị che khuất trên 60% vẫn gán nhãn nếu nhận diện được loại xe.'],
  ['VEH-03', 'Phương tiện', 'Xe đỗ ngoài làn vẫn gán nhãn như xe đang chạy.'],
  ['PED-01', 'Người đi bộ', 'Người đi bộ cầm xe đạp gán nhãn pedestrian, không gán cyclist.'],
  ['SIG-01', 'Biển báo', 'Biển báo bị che quá 50% đánh dấu occluded.'],
].map(([rule_id, section, content]) => ({ rule_id, section, content, guideline_version: 'gl-2.1' }));
const mappings = [['E1', 'car', 'truck', 'VEH-02'], ['E1', 'truck', 'car', 'VEH-01'], ['E2', 'pedestrian', 'cyclist', 'PED-01'], ['E3', 'sign', 'sign', 'SIG-01']]
  .map(([error_group, class_name, paired_class, rule_id]) => ({ error_group, class_name, paired_class, rule_id, guideline_version: 'gl-2.1' }));

const ROLES = ['annotator', 'reviewer', 'qa_lead', 'qc_admin', 'super_admin', 'product_owner', 'data_model_owner'];
// Ma trận quyền và quy tắc quy trình phản chiếu ROLE_MATRIX và WORKFLOW_RULES của src/backend/accounts/views.py (mã quyền theo hợp đồng).
const matrix = [
  {
    "function": "Datasets",
    "roles": {
      "annotator": "view_assigned",
      "reviewer": "view_assigned",
      "qa_lead": "view_assigned",
      "qc_admin": "view_all",
      "super_admin": "view_all",
      "product_owner": "view_assigned",
      "data_model_owner": "view_assigned"
    }
  },
  {
    "function": "Quality Analysis",
    "roles": {
      "annotator": "none",
      "reviewer": "none",
      "qa_lead": "run_view",
      "qc_admin": "configure",
      "super_admin": "run_configure",
      "product_owner": "view_kpi",
      "data_model_owner": "none"
    }
  },
  {
    "function": "Review Queues & Workspace",
    "roles": {
      "annotator": "none",
      "reviewer": "review",
      "qa_lead": "review_monitor",
      "qc_admin": "view",
      "super_admin": "review_monitor",
      "product_owner": "none",
      "data_model_owner": "none"
    }
  },
  {
    "function": "Rework",
    "roles": {
      "annotator": "execute",
      "reviewer": "request_verify",
      "qa_lead": "request_monitor",
      "qc_admin": "none",
      "super_admin": "execute_verify",
      "product_owner": "none",
      "data_model_owner": "none"
    }
  },
  {
    "function": "Adjudication",
    "roles": {
      "annotator": "none",
      "reviewer": "none",
      "qa_lead": "yes",
      "qc_admin": "none",
      "super_admin": "override_with_reason",
      "product_owner": "none",
      "data_model_owner": "none"
    }
  },
  {
    "function": "Calibration & Audit",
    "roles": {
      "annotator": "participate",
      "reviewer": "participate",
      "qa_lead": "manage",
      "qc_admin": "configure",
      "super_admin": "manage_configure",
      "product_owner": "none",
      "data_model_owner": "none"
    }
  },
  {
    "function": "Phê duyệt phát hành",
    "roles": {
      "annotator": "none",
      "reviewer": "none",
      "qa_lead": "authorized",
      "qc_admin": "none",
      "super_admin": "override_with_reason",
      "product_owner": "none",
      "data_model_owner": "none"
    }
  },
  {
    "function": "Configuration",
    "roles": {
      "annotator": "none",
      "reviewer": "none",
      "qa_lead": "limited",
      "qc_admin": "yes",
      "super_admin": "full_including_permissions",
      "product_owner": "none",
      "data_model_owner": "lock_detector_artifact"
    }
  }
];
const workflowRules = [
  {
    "rule": "anti_self_review",
    "name": "Reviewer không review annotation của chính mình",
    "description": "Backend từ chối khi trùng người (kể cả Super Admin ghi đè)",
    "enforced": false
  },
  {
    "rule": "super_admin_override_reason",
    "name": "Ghi đè của Super Admin phải có lý do",
    "description": "Áp dụng cho quyết định, phân xử, waiver, phê duyệt phát hành, duyệt guideline",
    "enforced": false
  },
  {
    "rule": "audit_logging",
    "name": "Mọi thao tác ghi nhật ký kiểm toán",
    "description": "Gắn nhãn Super Admin khi dùng quyền ghi đè; ghi sự kiện từ chối",
    "enforced": true
  },
  {
    "rule": "separation_of_duties",
    "name": "Người duyệt khác người yêu cầu",
    "description": "Nguyên tắc bốn mắt, từ chối khi trùng người yêu cầu và phê duyệt",
    "enforced": false
  }
];

const decisionCases = [
  { id: 1, issue_id: 42, outcome: 'confirm', actor_user_id: 2, rule_id: 'VEH-02', correct_label: 'car', reason: 'Xe con bị che 40%.', case_version: 'dc-1', created_at: T0 },
  { id: 2, issue_id: 43, outcome: 'guideline_gap', actor_user_id: 2, rule_id: 'VEH-03', correct_label: null, reason: 'Guideline chưa nêu xe đỗ ngoài làn.', case_version: 'dc-1', created_at: T0 },
];
const reworkRequests = [
  { id: 1, issue_id: 42, state: 'open', requested_by: 4, requested_at: T0 },
  { id: 2, issue_id: 43, state: 'verified', requested_by: 4, requested_at: T0 },
];

// ---------------------------------------------------------------- tiện ích
const page = (results, extra = {}) => ({ next: null, previous: null, ...extra, results });
const err = (status, code, message) => [status, { code, message, request_id: 'mock-' + Date.now().toString(36) }];
const num = (v) => Number(v);

// Trả [status, body] hoặc null nếu không khớp. `q` là URLSearchParams.
function route(method, path, q, body) {
  let m;
  if (method === 'GET') {
    if (path === '/api/auth/workflow-permissions/') return [200, { matrix, rules: workflowRules, user_roles: body.__roles || [] }];
    if (path === '/api/datasets/') return [200, page(datasets)];
    if ((m = path.match(/^\/api\/datasets\/(\d+)\/tasks\/$/))) return tasksByDataset[m[1]] ? [200, tasks(num(m[1]))] : err(404, 'NOT_FOUND', 'Dataset không tồn tại.');
    if (path === '/api/snapshots/') return [200, page(snapshots.filter((s) => !q.get('dataset_id') || s.dataset_id === num(q.get('dataset_id'))))];
    if ((m = path.match(/^\/api\/snapshots\/(\d+)\/$/))) { const s = snapshots.find((x) => x.id === num(m[1])); return s ? [200, s] : err(404, 'NOT_FOUND', 'Snapshot không tồn tại.'); }
    if (path === '/api/config-versions/') return [200, page(configs.filter((c) => !q.get('status') || c.status === q.get('status')))];
    if (path === '/api/runs/') {
      const ids = snapshots.filter((s) => !q.get('dataset') || s.dataset_id === num(q.get('dataset'))).map((s) => s.id);
      return [200, page(runs.filter((r) => ids.includes(r.snapshot_id)))];
    }
    if ((m = path.match(/^\/api\/runs\/(\d+)\/(ledger|shards|candidates|ranking|gate)?\/?$/))) {
      const r = runs.find((x) => x.id === num(m[1]));
      if (!r) return err(404, 'NOT_FOUND', 'QC run không tồn tại.');
      if (!m[2]) return [200, r];
      if (m[2] === 'ledger') return [200, ledger];
      if (m[2] === 'shards') return [200, page(shards)];
      if (m[2] === 'candidates') return [200, page(candidates, { raw_count: 412, dedup_count: 384 })];
      if (m[2] === 'ranking') {
        const random = q.get('queue') === 'random';
        let list = random ? randomRanking : ranking;
        if (q.get('review_state')) list = list.filter((f) => f.review_state === q.get('review_state'));
        return [200, page(list, { source: random ? 'random_audit' : 'risk', content_hash: hash('c1'), ranking_hash: hash('d2') })];
      }
      return null;
    }
    if (path === '/api/guidelines/rules/') return [200, page(rules)];
    if (path === '/api/guidelines/mappings/') return [200, page(mappings)];
    if ((m = path.match(/^\/api\/guidelines\/rules\/([^/]+)\/$/))) { const r = rules.find((x) => x.rule_id === decodeURIComponent(m[1])); return r ? [200, r] : err(404, 'NOT_FOUND', 'Không có quy tắc này.'); }
    if ((m = path.match(/^\/api\/frames\/(\d+)\/issues\/$/))) return [200, frameIssues(num(m[1]))];
    if (path === '/api/escalations/') return [200, page(escalated)];
    if ((m = path.match(/^\/api\/issues\/(\d+)\/$/))) return [200, issue(num(m[1]), num(m[1]) % 3)];
    if (path === '/api/decision-cases/') return [200, decisionCases.filter((c) => (!q.get('issue') || c.issue_id === num(q.get('issue'))) && (!q.get('rule_id') || c.rule_id === q.get('rule_id')))];
    if (path === '/api/rework/') return [200, page(reworkRequests)];
    return null;
  }
  if (method === 'POST') {
    if (path === '/api/snapshots/') return [202, { id: 16, status: 'pending', drift_jobs: [] }];
    if (path === '/api/config-versions/') return [201, { ...configs[2], id: 10, name: body.name || 'cfg-moi' }];
    if ((m = path.match(/^\/api\/config-versions\/(\d+)\/publish\/$/))) return [200, { ...configs[2], id: num(m[1]), status: 'published', published_at: T0 }];
    if (path === '/api/runs/') return [201, run(15, body.snapshot_id || 14, 'queued', body.config_version_id || 8)];
    if ((m = path.match(/^\/api\/runs\/(\d+)\/cancel\/$/))) return [200, { ...run(num(m[1]), 14, 'cancelled') }];
    if ((m = path.match(/^\/api\/runs\/(\d+)\/retry-failed\/$/))) return [202, run(num(m[1]), 14, 'running')];
    if ((m = path.match(/^\/api\/queues\/(risk|random)\/next\/$/))) {
      const list = m[1] === 'random' ? randomRanking : ranking;
      const f = list.find((x) => x.review_state === 'unreviewed');
      return f ? [200, { lease: { id: 9000 + f.frame_id, frame_id: f.frame_id, holder_user_id: 4, expires_at: new Date(Date.now() + 15 * 60000).toISOString() }, frame: frameSummary(f.frame_id), resumed: false }]
        : [204, null];
    }
    if ((m = path.match(/^\/api\/leases\/(\d+)\/renew\/$/))) return [200, { id: num(m[1]), frame_id: num(m[1]) - 9000, holder_user_id: 4, expires_at: new Date(Date.now() + 15 * 60000).toISOString() }];
    if ((m = path.match(/^\/api\/frames\/(\d+)\/complete\/$/))) return [200, { ...frameSummary(num(m[1])), review_state: 'reviewed' }];
    if (path === '/api/issues/') return [201, issue(900, 0)];
    if ((m = path.match(/^\/api\/issues\/(\d+)\/decisions\/$/))) return [201, { id: 1, issue_id: num(m[1]), action: body.action || 'confirm', actor_user_id: 4, revision: body.revision || 'r1', created_at: T0 }];
    if ((m = path.match(/^\/api\/issues\/(\d+)\/adjudications\/$/))) return [201, { id: 3, issue_id: num(m[1]), outcome: body.outcome || 'confirm', actor_user_id: 2, rule_id: body.rule_id || 'VEH-02', correct_label: body.correct_label ?? null, reason: body.reason || '', case_version: 'dc-1', created_at: T0 }];
    if (path === '/api/effort-events/') return [202, { accepted: (body.events || []).length }];
  }
  return null;
}

function frameSvg(id) {
  const i = id % 20;
  const b = bbox(i);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080"><rect width="1920" height="1080" fill="#3a3f47"/>`
    + `<rect y="640" width="1920" height="440" fill="#2b2f35"/><rect x="${b.x1}" y="${b.y1}" width="${b.x2 - b.x1}" height="${b.y2 - b.y1}" fill="none" stroke="#f5a623" stroke-width="6"/>`
    + `<text x="40" y="70" font-family="sans-serif" font-size="44" fill="#d8dce2">Khung mẫu #${id} (dữ liệu giả lập)</text></svg>`;
}

// ---------------------------------------------------------------- server
function proxy(req, res) {
  const up = http.request({ host: TARGET.hostname, port: TARGET.port, method: req.method, path: req.url, headers: req.headers }, (r) => {
    res.writeHead(r.statusCode || 502, r.headers); r.pipe(res);
  });
  up.on('error', () => { res.writeHead(502, { 'content-type': 'text/plain' }); res.end('Next dev chưa sẵn sàng. Thử lại sau vài giây.'); });
  req.pipe(up);
}

// Lấy phiên từ mock auth của Next để biết vai trò; không có phiên thì 401 như backend thật.
function session(req) {
  return new Promise((resolve) => {
    const r = http.request({ host: TARGET.hostname, port: TARGET.port, path: '/api/auth/session/', headers: { cookie: req.headers.cookie || '' } }, (up) => {
      let data = ''; up.on('data', (c) => (data += c));
      up.on('end', () => { try { resolve(up.statusCode === 200 ? JSON.parse(data) : null); } catch { resolve(null); } });
    });
    r.on('error', () => resolve(null)); r.end();
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  const send = (status, body, type = 'application/json') => {
    res.writeHead(status, { 'content-type': type, 'cache-control': 'no-store', 'x-request-id': 'mock' });
    res.end(body === null ? undefined : type === 'application/json' ? JSON.stringify(body) : body);
  };
  let m;
  if ((m = url.pathname.match(/^\/_mock\/frame\/(\d+)\.svg$/))) return send(200, frameSvg(num(m[1])), 'image/svg+xml');
  if (url.pathname === '/_mock/health') return send(200, { status: 'ok' });
  if (!url.pathname.startsWith('/api/') || url.pathname.startsWith('/api/auth/') && url.pathname !== '/api/auth/workflow-permissions/') return proxy(req, res);

  const sess = await session(req);
  if (!sess) { const [s, b] = err(401, 'NOT_AUTHENTICATED', 'Chưa đăng nhập.'); return send(s, b); }
  let body = {};
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    const chunks = []; for await (const c of req) chunks.push(c);
    try { body = JSON.parse(Buffer.concat(chunks).toString() || '{}'); } catch { body = {}; }
  }
  body.__roles = sess.roles;
  const hit = route(req.method, url.pathname, url.searchParams, body);
  if (!hit) { const [s, b] = err(404, 'NOT_FOUND', `API giả lập chưa hỗ trợ ${req.method} ${url.pathname}`); return send(s, b); }
  return send(hit[0], hit[1]);
});

server.on('upgrade', (req, socket, head) => {
  const up = net.connect(Number(TARGET.port), TARGET.hostname, () => {
    up.write(`${req.method} ${req.url} HTTP/1.1\r\n` + Object.entries(req.headers).map(([k, v]) => `${k}: ${v}`).join('\r\n') + '\r\n\r\n');
    if (head && head.length) up.write(head);
    socket.pipe(up).pipe(socket);
  });
  up.on('error', () => socket.destroy()); socket.on('error', () => up.destroy());
});

server.listen(PORT, HOST, () => console.log(`mock-api: http://${HOST}:${PORT} -> Next ${TARGET.origin}`));
