import { apiArray, apiEndpoint, apiObject } from '@/lib/api-explorer/data';

export interface HomeDatasetRow {
  id: number;
  name: string;
  version?: string;
  cvatProjectId?: number;
  subLabel?: string;
  tasksJobs: string;
  frames: string;
  qcRun: string;
  qcRunStatus?: string | null;
  qcRunTone?: 'success' | 'warning' | 'danger' | 'info' | null;
  qcRunTime?: string;
  coverage: string;
  openIssues: string;
  gate: string;
  gateTone?: 'success' | 'warning' | 'danger' | 'info' | null;
  actionHref: string;
  actionTip: string;
}

const datasets = apiArray(apiObject(apiEndpoint('datasets_list').response).results).map(apiObject);
const label = (value: string) => ({ partial: 'Partial', checked: 'Checked', blocked: 'Blocked', released: 'Released', ready_for_approval: 'Ready · chờ duyệt' }[value] ?? value);

/** Product dataset rows sourced from the canonical API response used by the UI. */
export const HOME_DATASETS: HomeDatasetRow[] = datasets.map((dataset, index) => {
  const latest = apiObject(dataset.latest_run);
  const hasRun = Object.keys(latest).length > 0;
  const gate = String(latest.gate ?? 'not_checked');
  return {
    id: Number(dataset.id),
    name: String(dataset.name),
    version: String(dataset.version),
    cvatProjectId: Number(dataset.cvat_project_id),
    subLabel: dataset.read_only ? `CVAT project #${String(dataset.cvat_project_id)} · chỉ xem` : undefined,
    tasksJobs: `${String(dataset.task_count)} / ${String(dataset.job_count)}`,
    frames: Number(dataset.frame_count).toLocaleString('en-US'),
    qcRun: hasRun ? `#${String(latest.display_id)}` : 'Chưa có Quality Control Run',
    qcRunStatus: hasRun ? label(String(latest.status)) : null,
    qcRunTone: latest.status === 'checked' ? 'success' : latest.status === 'partial' ? 'warning' : null,
    qcRunTime: hasRun ? String(latest.started_at).replace('T', ' ').slice(0, 16) : undefined,
    coverage: hasRun ? `${(Number(latest.coverage) * 100).toFixed(1)}%` : '—',
    openIssues: hasRun ? String(latest.open_issues) : '—',
    gate: label(gate).replace('not_checked', 'Not checked'),
    gateTone: gate === 'released' ? 'success' : gate === 'blocked' ? 'danger' : gate === 'ready_for_approval' ? 'warning' : null,
    actionHref: index === 1 ? '/reports/releases' : index === 3 ? '/analysis' : '/?view=summary',
    actionTip: index === 0 ? 'Tiếp tục làm việc với Dataset này' : index === 1 ? 'Xem lịch sử phát hành' : index === 3 ? 'Tạo snapshot đầu tiên' : 'Mở Dataset này',
  };
});
