'use client';

import React from 'react';
import Link from 'next/link';
import type { Dataset } from '@/lib/snapshots/api';
import type { Run } from '@/lib/execution/api';
import { QUALITY_SUMMARY_API_EXPLORER as data } from '@/lib/overview/api-explorer-data';

interface QualitySummaryProps {
  currentDataset?: Dataset | null;
  selectedRun?: Run | null;
  selectedTaskScope?: string | null;
  onTaskScopeChange?: (task: string | null) => void;
}

function percent(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function badgeTone(status: string) {
  if (['checked', 'completed', 'resolved', 'passed'].includes(status)) return 'success';
  if (['running', 'in_review'].includes(status)) return 'info';
  if (['partial', 'pending', 'fix_pending', 'recheck_pending'].includes(status)) return 'warning';
  if (['failed', 'reopened'].includes(status)) return 'danger';
  return '';
}

function statusLabel(value: string) {
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase());
}

export function QualitySummary({ currentDataset, selectedRun, selectedTaskScope, onTaskScopeChange }: QualitySummaryProps) {
  const frameCount = data.tasks.reduce((total, task) => total + task.jobs.reduce((sum, job) => sum + job.frameCount, 0), 0);
  const confirmedTotal = Object.values(data.report.confirmedErrors).reduce((sum, count) => sum + count, 0);
  const categories = [
    ['Sai nhãn', data.report.confirmedErrors.label],
    ['Hình học', data.report.confirmedErrors.geometry],
    ['Thiếu object', data.report.confirmedErrors.missingObject],
    ['Trùng / chồng lấn', data.report.confirmedErrors.duplicateOverlap],
    ['Thuộc tính / Track', data.report.confirmedErrors.attributeTrack],
  ] as const;
  const maxCategory = Math.max(...categories.map(([, count]) => count));
  const datasetName = currentDataset?.name ?? data.dataset.name;
  const runId = selectedRun?.id ?? data.run.id;

  return <>
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Quality Summary</h1>
        <p className="lx-lead">Tình trạng kiểm tra của {datasetName} · Quality Control Run #{runId} · Snapshot #{data.run.snapshotId}.</p>
      </div>
      <div className="lx-actions">
        <Link className="lx-btn" href="/reports">Xem Quality Report</Link>
        <Link className="lx-btn lx-btn--primary" href="/review">Vào Review Center →</Link>
      </div>
    </div>

    <div className="lx-callout">
      <span className="lx-badge lx-badge--danger">Release blocked</span>
      <span className="lx-callout__text">Coverage {percent(data.gate.observed)} chưa đạt ngưỡng {percent(data.gate.threshold)} · {data.report.openCriticalIssues} lỗi nghiêm trọng đang mở · {data.rework.fixPending} yêu cầu sửa đang chờ.</span>
      <Link className="lx-btn lx-btn--sm" href="/reports/gate">Xem Quality Gate</Link>
    </div>

    <div className="lx-grid lx-grid--4">
      <div className="lx-metric"><span className="lx-metric__k">Frame trong phạm vi</span><span className="lx-metric__v">{frameCount.toLocaleString('en-US')}</span><span className="lx-metric__n">48,912 object · 7 job</span></div>
      <div className="lx-metric"><span className="lx-metric__k">Coverage</span><span className="lx-metric__v is-warn">{percent(data.report.coverage)}</span><div className="lx-progress lx-progress--warn" role="img" aria-label={`Coverage ${percent(data.report.coverage)}`}><i style={{ width: percent(data.report.coverage) }} /></div><span className="lx-metric__n">Ngưỡng yêu cầu {percent(data.gate.threshold)}</span></div>
      <div className="lx-metric"><span className="lx-metric__k">Candidate issue</span><span className="lx-metric__v">{data.candidates.count}</span><span className="lx-metric__n">{data.candidates.rawCount} bản ghi thô → {data.candidates.count} sau khi gộp trùng</span></div>
      <div className="lx-metric"><span className="lx-metric__k">Lỗi đã xác nhận</span><span className="lx-metric__v">{confirmedTotal}</span><span className="lx-metric__n is-bad">{data.report.openCriticalIssues} lỗi nghiêm trọng đang mở</span></div>
    </div>

    <div className="lx-cols">
      <section className="lx-card lx-main">
        <div className="lx-card__head"><h2 className="lx-h2">Trạng thái từng engine</h2><Link className="lx-link lx-link-sm" href="/analysis/history">Xem Execution History</Link></div>
        <div className="lx-scroll"><table className="lx-table"><thead><tr><th>Engine</th><th>Trạng thái</th><th className="r">Coverage</th><th>Ghi chú</th></tr></thead><tbody>
          {data.engineStates.map(engine => <tr key={engine.engine}><td className="lx-cell__main">{engine.engine}</td><td><span className={`lx-badge${badgeTone(engine.status) ? ` lx-badge--${badgeTone(engine.status)}` : ''}`}>{statusLabel(engine.status)}</span></td><td className="r">{percent(engine.coverage)}</td><td className="lx-muted">{engine.note}</td></tr>)}
        </tbody></table></div>
      </section>

      <section className="lx-card lx-side">
        <div className="lx-card__head"><h2 className="lx-h2">Khối lượng review</h2><Link className="lx-link lx-link-sm" href="/review">Mở hàng đợi</Link></div>
        <div className="lx-card__body lx-stack lx-stack--14">
          {data.reviewQueues.map(queue => <div className="lx-stack" style={{ gap: 6 }} key={queue.label}><div className="lx-row lx-row--between"><span>{queue.label}</span><b className="lx-num">{queue.count}</b></div><div className="lx-progress"><i style={{ width: `${queue.count ? queue.reviewed / queue.count * 100 : 0}%` }} /></div><span className="lx-hint">{queue.hint}</span></div>)}
          <div className="lx-row lx-row--between lx-row--border-top lx-pt-1"><span className="lx-muted">Đã xử lý</span><b className="lx-num">242</b></div>
        </div>
      </section>
    </div>

    <div className="lx-cols">
      <section className="lx-card lx-main">
        <div className="lx-card__head"><h2 className="lx-h2">Theo Task</h2><span className="lx-hint">Chọn dòng để đặt phạm vi</span></div>
        <div className="lx-scroll"><table className="lx-table lx-table--min-640"><thead><tr><th>Task</th><th className="r">Job</th><th className="r">Frame</th><th className="r">Coverage</th><th className="r">Candidate</th><th>Gate</th></tr></thead><tbody>
          {data.tasks.map(task => {
            const scope = `T-${task.id} · ${task.name}`;
            const selected = selectedTaskScope === scope;
            const frames = task.jobs.reduce((sum, job) => sum + job.frameCount, 0);
            return <tr key={task.id} role="row" tabIndex={0} aria-selected={selected} className={`lx-tr--clickable${selected ? ' is-selected' : ''}`} onClick={() => onTaskScopeChange?.(scope)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onTaskScopeChange?.(scope); } }}>
              <td><div className="lx-cell__main">{scope}</div><div className="lx-cell__sub">Job {task.jobs[0]?.id} – {task.jobs.at(-1)?.id}</div></td><td className="r">{task.jobs.length}</td><td className="r">{frames.toLocaleString('en-US')}</td><td className={`r${task.coverage < .95 ? ' is-warn' : ''}`}>{percent(task.coverage)}</td><td className="r">{task.candidateCount}</td><td><span className={`lx-badge${badgeTone(task.gate) ? ` lx-badge--${badgeTone(task.gate)}` : ''}`}>{task.gate === 'passed' ? 'Đạt' : statusLabel(task.gate)}</span></td>
            </tr>;
          })}
        </tbody></table></div>
      </section>

      <section className="lx-card lx-side">
        <div className="lx-card__head"><h2 className="lx-h2">Lỗi xác nhận theo loại</h2></div>
        <div className="lx-card__body lx-stack lx-stack--12">{categories.map(([label, count]) => <div className="lx-bar" key={label}><span>{label}</span><div className="lx-bar__t"><i style={{ width: `${count / maxCategory * 100}%` }} /></div><span className="lx-bar__n">{count}</span></div>)}</div>
      </section>
    </div>
  </>;
}
