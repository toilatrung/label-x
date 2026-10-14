'use client';

import React from 'react';
import Link from 'next/link';
import type { Dataset } from '@/lib/snapshots/api';
import type { Run } from '@/lib/execution/api';
import { engineStatusLabel } from '@/lib/execution/api';
import { ApiRequestError, errorMessage } from '@/lib/api/errors';
import { formatCount, snapshotCode } from '@/lib/format';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import {
  FAMILY_LABELS,
  confirmedIssueCount,
  gateCondition,
  percentText,
  reviewedCount,
  taskFrameCount,
  useCandidateCategories,
  useCandidateTotals,
  useDatasetTasks,
  useEscalationTally,
  useLatestRun,
  useQueueSummary,
  useReworkCounts,
  useRunDetail,
  useRunGate,
  useRunEngines,
  useRunLedger,
  useRunMetrics,
  useTasksQuality,
  type LedgerEntry,
  type RunEngineStat,
  type Tone,
} from '@/lib/overview/api';

interface QualitySummaryProps {
  currentDataset?: Dataset | null;
  /** Run người dùng đã chọn; không có thì dùng Quality Control Run mới nhất của Dataset. */
  selectedRun?: Run | null;
  selectedTaskScope?: string | null;
  onTaskScopeChange?: (task: string | null) => void;
}

interface QueryLike {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => unknown;
}

const ENGINE_LABELS: Record<string, string> = {
  schema: 'Schema / Taxonomy',
  geometry: 'Geometry',
  duplicate: 'Duplicate / Overlap',
  detector: 'Mô hình độc lập',
  vlm: 'Mô hình thị giác – ngôn ngữ',
  metric: 'Metric',
};

const NOT_CHECKED_REASONS: Record<string, string> = {
  no_reference: 'chưa có Ground Truth',
  no_model: 'chưa có mô hình',
  disabled: 'engine đang tắt',
  not_applicable: 'ngoài phạm vi áp dụng',
  not_triggered: 'không kích hoạt',
};

const EXCLUDED_REASONS = new Set(['not_applicable', 'not_triggered']);

function engineTone(status: LedgerEntry['status']): Tone {
  return ({ checked: 'success', partial: 'warning', running: 'info', failed: 'danger', not_checked: '' } as const)[status] ?? '';
}

function reasonText(reasons: [string, number][]): string {
  return reasons
    .filter(([, count]) => count > 0)
    .map(([key, count]) => `${formatCount(count)} ${NOT_CHECKED_REASONS[key] ?? key}`)
    .join(', ');
}

/** Ghi chú engine dựng từ ledger; khi excluded > 0 phải nêu số đơn vị bị loại và applicability_version (contract LedgerEntry). */
function engineNote(entry: LedgerEntry, stat: RunEngineStat | undefined): string {
  const unit = entry.unit;
  const parts = [`${formatCount(entry.completed)} / ${formatCount(entry.eligible)} ${unit} hoàn tất`];
  if (stat) parts.unshift(`${formatCount(stat.candidates)} candidate issue`);
  if (entry.failed > 0) parts.push(`${formatCount(entry.failed)} lỗi`);
  if (entry.pending > 0) parts.push(`${formatCount(entry.pending)} đang chờ`);
  const reasons = Object.entries((entry.not_checked_reasons ?? {}) as Record<string, number>);
  const notCheckedText = reasonText(reasons.filter(([key]) => !EXCLUDED_REASONS.has(key)));
  if (notCheckedText) parts.push(`chưa kiểm tra: ${notCheckedText}`);
  if (entry.excluded > 0) {
    const excludedText = reasonText(reasons.filter(([key]) => EXCLUDED_REASONS.has(key))) || 'ngoài phạm vi';
    parts.push(`${formatCount(entry.excluded)} ${unit} loại khỏi mẫu số (${excludedText}; applicability ${entry.applicability_version})`);
  }
  return parts.join(' · ');
}

function QueryError({ query, label }: { query: QueryLike; label: string }) {
  return (
    <div className="lx-state--card" role="alert">
      <div className="lx-text-danger lx-mb-3">{label}: {errorMessage(query.error)}</div>
      <button type="button" className="lx-btn lx-btn--sm" onClick={() => void query.refetch()}>Thử lại</button>
    </div>
  );
}

