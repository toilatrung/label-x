import { configVersion, evaluation, issue, rework, run, session, snapshot, waiver } from './examples';
import type { ApiResponseExample } from './types';

const variants = <T extends string>(statuses: readonly T[], build: (status: T, index: number) => unknown): ApiResponseExample[] =>
  statuses.map((status, index) => ({ label: status, response: build(status, index) }));

const snapshotStatuses = ['pending', 'exporting', 'locked', 'failed'] as const;
const runStatuses = ['queued', 'running', 'completed', 'partial', 'failed', 'cancelled'] as const;
const engineStatuses = ['running', 'checked', 'partial', 'failed', 'not_checked'] as const;
const shardStatuses = ['pending', 'running', 'completed', 'failed', 'cancelled'] as const;
const frameStatuses = ['unreviewed', 'in_review', 'incomplete', 'reviewed', 'awaiting_followup', 'completed'] as const;
const issueStates = ['pending_review', 'in_review', 'confirmed', 'rejected', 'escalated', 'fix_pending', 'recheck_pending', 'resolved', 'reopened'] as const;
const reworkStatuses = ['fix_pending', 'recheck_pending', 'resolved', 'reopened'] as const;
const evaluationStatuses = ['queued', 'running', 'completed', 'failed', 'insufficient_sample'] as const;
const gateStatuses = ['passed', 'failed', 'not_checked'] as const;
const waiverStatuses = ['pending', 'approved', 'rejected', 'expired'] as const;

const ledgerFor = (status: typeof engineStatuses[number], index: number) => {
  const rows = {
    running: { completed: 72, failed: 0, pending: 28, not_checked: 0, coverage: 0.72 },
    checked: { completed: 100, failed: 0, pending: 0, not_checked: 0, coverage: 1 },
    partial: { completed: 86, failed: 4, pending: 10, not_checked: 0, coverage: 0.86 },
    failed: { completed: 0, failed: 100, pending: 0, not_checked: 0, coverage: 0 },
    not_checked: { completed: 0, failed: 0, pending: 0, not_checked: 100, coverage: 0 },
  }[status];
  return {
    engine: ['schema', 'geometry', 'duplicate', 'detector', 'metric'][index], status, required: true,
    unit: 'frame', total: 100, eligible: 100, excluded: 0, applicability_version: '2026.10',
    ...rows, not_checked_reasons: status === 'not_checked' ? { no_reference: 100 } : {},
  };
};

