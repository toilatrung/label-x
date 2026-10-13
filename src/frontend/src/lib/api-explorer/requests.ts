import { configVersion, reference, snapshot, waiver } from './examples';
import type { components } from '@/lib/api/contract';

// Contract bodies use wire fields; design-only bodies describe the sketch, not a live API.
export const REQUEST_BODIES: Readonly<Record<string, unknown>> = {
  auth_login: { username: 'qa.lead', password: '<password>' } satisfies components['schemas']['LoginRequest'],
  snapshots_create: { dataset_id: 14, scope: { cvat_task_ids: [119, 120], cvat_job_ids: [] } } satisfies components['schemas']['SnapshotCreate'],
  config_versions_create: { name: configVersion.name, engines: configVersion.engines, thresholds: configVersion.thresholds, models: configVersion.models } satisfies components['schemas']['ConfigVersionCreate'],
  runs_create: { snapshot_id: 14, config_version_id: 7, seed: snapshot.seed } satisfies components['schemas']['RunCreate'],
  queues_next: { run_id: 91 } satisfies components['schemas']['QueueNextRequest'],
  frames_complete: { lease_id: 61 } satisfies components['schemas']['FrameCompleteRequest'],
  issues_create: { frame_id: 3301, lease_id: 61, family: 'E2', anchor: { kind: 'manual_region', objects: [], bbox: { x1: 120, y1: 180, x2: 360, y2: 340 }, policy_version: 'pilot-1' }, description: 'Sai nhãn bus hay truck' } satisfies components['schemas']['ManualIssueCreate'],
  issues_decide: { lease_id: 61, action: 'confirm', revision: snapshot.revision_hash, family: 'E2', severity: 'medium', rule_id: 'VEH-03' } satisfies components['schemas']['IssueDecisionCreate'],
  issues_adjudicate: { outcome: 'confirm', rule_id: 'VEH-03', correct_label: 'truck', reason: 'Xe buýt mini chở hàng; đối chiếu Guideline v1.2.' } satisfies components['schemas']['AdjudicationCreate'],
  rework_create: { issue_id: 902, instruction: 'Đổi nhãn bus → truck theo VEH-03', annotator_user_id: 28, due_at: '2026-10-15T10:00:00Z', severity: 'medium', cvat_deep_link: 'http://localhost:8080/tasks/19/jobs/44' } satisfies components['schemas']['ReworkCreate'],
  rework_submitted: { cvat_revision: '3aa7992e'.repeat(8) } satisfies components['schemas']['ReworkSubmission'],
  rework_verify: { passed: true, revision: '3aa7992e'.repeat(8) } satisfies components['schemas']['ReworkVerification'],
  references_create: { snapshot_id: reference.snapshot_id, gt_source: 'bdd100k/labels.json', gt_checksum: reference.gt_checksum, mapping_version: reference.mapping_version, matching_threshold: reference.matching_threshold, minimum_area: reference.minimum_area, algorithm_version: reference.algorithm_version } satisfies components['schemas']['ReferenceCreate'],
  effort_events_create: { events: [{ client_event_id: 'b53b8c2b-15b8-4a04-a6bf-9256647ecf86', frame_id: 3301, activity: 'review_issue', started_at: '2026-10-12T04:00:00Z', ended_at: '2026-10-12T04:01:00Z', gaps: [], policy_version: 'pilot-1' }] } satisfies components['schemas']['EffortEventBatch'],
  evaluations_create: { snapshot_id: 18, run_id: 31, reference_id: 9, score_version: 'score-v0', parameters: { minimum_sample: 100 } } satisfies components['schemas']['EvaluationCreate'],
  waivers_create: { run_id: waiver.run_id, condition: 'coverage', reason: waiver.reason, evidence: waiver.evidence, expires_at: waiver.expires_at } satisfies components['schemas']['WaiverCreate'],
  waivers_approve: { approved: true, reason: 'Đã kiểm tra bằng chứng và phạm vi waiver.' } satisfies components['schemas']['WaiverDecision'],
  guideline_gaps_create: { rule: 'VEH-03', content: 'Xe buýt mini chở hàng thuộc nhãn nào', reason: 'Reviewer bất đồng giữa bus và truck.', issueId: 98 },
  workflow_rule_update: { enforced: true },
  models_update: { confidence_threshold: 0.65, status: 'active' },
  benchmarks_create: { name: 'Benchmark v1.3', snapshot_id: 18 },
  benchmarks_import_cvat: { benchmark_id: 10, cvat_task_ids: [19] },
  calibration_assignments_create: { benchmark_id: 9, assignee_user_id: 12, frame_count: 45, due_at: '2026-10-18T00:00:00Z' },
  audit_samples_create: { run_id: 91, stream: 'random', requested_size: 100, seed: 20261004 },
  run_report_export: { format: 'pdf' },
  release_approve: { reason: 'Quality Gate đạt; phê duyệt phát hành v1.3.' },
};

export const REQUEST_QUERIES: Readonly<Record<string, string>> = {
  snapshots_list: "?dataset_id=14",
  rework_list: "?dataset_id=14",
};
