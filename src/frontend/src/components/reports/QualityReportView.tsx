'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import { errorMessage } from '@/lib/api/errors';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { ReportRunPicker, useSelectedRunId } from '@/components/reports/ReportRunPicker';
import { useDatasets, useSnapshot } from '@/lib/snapshots/queries';
import { useRunGate, useRunReport } from '@/lib/reports/queries';
import {
  createReportExport, EXPORT_FORMATS, EXPORT_STATUS_LABELS, formatDate, ISSUE_FAMILY_LABELS, newIdempotencyKey,
  OPEN_CONFIRMED_STATES, percent, requiredCoverage, sourceReasonLabel,
  type GateResult, type ReportExport, type ReportExportFormat, type RunReport,
} from '@/lib/reports/api';

type Tab = 'summary' | 'class' | 'cause';
const TABS: ReadonlyArray<[Tab, string]> = [['summary', 'Tóm tắt'], ['class', 'Theo lớp và loại hình'], ['cause', 'Nguyên nhân gốc']];
const DASH = <span className="lx-subtle">—</span>;

const GATE_BADGE: Record<GateResult['status'], { tone: string; label: string }> = {
  failed: { tone: 'danger', label: 'Release blocked' },
  passed: { tone: 'success', label: 'Gate passed' },
  not_checked: { tone: '', label: 'Gate not checked' },
};

function badgeClass(tone: string) {
  return `lx-badge${tone ? ` lx-badge--${tone}` : ''}`;
}

/** Tên Dataset và số task/job của run lấy từ snapshot thật của báo cáo. */
function useReportScope(report: RunReport | undefined) {
  const { session } = useAuth();
  const snapshot = useSnapshot(session?.user.id, report?.snapshot_id ?? null);
  const datasets = useDatasets(session?.user.id);
  const datasetId = snapshot.data?.dataset_id ?? null;
  const dataset = datasets.data?.pages.flatMap((p) => p.results ?? []).find((d) => d.id === datasetId);
  const jobs = snapshot.data?.jobs ?? [];
  return {
    datasetName: dataset ? dataset.name : datasetId !== null ? `Dataset #${datasetId}` : null,
    tasks: snapshot.data ? new Set(jobs.map((j) => j.cvat_task_id)).size : null,
    jobs: snapshot.data ? jobs.length : null,
  };
}

function ExportStatus({ exports }: { exports: ReportExport[] }) {
  if (exports.length === 0) return null;
  return (
    <span className="lx-hint" aria-live="polite">
      {exports.map((e, i) => (
        <React.Fragment key={e.id}>
          {i > 0 && ' · '}
          {e.format.toUpperCase()}:{' '}
          {e.status === 'completed' && e.download_url
            ? <a className="lx-link" href={e.download_url} target="_blank" rel="noopener noreferrer">Tải xuống</a>
            : <>{EXPORT_STATUS_LABELS[e.status]}{e.error ? ` (${e.error})` : ''}</>}
        </React.Fragment>
      ))}
    </span>
  );
}