function InlineError({ query }: { query: QueryLike }) {
  if (query.error instanceof ApiRequestError && query.error.status === 403) {
    return <span className="lx-hint">Không có quyền xem trong phạm vi này</span>;
  }
  return (
    <span className="lx-hint" role="alert">
      <span className="lx-text-danger">Không tải được.</span>{' '}
      <button type="button" className="lx-btn lx-btn--sm" onClick={() => void query.refetch()}>Thử lại</button>
    </span>
  );
}

function HeaderActions() {
  return (
    <div className="lx-actions">
      <Link className="lx-btn" href="/reports">Xem Quality Report</Link>
      <Link className="lx-btn lx-btn--primary" href="/review">Vào Review Center →</Link>
    </div>
  );
}

export function QualitySummary({ currentDataset, selectedRun, selectedTaskScope, onTaskScopeChange }: QualitySummaryProps) {
  const datasetId = currentDataset?.id ?? null;
  const latestRun = useLatestRun(selectedRun ? null : datasetId);
  const baseRun = selectedRun ?? latestRun.data ?? null;
  const runId = baseRun?.id ?? null;

  const runDetail = useRunDetail(runId);
  const gate = useRunGate(runId);
  const ledger = useRunLedger(runId);
  const candidates = useCandidateTotals(runId);
  const categories = useCandidateCategories(runId);
  const metrics = useRunMetrics(runId);
  const engines = useRunEngines(runId);
  const tasksQuality = useTasksQuality(runId);
  const riskQueue = useQueueSummary('risk', runId);
  const randomQueue = useQueueSummary('random', runId);
  const escalations = useEscalationTally(runId);
  const rework = useReworkCounts(runId !== null ? datasetId : null);
  const tasks = useDatasetTasks(datasetId);

  if (!currentDataset) {
    return <>
      <div className="lx-head">
        <div className="lx-head__text">
          <h1 className="lx-h1">Quality Summary</h1>
          <p className="lx-lead">Chưa chọn Dataset. Chọn một Dataset ở Quality Control Home để xem tình trạng kiểm tra.</p>
        </div>
        <HeaderActions />
      </div>
      <div className="lx-card lx-state--card-muted">
        <div>Chưa có Dataset trong ngữ cảnh làm việc.</div>
        <Link className="lx-btn lx-btn--sm lx-mt-3" href="/">Về Quality Control Home</Link>
      </div>
    </>;
  }

  const run = runDetail.data ?? baseRun;
  const taskList = tasks.data ?? [];
  const jobCount = taskList.reduce((sum, task) => sum + task.jobs.length, 0);
  const jobsByTask = new Map(taskList.map(task => [task.cvat_task_id, task.jobs]));
  const coverage = gateCondition(gate.data, 'coverage');
  const critical = gateCondition(gate.data, 'open_critical_issues');
  const criticalCount = critical?.observed ?? null;
  const fixPending = rework.data?.fix_pending;
  const coverageFailed = coverage?.status === 'failed';
  const gateStatus = gate.data?.status;

  const lead = run
    ? `Tình trạng kiểm tra của ${currentDataset.name} · Quality Control Run #${run.id} · Snapshot ${snapshotCode(run.snapshot_id)}. Coverage thấp và lỗi nghiêm trọng luôn hiển thị riêng, không gộp vào một điểm chất lượng duy nhất.`
    : `Tình trạng kiểm tra của ${currentDataset.name}.`;

  const jobRangeOf = (jobIds: number[]) => jobIds.length === 0 ? 'Chưa có Job'
    : jobIds.length === 1 ? `Job ${jobIds[0]}` : `Job ${Math.min(...jobIds)} – ${Math.max(...jobIds)}`;
  const taskRow = (key: number, scope: string, sub: string, jobs: string, frames: number) => {
    const selected = selectedTaskScope === scope;
    return <tr key={key} tabIndex={0} aria-selected={selected} className={`lx-tr--clickable${selected ? ' is-selected' : ''}`} onClick={() => onTaskScopeChange?.(scope)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onTaskScopeChange?.(scope); } }}>
      <td><div className="lx-cell__main">{scope}</div><div className="lx-cell__sub">{sub}</div></td>
      <td className="r">{jobs}</td>
      <td className="r">{formatCount(frames)}</td>
      <td className="r lx-subtle">—</td><td className="r lx-subtle">—</td><td className="r lx-subtle">—</td>
      <td><span className="lx-subtle">—</span></td>
    </tr>;
  };
  const taskHead = <thead><tr><th>Task</th><th className="r">Job</th><th className="r">Frame</th><th className="r">Coverage</th><th className="r">Candidate</th><th className="r">Đã xác nhận</th><th>Gate</th></tr></thead>;

  // Có run: GET /api/runs/{id}/tasks-quality/ (frame, issue, tỷ lệ review theo Task của run), Job ghép từ tasks CVAT.
  // Chưa có run: chỉ có cấu trúc Task/Job/Frame từ GET /api/datasets/{id}/tasks/.
  const taskSection = (
    <section className="lx-card lx-main">
      <div className="lx-card__head"><h2 className="lx-h2">Theo Task</h2><span className="lx-hint">Chọn một dòng để đặt Phạm vi cho toàn module</span></div>
      {/* TODO(backend): coverage, candidate, lỗi đã xác nhận và gate theo Task — TaskQuality (MBE-06) chưa có các trường này. */}
      {run && <div className="lx-card__body"><NotConnectedNotice detail="Coverage, Candidate, Đã xác nhận và Gate theo Task chưa có trong API tasks-quality" /></div>}
      {run ? (
        tasksQuality.isPending ? <div className="lx-state--card-muted">Đang tải chất lượng theo Task…</div>
          : tasksQuality.isError ? <QueryError query={tasksQuality} label="Không tải được chất lượng theo Task" />
            : tasksQuality.data.length === 0 ? <div className="lx-state--card-muted">Run không có Task nào trong phạm vi.</div>
              : <div className="lx-scroll"><table className="lx-table lx-table--min-640">{taskHead}<tbody>
                {tasksQuality.data.map(task => {
                  const jobs = jobsByTask.get(task.cvat_task_id);
                  const sub = [jobs ? jobRangeOf(jobs.map(job => job.cvat_job_id)) : null, `${formatCount(task.issues)} issue`, `đã review ${percentText(task.reviewed_ratio)}`].filter(Boolean).join(' · ');
                  return taskRow(task.cvat_task_id, `T-${task.cvat_task_id} · ${task.name}`, sub, jobs ? String(jobs.length) : '—', task.frames);
                })}
              </tbody></table></div>
      ) : tasks.isPending ? <div className="lx-state--card-muted">Đang tải danh sách Task từ CVAT…</div>
        : tasks.isError ? <QueryError query={tasks} label="Không tải được danh sách Task" />
          : taskList.length === 0 ? <div className="lx-state--card-muted">Dataset chưa có Task nào được đồng bộ từ CVAT.</div>
            : <div className="lx-scroll"><table className="lx-table lx-table--min-640">{taskHead}<tbody>
              {taskList.map(task => taskRow(task.cvat_task_id, `T-${task.cvat_task_id} · ${task.name}`, jobRangeOf(task.jobs.map(job => job.cvat_job_id)), String(task.jobs.length), taskFrameCount(task)))}
            </tbody></table></div>}
    </section>
  );

  if (!selectedRun && (latestRun.isPending || latestRun.isError || latestRun.data === null)) {
    return <>
      <div className="lx-head">
        <div className="lx-head__text"><h1 className="lx-h1">Quality Summary</h1><p className="lx-lead">{lead}</p></div>
        <HeaderActions />
      </div>
      {latestRun.isPending ? <div className="lx-card lx-state--card-muted">Đang tải Quality Control Run gần nhất…</div>
        : latestRun.isError ? <div className="lx-card"><QueryError query={latestRun} label="Không tải được Quality Control Run" /></div>
          : <div className="lx-card lx-state--card-muted">
            <div>Dataset chưa có Quality Control Run nào. Tạo Snapshot và chạy kiểm tra để có số liệu chất lượng.</div>
            <Link className="lx-btn lx-btn--sm lx-mt-3" href="/analysis">Tạo snapshot đầu tiên</Link>
          </div>}
      <div className="lx-cols">{taskSection}</div>
    </>;
  }

  const queues = [
    { key: 'risk', label: 'Ưu tiên theo rủi ro', query: riskQueue },
    { key: 'random', label: 'Kiểm tra ngẫu nhiên', query: randomQueue },
  ] as const;
  const confirmed = metrics.data ? confirmedIssueCount(metrics.data) : null;
  const callout = gate.isPending
    ? { tone: 'lx-callout--info', badge: '', label: 'Đang tải Quality Gate…' }
    : gateStatus === 'failed' ? { tone: '', badge: 'lx-badge--danger', label: 'Release blocked' }
      : gateStatus === 'passed' ? { tone: 'lx-callout--info', badge: 'lx-badge--success', label: 'Gate đạt' }
        : { tone: 'lx-callout--warning', badge: '', label: 'Gate chưa kiểm tra' };
  const calloutParts = [
    coverage ? `Coverage ${percentText(coverage.observed)} ${coverageFailed ? 'chưa đạt' : 'so với'} ngưỡng ${percentText(coverage.threshold)}` : null,
    criticalCount !== null ? `${formatCount(criticalCount)} lỗi nghiêm trọng chưa đóng` : null,
    fixPending !== undefined ? `${formatCount(fixPending)} yêu cầu sửa chờ xử lý` : null,
  ].filter(Boolean);
  const coverageWidth = coverage?.observed !== null && coverage?.observed !== undefined ? `${Math.min(100, coverage.observed * 100)}%` : '0%';

  return <>
    <div className="lx-head">
      <div className="lx-head__text"><h1 className="lx-h1">Quality Summary</h1><p className="lx-lead">{lead}</p></div>
      <HeaderActions />
    </div>

    <div className={`lx-callout${callout.tone ? ` ${callout.tone}` : ''}`}>
      <span className={`lx-badge${callout.badge ? ` ${callout.badge}` : ''}`}>{callout.label}</span>
      <span className="lx-callout__text">
        {gate.isError ? <InlineError query={gate} /> : calloutParts.length ? `${calloutParts.join(' · ')}.` : '—'}
      </span>
      <Link className="lx-btn lx-btn--sm" href="/reports/gate">Xem Quality Gate</Link>
    </div>

    <div className="lx-grid lx-grid--4">
      <div className="lx-metric"><span className="lx-metric__k">Frame trong phạm vi</span>
        <span className="lx-metric__v">{metrics.isPending ? '…' : metrics.data ? formatCount(metrics.data.frames_total) : '—'}</span>
        <span className="lx-metric__n">{metrics.isError ? <InlineError query={metrics} /> : tasks.data ? `${formatCount(jobCount)} job · ${formatCount(taskList.length)} task trong CVAT` : '—'}</span></div>
      <div className="lx-metric"><span className="lx-metric__k">Coverage</span>
        <span className={`lx-metric__v${coverageFailed ? ' is-warn' : ''}`}>{gate.isPending ? '…' : percentText(coverage?.observed)}</span>
        <div className={`lx-progress${coverageFailed ? ' lx-progress--warn' : ''}`} role="img" aria-label={`Coverage ${percentText(coverage?.observed)}`}><i style={{ width: coverageWidth }} /></div>
        <span className="lx-metric__n">{gate.isError ? <InlineError query={gate} /> : `Ngưỡng yêu cầu ${percentText(coverage?.threshold)}`}</span></div>
      <div className="lx-metric"><span className="lx-metric__k">Candidate issue</span>
        <span className="lx-metric__v">{categories.isPending ? '…' : categories.data ? formatCount(categories.data.total) : candidates.data ? formatCount(candidates.data.dedup) : '—'}</span>
        <span className="lx-metric__n">{categories.isError && candidates.isError ? <InlineError query={categories} />
          : candidates.data?.raw !== null && candidates.data?.raw !== undefined ? `${formatCount(candidates.data.raw)} bản ghi thô → ${formatCount(candidates.data.dedup)} sau khi gộp trùng`
            : 'Sau khi gộp trùng; server chưa trả số bản ghi thô'}</span></div>
      {/* Lỗi đã xác nhận = issue ở trạng thái confirmed trở đi (issues_by_state của GET /api/runs/{id}/metrics/). */}
      <div className="lx-metric"><span className="lx-metric__k">Lỗi đã xác nhận</span>
        <span className="lx-metric__v">{metrics.isPending ? '…' : confirmed === null ? '—' : formatCount(confirmed)}</span>
        <span className={`lx-metric__n${criticalCount ? ' is-bad' : ''}`}>{metrics.isError ? <InlineError query={metrics} /> : criticalCount !== null ? `${formatCount(criticalCount)} lỗi nghiêm trọng chưa đóng` : `${formatCount(metrics.data?.issues_total)} issue trong run`}</span></div>
    </div>

    <div className="lx-cols">
      <section className="lx-card lx-main">
        <div className="lx-card__head"><h2 className="lx-h2">Trạng thái từng engine</h2><Link className="lx-link lx-link-sm" href="/analysis/history">Xem Execution History</Link></div>
        {ledger.isPending ? <div className="lx-state--card-muted">Đang tải coverage ledger…</div>
          : ledger.isError ? <QueryError query={ledger} label="Không tải được trạng thái engine" />
            : ledger.data.length === 0 ? <div className="lx-state--card-muted">Run chưa có bản ghi coverage ledger.</div>
              : <div className="lx-scroll"><table className="lx-table"><thead><tr><th>Engine</th><th>Trạng thái</th><th className="r">Coverage</th><th>Ghi chú</th></tr></thead><tbody>
                {ledger.data.map(entry => {
                  const tone = engineTone(entry.status);
                  return <tr key={entry.engine}><td className="lx-cell__main">{ENGINE_LABELS[entry.engine] ?? entry.engine}</td><td><span className={`lx-badge${tone ? ` lx-badge--${tone}` : ''}`}>{engineStatusLabel[entry.status] ?? entry.status}</span></td><td className={`r${entry.coverage === null ? ' lx-subtle' : ''}`}>{percentText(entry.coverage)}</td><td className="lx-muted">{engineNote(entry, engines.data?.find(stat => stat.engine === entry.engine))}</td></tr>;
                })}
              </tbody></table></div>}
      </section>

      <section className="lx-card lx-side">
        <div className="lx-card__head"><h2 className="lx-h2">Khối lượng review</h2><Link className="lx-link lx-link-sm" href="/review">Mở hàng đợi</Link></div>
        <div className="lx-card__body lx-stack lx-stack--14">
          {queues.map(({ key, label, query }) => {
            const total = query.data?.total ?? 0;
            const reviewed = query.data ? reviewedCount(query.data) : 0;
            return <div className="lx-stack" style={{ gap: 6 }} key={key}>
              <div className="lx-row lx-row--between"><span>{label}</span><b className="lx-num">{query.isPending ? '…' : query.data ? formatCount(total) : '—'}</b></div>
              <div className="lx-progress"><i style={{ width: `${total ? reviewed / total * 100 : 0}%` }} /></div>
              {query.isError ? <InlineError query={query} /> : <span className="lx-hint">{query.isPending ? 'Đang tải…' : query.data ? `Đã review ${formatCount(reviewed)} / ${formatCount(total)}` : 'Run chưa có hàng đợi review'}</span>}
            </div>;
          })}
          <div className="lx-stack" style={{ gap: 6 }}>
            <div className="lx-row lx-row--between"><span>Chưa chắc chắn / Chuyển cấp trên</span><b className="lx-num">{escalations.isPending ? '…' : escalations.data ? `${escalations.data.hasMore ? '≥ ' : ''}${formatCount(escalations.data.loaded)}` : '—'}</b></div>
            <div className="lx-progress"><i style={{ width: '0%' }} /></div>
            {escalations.isError ? <InlineError query={escalations} /> : <span className="lx-hint">Chờ phân xử tại Escalations</span>}
          </div>
          <div className="lx-row lx-row--between lx-row--border-top lx-pt-1"><span className="lx-muted">Đã xử lý</span><b className="lx-num">{metrics.isPending ? '…' : metrics.data ? formatCount(metrics.data.frames_reviewed) : '—'}</b></div>
        </div>
      </section>
    </div>

    <div className="lx-cols">
      {taskSection}
      <section className="lx-card lx-side">
        <div className="lx-card__head"><h2 className="lx-h2">Candidate theo loại lỗi</h2></div>
        {/* GET /api/runs/{id}/candidate-categories/ (MBE-06): số candidate theo IssueFamily. */}
        {categories.isPending ? <div className="lx-state--card-muted">Đang tải candidate theo loại lỗi…</div>
          : categories.isError ? <QueryError query={categories} label="Không tải được candidate theo loại lỗi" />
            : categories.data.categories.length === 0 ? <div className="lx-state--card-muted">Run chưa có candidate issue.</div>
              : <div className="lx-card__body lx-stack lx-stack--12">
                {categories.data.categories.map(category => {
                  const max = Math.max(...categories.data.categories.map(row => row.count));
                  return <div className="lx-bar" key={category.family}><span>{FAMILY_LABELS[category.family] ?? category.family}</span><div className="lx-bar__t"><i style={{ width: `${max ? category.count / max * 100 : 0}%` }} /></div><span className="lx-bar__n">{formatCount(category.count)}</span></div>;
                })}
              </div>}
      </section>
    </div>
  </>;
}
