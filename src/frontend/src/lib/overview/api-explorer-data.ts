import { API_ENDPOINTS } from '@/lib/api-explorer/catalog';

const endpoint = (id: string) => {
  const item = API_ENDPOINTS.find(candidate => candidate.id === id);
  if (!item) throw new Error(`Thiếu API Explorer endpoint: ${id}`);
  return item;
};
const object = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const array = (value: unknown): unknown[] => Array.isArray(value) ? value : [];

const dataset = object(array(object(endpoint('datasets_list').response).results)[0]);
const tasks = array(endpoint('datasets_tasks').response).map(object);
const run = object(array(object(endpoint('runs_list').response).results)[0]);
const report = object(endpoint('run_report').response);
const reportMetrics = object(report.metrics);
const confirmedErrors = object(report.confirmed_errors);
const gateExamples = endpoint('runs_gate').responseExamples ?? [];
const gate = object(gateExamples.find(item => item.label === 'failed')?.response ?? endpoint('runs_gate').response);
const gateConditions = array(gate.conditions).map(object);
const gateCondition = gateConditions.find(value => String(value.name).toLowerCase() === 'coverage')
  ?? object(array(endpoint('runs_gate').response && (endpoint('runs_gate').response as Record<string, unknown>).conditions).find(value => String(object(value).name).toLowerCase() === 'coverage'));
const reworkExamples = endpoint('rework_list').responseExamples ?? [];
const rework = object(reworkExamples[0]?.response ?? endpoint('rework_list').response);
const reworkCounts = object(rework.counts);

export const QUALITY_SUMMARY_API_EXPLORER = {
  dataset: {
    id: Number(dataset.id),
    name: String(dataset.name),
    cvatProjectId: Number(dataset.cvat_project_id),
    guidelineVersion: String(dataset.guideline_version),
  },
  tasks: tasks.map(task => ({
    id: Number(task.id), name: String(task.name), coverage: Number(task.coverage),
    candidateCount: Number(task.candidate_count), confirmedCount: Number(task.confirmed_count), gate: String(task.gate),
    jobs: array(task.jobs).map(value => {
      const job = object(value);
      return { id: Number(job.id), frameCount: Number(job.frame_count) };
    }),
  })),
  run: { id: Number(run.id), snapshotId: Number(run.snapshot_id), status: String(run.status) },
  candidates: { count: Number(reportMetrics.candidate_count), rawCount: Number(reportMetrics.raw_candidate_count) },
  report: {
    coverage: Number(reportMetrics.coverage),
    openCriticalIssues: Number(reportMetrics.open_critical_issues),
    reworkCompletion: Number(reportMetrics.rework_completion),
    confirmedErrors: {
      label: Number(confirmedErrors.label),
      geometry: Number(confirmedErrors.geometry),
      missingObject: Number(confirmedErrors.missing_object), duplicateOverlap: Number(confirmedErrors.duplicate_overlap),
      attributeTrack: Number(confirmedErrors.attribute_track),
    },
  },
  gate: {
    status: String(gate.status ?? 'failed'),
    observed: Number(gateCondition?.observed ?? reportMetrics.coverage ?? 0.924),
    threshold: Number(gateCondition?.threshold ?? 0.95),
  },
  rework: {
    fixPending: Number(reworkCounts.fix_pending),
    recheckPending: Number(reworkCounts.recheck_pending),
    resolved: Number(reworkCounts.resolved),
    reopened: Number(reworkCounts.reopened),
  },
  engineStates: array((endpoint('runs_ledger').responseExamples ?? []).find(example => example.label === 'design')?.response).map(value => {
    const row = object(value);
    return {
      engine: String(row.engine), status: String(row.status), completed: Number(row.completed),
      eligible: Number(row.eligible), failed: Number(row.failed), pending: Number(row.pending),
      coverage: row.coverage === null ? null : Number(row.coverage), note: String(row.note),
    };
  }),
  reviewQueues: [
    { label: 'Ưu tiên theo rủi ro', count: 124, reviewed: 47, hint: 'Đã review 47 / 124' },
    { label: 'Kiểm tra ngẫu nhiên', count: 50, reviewed: 10, hint: 'Đã review 10 / 50' },
    { label: 'Chưa chắc chắn / Chuyển cấp trên', count: 18, reviewed: 0, hint: 'Chờ phân xử tại Escalations' },
  ],
} as const;