export function QualityReportHeader() {
  const runId = useSelectedRunId();
  const { session } = useAuth();
  const client = useQueryClient();
  const report = useRunReport(runId);
  const gate = useRunGate(runId);
  const scope = useReportScope(report.data);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [requested, setRequested] = useState<ReportExport | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    const onPointer = (e: MouseEvent) => { if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onPointer);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onPointer); };
  }, [open]);

  async function requestExport(format: ReportExportFormat) {
    if (runId === null) return;
    setOpen(false); setBusy(true); setExportError(null); setRequested(null);
    try {
      const created = await createReportExport(runId, format, newIdempotencyKey());
      setRequested(created);
      await client.invalidateQueries({ queryKey: ['run-report', session?.user.id, runId] });
    } catch (err) { setExportError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  const data = report.data;
  const badge = gate.data ? GATE_BADGE[gate.data.status] : null;
  const created = formatDate(data?.generated_at);
  return (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Quality Report</h1>
        <p className="lx-lead">
          {data
            ? <>{scope.datasetName ?? `Snapshot #${data.snapshot_id}`} · Quality Control Run <span className="lx-mono">#QC-{data.run_id}</span>{created ? ` · tạo ngày ${created}` : ''}. </>
            : runId === null ? 'Chọn Quality Control Run để xem báo cáo. ' : null}
          Báo cáo luôn ghi rõ phạm vi, nguồn Ground Truth, coverage và những phần chưa đủ dữ liệu.
        </p>
      </div>
      <div className="lx-actions lx-actions--rel" ref={menuRef}>
        {badge && <span className={badgeClass(badge.tone)}>{badge.label}</span>}
        <button type="button" className="lx-btn" aria-haspopup="menu" aria-expanded={open} disabled={runId === null || busy} onClick={() => setOpen(!open)}>
          {busy ? 'Đang gửi…' : 'Xuất báo cáo'}
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 4.5 6 7.5 9 4.5" /></svg>
        </button>
        {open && (
          <div className="lx-menu lx-menu--end lx-menu--right" role="menu">
            {EXPORT_FORMATS.map((f) => (
              <button key={f.key} type="button" className="lx-menu__item" role="menuitem" onClick={() => void requestExport(f.key)}>
                <span className="lx-menu__t">{f.label}</span><span className="lx-menu__d">{f.note}</span>
              </button>
            ))}
          </div>
        )}
        {requested && (
          <span className="lx-hint" aria-live="polite">
            Server đã nhận yêu cầu xuất {requested.format.toUpperCase()} <span className="lx-mono">#{requested.id}</span>: {EXPORT_STATUS_LABELS[requested.status]}.
          </span>
        )}
        {exportError && <span className="lx-hint" role="alert">{exportError}</span>}
        {data && <ExportStatus exports={data.exports} />}
      </div>
    </div>
  );
}

function Metric({ label, value, note, tone = '' }: { label: string; value: React.ReactNode; note: React.ReactNode; tone?: string }) {
  return (
    <div className="lx-metric">
      <span className="lx-metric__k">{label}</span>
      <span className={`lx-metric__v${tone ? ` ${tone}` : ''}`}>{value}</span>
      <span className="lx-metric__n">{note}</span>
    </div>
  );
}

function ReportMetrics({ report, gate, gateError }: { report: RunReport; gate: GateResult | undefined; gateError: boolean }) {
  const scope = useReportScope(report);
  const m = report.metrics;
  const coverage = requiredCoverage(report.engine_coverage);
  const coverageRule = gate?.conditions.find((c) => c.name === 'coverage');
  const critical = gate?.conditions.find((c) => c.name === 'open_critical_issues');
  const rework = gate?.conditions.find((c) => c.name === 'rework_verified');
  const openConfirmed = OPEN_CONFIRMED_STATES.reduce((sum, s) => sum + (m.issues_by_state[s] ?? 0), 0);
  const gateNote = gateError ? 'Không tải được Quality Gate' : 'Đang tải Quality Gate…';
  let coverageNote = gateNote;
  if (coverageRule) coverageNote = `Ngưỡng yêu cầu ${percent(coverageRule.threshold, 0)}`;
  else if (coverage === null) coverageNote = 'Chưa có đơn vị đủ điều kiện';
  else if (gate) coverageNote = 'Engine bắt buộc';
  let criticalNote = gateNote;
  if (critical && critical.observed !== null && critical.observed !== undefined) criticalNote = `Trong đó ${critical.observed} nghiêm trọng`;
  else if (gate) criticalNote = 'Chưa đủ dữ liệu lỗi nghiêm trọng';
  let reworkNote = gateNote;
  if (rework) reworkNote = 'Theo điều kiện Rework của Quality Gate';
  else if (gate) reworkNote = 'Server chưa trả điều kiện Rework';
  return (
    <div className="lx-grid lx-grid--4">
      <Metric label="Frame trong phạm vi" value={m.frames_total.toLocaleString('en-US')}
        note={scope.tasks !== null ? `${scope.tasks} task · ${scope.jobs} job` : `Snapshot #${report.snapshot_id}`} />
      <Metric label="Coverage" value={percent(coverage) ?? DASH} note={coverageNote}
        tone={coverage !== null && coverageRule && coverage < coverageRule.threshold ? 'is-warn' : ''} />
      <Metric label="Lỗi đã xác nhận chưa đóng" value={openConfirmed.toLocaleString('en-US')} note={criticalNote}
        tone={openConfirmed > 0 ? 'is-bad' : ''} />
      <Metric label="Rework hoàn thành" value={(rework && percent(rework.observed)) ?? DASH} note={reworkNote} />
    </div>
  );
}

function ExcludedNotice({ report }: { report: RunReport }) {
  const excluded = report.engine_coverage.filter((e) => e.excluded > 0);
  if (excluded.length === 0) return null;
  const reasons = (r: Record<string, number>) =>
    Object.entries(r).filter(([k]) => k === 'not_applicable' || k === 'not_triggered').map(([k, v]) => `${k} ${v}`).join(', ');
  return (
    <p className="lx-callout lx-callout--warning lx-callout--compact lx-m-0">
      Coverage đã loại khỏi mẫu số:{' '}
      {excluded.map((e) => `${e.engine} ${e.excluded} ${e.unit} (${reasons(e.not_checked_reasons) || 'không rõ lý do'}, applicability ${e.applicability_version})`).join('; ')}.
    </p>
  );
}

function FamilyBars({ byFamily }: { byFamily: Record<string, number> }) {
  const rows = Object.entries(byFamily).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);
  const max = rows[0]?.[1] ?? 0;
  if (rows.length === 0) return <p className="lx-muted lx-m-0 lx-text-13">Run này chưa có issue nào.</p>;
  return (
    <>
      {rows.map(([family, count]) => (
        <div key={family} className="lx-bar">
          <span>{ISSUE_FAMILY_LABELS[family] ?? family}</span>
          <div className="lx-bar__t"><i style={{ width: `${Math.round((count / max) * 100)}%` }} /></div>
          <span className="lx-bar__n">{count}</span>
        </div>
      ))}
    </>
  );
}