/** Contract-valid state variants shown by API Explorer without changing the default response. */
export const STATUS_RESPONSE_EXAMPLES: Readonly<Partial<Record<string, readonly ApiResponseExample[]>>> = {
  auth_session: variants(['mapped', 'missing'] as const, status => ({
    ...session,
    identity_mapping: { status, cvat_user_id: status === 'mapped' ? 41 : null },
  })),
  snapshots_list: [{ label: 'design', response: { next: null, previous: null, results: [
    { ...snapshot, id: 14, display_id: 'SNP-014', dataset_name: 'Road Vision Urban · v1.4', revision_hash: 'a91f3c', frame_count: 12500, run_id: 91, display_run_id: 'QC-091', display_status: 'Đang dùng' },
    { ...snapshot, id: 13, display_id: 'SNP-013', dataset_name: 'Road Vision Urban · v1.4', revision_hash: '7be204', frame_count: 12500, run_id: 88, display_run_id: 'QC-088', display_status: 'Đã thay thế' },
    { ...snapshot, id: 12, display_id: 'SNP-012', dataset_name: 'Road Vision Highway · v0.9', revision_hash: 'c40d19', frame_count: 5600, run_id: 85, display_run_id: 'QC-085', display_status: 'Đã khoá' },
    { ...snapshot, id: 11, display_id: 'SNP-011', dataset_name: 'Road Vision Urban · v1.3', revision_hash: 'f02a6d', frame_count: 11800, run_id: 77, display_run_id: 'QC-077', display_status: 'Đã khoá' },
  ] } }, ...variants(snapshotStatuses, (status, index) => ({
    next: null, previous: null,
    results: [{ ...snapshot, id: 18 + index, status, revision_hash: status === 'locked' ? snapshot.revision_hash : null,
      failure_reason: status === 'failed' ? 'export_error' : null }],
  }))],
  snapshots_retrieve: variants(snapshotStatuses, (status, index) => ({
    ...snapshot, id: 18 + index, status, revision_hash: status === 'locked' ? snapshot.revision_hash : null,
    failure_reason: status === 'failed' ? 'export_error' : null,
  })),
  config_versions_list: variants(['draft', 'published'] as const, status => ({
    next: null, previous: null,
    results: [{ ...configVersion, status, published_at: status === 'published' ? configVersion.published_at : null }],
  })),
  runs_list: [{ label: 'design', response: { next: null, previous: null, results: [
    { ...run, id: 91, display_id: 'QC-091', snapshot_id: 14, display_snapshot_id: 'SNP-014', created_at: '2026-10-04T06:58:00Z', coverage: 0.924, status: 'partial' },
    { ...run, id: 88, display_id: 'QC-088', snapshot_id: 13, display_snapshot_id: 'SNP-013', created_at: '2026-10-02T17:30:00Z', coverage: 0.951, status: 'checked' },
    { ...run, id: 83, display_id: 'QC-083', snapshot_id: 13, display_snapshot_id: 'SNP-013', created_at: '2026-10-01T09:12:00Z', coverage: 0.41, status: 'failed' },
  ] } }, ...variants(runStatuses, (status, index) => ({
    next: null, previous: null,
    results: [{ ...run, id: 31 + index, status, is_final: status === 'completed', finished_at: ['completed', 'partial', 'failed', 'cancelled'].includes(status) ? '2026-10-12T03:20:00Z' : null }],
  }))],
  runs_retrieve: variants(runStatuses, (status, index) => ({
    ...run, id: 31 + index, status, is_final: status === 'completed',
    finished_at: ['completed', 'partial', 'failed', 'cancelled'].includes(status) ? '2026-10-12T03:20:00Z' : null,
  })),
  runs_ledger: [{
    label: 'design',
    response: [
      { engine: 'Schema / Taxonomy', status: 'checked', required: true, unit: 'frame', total: 12500, eligible: 12500, completed: 12500, failed: 0, pending: 0, coverage: 1, note: 'Không phát hiện lỗi cấu trúc' },
      { engine: 'Geometry', status: 'issue_found', required: true, unit: 'frame', total: 12500, eligible: 12500, completed: 12275, failed: 0, pending: 225, coverage: 0.982, candidate_count: 74, note: '74 candidate issue' },
      { engine: 'Duplicate / Overlap', status: 'issue_found', required: true, unit: 'frame', total: 12500, eligible: 12500, completed: 12275, failed: 0, pending: 225, coverage: 0.982, candidate_count: 41, note: '41 candidate issue' },
      { engine: 'Mô hình độc lập', status: 'partial', required: true, unit: 'frame', total: 12500, eligible: 12500, completed: 10838, failed: 0, pending: 1662, coverage: 0.867, note: 'Job 2273, 2274 chưa chạy hết' },
      { engine: 'Mô hình thị giác – ngôn ngữ', status: 'failed', required: true, unit: 'frame', total: 12500, eligible: 12500, completed: 0, failed: 12500, pending: 0, coverage: 0, note: 'Hết thời gian chờ · có thể chạy lại' },
      { engine: 'Metric', status: 'not_checked', required: false, unit: 'frame', total: 12500, eligible: 0, completed: 0, failed: 0, pending: 0, coverage: null, note: 'Chưa có Ground Truth cho phạm vi này', not_checked_reasons: { no_reference: 12500 } },
    ],
  }, ...variants(engineStatuses, (status, index) => [ledgerFor(status, index)])],
  runs_shards: variants(shardStatuses, (status, index) => ({
    next: null, previous: null,
    results: [{ id: 88 + index, engine: 'geometry', shard_key: `job:${2270 + index}`, shard_index: index, status, attempt: status === 'failed' ? 3 : 1,
      last_error: status === 'failed' ? 'worker timeout' : '', started_at: status === 'pending' ? null : '2026-10-12T03:01:00Z',
      finished_at: ['completed', 'failed', 'cancelled'].includes(status) ? '2026-10-12T03:05:00Z' : null }],
  })),
  queues_list: variants(frameStatuses, (review_state, index) => ({
    next: null, previous: null,
    results: [{ frame_id: 3301 + index, rank: index + 1, score: 0.94 - index * 0.05, priority: index < 2 ? 'high' : 'normal', family: 'geometry', review_state,
      holder: review_state === 'in_review' ? { user_id: 12, expires_at: '2026-10-12T04:15:00Z' } : null }],
  })),
  frames_issues: [{
    label: 'all engine + issue states',
    response: {
      frame: { id: 3301, review_state: 'in_review' },
      engines: engineStatuses.map((status, index) => ({ engine: ['schema', 'geometry', 'duplicate', 'detector', 'metric'][index], status,
        reason: status === 'not_checked' ? 'no_reference' : null, failed_units: status === 'failed' ? 10 : 0 })),
      issues: issueStates.map((state, index) => ({ ...issue, id: 902 + index, state, status: undefined })),
    },
  }],
  issues_decide: variants(['confirm', 'reject', 'uncertain', 'escalate'] as const, (action, index) => ({
    id: 1102 + index, issue_id: 902, action, actor_user_id: 12, revision: snapshot.revision_hash,
    family: action === 'confirm' ? 'E2' : null, severity: action === 'confirm' ? 'medium' : null,
    reason: action === 'confirm' ? null : `Ví dụ quyết định ${action}`, created_at: '2026-10-12T04:20:00Z',
  })),
  issues_adjudicate: variants(['confirm', 'reject', 'guideline_gap'] as const, (outcome, index) => ({
    id: 81 + index, issue_id: 902, outcome, actor_user_id: 7, rule_id: 'GEO-001',
    reason: `Ví dụ phân xử ${outcome}`, case_version: 'v1', created_at: '2026-10-12T04:30:00Z',
  })),
  rework_list: variants(reworkStatuses, (status, index) => ({
    next: null, previous: null,
    counts: { fix_pending: 12, recheck_pending: 4, resolved: 74, reopened: 2 },
    results: [{ ...rework, id: 73 + index, status, submitted_revision: status === 'fix_pending' ? null : 'sha256:3aa7…992e' }],
  })),
  rework_retrieve: variants(reworkStatuses, (status, index) => ({
    ...rework, id: 73 + index, status, submitted_revision: status === 'fix_pending' ? null : 'sha256:3aa7…992e',
  })),
  evaluations_retrieve: variants(evaluationStatuses, (status, index) => ({
    ...evaluation, id: 14 + index, status,
    leakage_check: status === 'completed' ? 'passed' : status === 'failed' ? 'failed' : 'not_checked',
    metrics: status === 'completed' ? {
      computed: { status: 'computed', value: 0.91, sample_size: 220, denominator: 240, method: 'score-v0' },
      not_checked: { status: 'not_checked', value: null, sample_size: 0, denominator: 0, method: 'score-v0' },
      insufficient_sample: { status: 'insufficient_sample', value: null, sample_size: 20, denominator: 100, method: 'score-v0' },
    } : null,
  })),
  runs_gate: variants(gateStatuses, status => ({
    run_id: 31, source_run_id: 31, source_reason: 'final_run', status,
    conditions: [
      { name: 'coverage', status: status === 'passed' ? 'passed' : status, observed: status === 'not_checked' ? null : status === 'passed' ? 0.98 : 0.92, threshold: 0.95, waiver_id: null },
      { name: 'agreement', status: 'waived', observed: 0.88, threshold: 0.9, waiver_id: 6 },
    ],
  })),
  waivers_approve: variants(waiverStatuses, (status, index) => ({
    ...waiver, id: 6 + index, status, approved_by: ['approved', 'rejected'].includes(status) ? 7 : null,
  })),
  benchmarks_list: variants(['draft', 'in_review', 'locked', 'superseded'] as const, (status, index) => ({
    results: [{ id: 9 + index, name: `Benchmark v1.${index + 1}`, snapshot_id: 18, frame_count: status === 'draft' ? 0 : 200,
      status, locked_at: status === 'locked' ? '2026-10-10T08:00:00Z' : null }],
  })),
  benchmarks_import_cvat: variants(['queued', 'running', 'completed', 'failed'] as const, status => ({
    import_id: 22, benchmark_id: 10, cvat_task_ids: [19], status,
    error: status === 'failed' ? 'Taxonomy mapping mismatch' : null,
  })),
  audit_samples_list: variants(['pending', 'in_review', 'reviewed'] as const, (status, index) => ({
    next: null, previous: null, stream: index === 0 ? 'random' : 'risk',
    results: [{ id: 41 + index, run_id: 31, frame_id: 3301 + index, status, seed: 104729 }],
  })),
  calibration_reviewers: variants(['assigned', 'in_progress', 'completed', 'overdue'] as const, (status, index) => ({
    results: [{ user_id: 12 + index, full_name: ['Bình Hồ', 'An Nguyễn', 'Chi Lâm', 'Minh Đức'][index],
      completed: status === 'assigned' ? 0 : status === 'completed' ? 45 : 40, assigned: 45,
      agreement: status === 'completed' ? 0.956 : null, status }],
  })),
  calibration_models: variants(['queued', 'running', 'completed', 'insufficient_sample', 'failed'] as const, status => ({
    results: [{ model_id: 5, name: 'Detector v2.3', precision: status === 'completed' ? 0.875 : null,
      recall: status === 'completed' ? 0.81 : null, status }],
  })),
  calibration_assignments_create: variants(['assigned', 'in_progress', 'completed', 'overdue'] as const, status => ({
    id: 66, benchmark_id: 9, assignee_user_id: 12, frame_count: 45, due_at: '2026-10-18T00:00:00Z', status,
  })),
  guideline_gaps_list: variants(['open', 'resolved'] as const, (status, index) => ({
    next: null, previous: null,
    results: [{ id: 12 + index, issue_id: 902, status, title: 'Phân biệt bus và truck', proposed_rule: 'VEH-08' }],
  })),
  models_list: variants(['active', 'experimental', 'inactive'] as const, (status, index) => ({
    results: [{ id: 5 + index, name: ['Detector', 'Vision-language model', 'Classifier'][index], version: 'v2.3',
      role: 'object_detection', taxonomy_version: 'v3', confidence_threshold: 0.6, status }],
  })),
  guideline_versions_list: variants(['active', 'pending_approval', 'superseded'] as const, (status, index) => ({
    results: [{ version: `v1.${2 + index}`, taxonomy_version: 'v3', dataset_ids: status === 'pending_approval' ? [] : [12],
      effective_at: status === 'pending_approval' ? null : '2026-08-20', status }],
  })),
  run_report_export: variants(['queued', 'running', 'completed', 'failed'] as const, (status, index) => ({
    export_id: 55 + index, run_id: 31, format: ['pdf', 'csv', 'json', 'pdf'][index], status,
    download_url: status === 'completed' ? '/downloads/RPT-QC-091.pdf' : null,
    error: status === 'failed' ? 'Renderer unavailable' : null,
  })),
  releases_list: variants(['draft', 'approved', 'released', 'blocked'] as const, (status, index) => ({
    next: null, previous: null,
    results: [{ id: 13 + index, version: `v1.${4 + index}`, dataset_id: 12, snapshot_id: 18, run_id: 31, status,
      released_at: status === 'released' ? '2026-10-11T09:00:00Z' : null }],
  })),
  release_approve: variants(['approved', 'rejected'] as const, status => ({
    id: 13, version: 'v1.4', status, approved_by: 7, approved_at: '2026-10-12T07:00:00Z',
    reason: status === 'rejected' ? 'Quality gate chưa đạt' : null,
  })),
};