export function QualityReportBody() {
  const runId = useSelectedRunId();
  const report = useRunReport(runId);
  const gate = useRunGate(runId);
  const [tab, setTab] = useState<Tab>('summary');
  const data = report.data;
  const viaSource = data && data.source_run_id !== data.run_id;
  return (
    <>
      <section className="lx-card" aria-label="Chọn Quality Control Run">
        <div className="lx-card__body"><ReportRunPicker /></div>
      </section>
      {runId === null && <p className="lx-muted lx-m-0">Chọn Quality Control Run để xem báo cáo.</p>}
      {report.isLoading && <p className="lx-m-0">Đang tải báo cáo…</p>}
      {report.isError && (
        <div className="lx-row" role="alert">
          <span>{errorMessage(report.error)}</span>
          <button type="button" className="lx-btn lx-btn--sm" onClick={() => void report.refetch()}>Thử lại</button>
        </div>
      )}
      {data && (
        <>
          {viaSource && (
            <p className="lx-callout lx-callout--warning lx-callout--compact lx-m-0">
              Số liệu tính theo run <span className="lx-mono">#QC-{data.source_run_id}</span>: {sourceReasonLabel(data.source_reason)}.
            </p>
          )}
          <ReportMetrics report={data} gate={gate.data} gateError={gate.isError} />
          {gate.isError && (
            <div className="lx-row" role="alert">
              <span>Không tải được Quality Gate: {errorMessage(gate.error)}</span>
              <button type="button" className="lx-btn lx-btn--sm" onClick={() => void gate.refetch()}>Thử lại</button>
            </div>
          )}
          <ExcludedNotice report={data} />

          <section className="lx-card" aria-label="Chi tiết báo cáo">
            <div className="lx-tabs lx-tabs--inset" role="tablist">
              {TABS.map(([key, label]) => (
                <button key={key} type="button" role="tab" aria-selected={tab === key} className={`lx-tab${tab === key ? ' is-active' : ''}`} onClick={() => setTab(key)}>{label}</button>
              ))}
            </div>

            {tab === 'summary' && (
              <div className="lx-card__body lx-cols">
                <div className="lx-main lx-stack lx-stack--3">
                  <h2 className="lx-h2">Lỗi đã xác nhận theo loại</h2>
                  <span className="lx-hint">Tổng {data.metrics.issues_total} issue của run, đếm theo loại lỗi (server chưa tách theo trạng thái).</span>
                  <FamilyBars byFamily={data.metrics.issues_by_family} />
                </div>
                <div className="lx-side lx-stack lx-stack--3">
                  <h2 className="lx-h2">Cặp nhãn bị nhầm nhiều nhất</h2>
                  {/* TODO(backend): RunReport chưa có cặp nhãn bị nhầm (contract MBE-03 không có trường này). */}
                  <NotConnectedNotice detail="Báo cáo của run chưa có số liệu cặp nhãn bị nhầm" />
                </div>
              </div>
            )}

            {tab === 'class' && (
              <>
                <div className="lx-card__body">
                  {/* TODO(backend): RunReport chưa có chỉ số theo lớp (Intersection over Union, Precision, Recall, lỗi theo lớp). */}
                  <NotConnectedNotice detail="Báo cáo của run chưa có chỉ số theo lớp và loại hình" />
                </div>
                <div className="lx-scroll">
                  <table className="lx-table lx-table--min-700">
                    <thead><tr><th>Lớp</th><th>Loại hình</th><th className="r">Intersection over Union</th><th className="r">Precision</th><th className="r">Recall</th><th className="r">Lỗi đã xác nhận</th></tr></thead>
                    <tbody><tr><td colSpan={6} className="lx-muted">Chưa có dữ liệu theo lớp từ server.</td></tr></tbody>
                  </table>
                </div>
                <div className="lx-card__foot"><span>Lớp kém nhất được tô màu cảnh báo. Loại hình chưa có Ground Truth ghi là chưa đánh giá, không ghi là đạt.</span></div>
              </>
            )}

            {tab === 'cause' && (
              <>
                <div className="lx-card__body">
                  {/* TODO(backend): RunReport chưa có nhóm nguyên nhân gốc và đề xuất. */}
                  <NotConnectedNotice detail="Báo cáo của run chưa có phân tích nguyên nhân gốc" />
                </div>
                <div className="lx-scroll">
                  <table className="lx-table lx-table--min-640">
                    <thead><tr><th>Nguyên nhân gốc</th><th className="r">Số lỗi</th><th>Đề xuất</th></tr></thead>
                    <tbody><tr><td colSpan={3} className="lx-muted">Chưa có dữ liệu nguyên nhân gốc từ server.</td></tr></tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        </>
      )}
    </>
  );
}
