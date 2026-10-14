'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import { hasDatasetPermission } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import { formatDateTime } from '@/lib/format';
import { getRun } from '@/lib/execution/api';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { SampleDataBadge } from '@/components/ui/SampleDataBadge';
import { ACTIVE_CALIBRATIONS, PERF_BENCHMARK_STREAM } from '@/lib/calibration/sample-data';
import {
  createEvaluation, getEffectivenessReport, getEvaluation, listEvaluations, listReferences, newIdempotencyKey, percent, sourceReasonLabel,
  type Evaluation, type MetricValue,
} from '@/lib/reports/api';

const EVALUATION_STATUS: Record<Evaluation['status'], { tone: string; label: string }> = {
  queued: { tone: 'info', label: 'Queued' },
  running: { tone: 'info', label: 'Running' },
  completed: { tone: 'success', label: 'Completed' },
  failed: { tone: 'danger', label: 'Failed' },
  insufficient_sample: { tone: 'warning', label: 'Chưa đủ mẫu' },
};

function badgeClass(tone: string) {
  return `lx-badge${tone ? ` lx-badge--${tone}` : ''}`;
}

function useEvaluationId(): number | null {
  const value = Number(useSearchParams().get('evaluation'));
  return Number.isInteger(value) && value > 0 ? value : null;
}

function useEvaluation(id: number | null) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['kpi-evaluation', session?.user.id, id],
    queryFn: ({ signal }) => getEvaluation(id!, signal),
    enabled: id !== null && !!session,
    retry: false,
    refetchInterval: (q) => q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 3000 : false,
  });
}

function metricText(m: MetricValue | undefined): { value: string; tone: string } {
  if (!m) return { value: '—', tone: '' };
  if (m.status === 'insufficient_sample') return { value: 'Chưa đủ mẫu', tone: 'is-warn' };
  if (m.status !== 'computed' || m.value === null || m.value === undefined) return { value: 'Not checked', tone: '' };
  return { value: percent(m.value) ?? '—', tone: '' };
}

/** Danh sách KPI evaluation và reference đã khoá của Dataset đang chọn (GET /api/evaluations/, /api/references/). */
function useScopeOptions() {
  const { session, datasetId } = useAuth();
  const canList = hasDatasetPermission(session, datasetId, (role) => ['qa_lead', 'super_admin', 'product_owner'].includes(role));
  const enabled = !!session && datasetId !== null && canList;
  const evaluations = useQuery({
    queryKey: ['kpi-evaluations', session?.user.id, datasetId],
    queryFn: ({ signal }) => listEvaluations(datasetId!, signal), enabled, retry: false,
  });
  const references = useQuery({
    queryKey: ['kpi-references', session?.user.id, datasetId],
    queryFn: ({ signal }) => listReferences(datasetId!, signal), enabled, retry: false,
  });
  return { enabled, datasetId, evaluations, references };
}

export function PerformanceHeader() {
  const id = useEvaluationId();
  const evaluation = useEvaluation(id);
  const ev = evaluation.data;
  const router = useRouter();
  const pathname = usePathname();
  const { enabled, datasetId, evaluations, references } = useScopeOptions();
  // undefined: theo reference của evaluation đang xem; null: mọi reference.
  const [referenceFilter, setReferenceFilter] = useState<number | null | undefined>(undefined);
  const reference = referenceFilter === undefined ? ev?.reference_id ?? null : referenceFilter;
  const rows = (evaluations.data?.results ?? []).filter((row) => reference === null || row.reference_id === reference);
  const show = (next: number) => router.replace(`${pathname}?evaluation=${next}`);
  const placeholder = (query: { isPending: boolean; isError: boolean }, empty: string) =>
    !enabled ? (datasetId === null ? 'Chưa chọn Dataset' : 'Không có quyền xem') : query.isPending ? 'Đang tải…' : query.isError ? 'Không tải được' : empty;
  return (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Performance Evaluation</h1>
        <p className="lx-lead">Đánh giá chất lượng của chính quy trình kiểm tra: mức thống nhất của reviewer, độ chính xác của candidate và lỗi còn sót. Luôn ghi kèm cỡ mẫu và phương pháp.</p>
      </div>
      <div className="lx-actions">
        <select className="lx-select lx-select--inline" aria-label="Phạm vi đánh giá" value={id ?? ''}
          disabled={!evaluations.isSuccess} title={evaluations.isError ? errorMessage(evaluations.error) : undefined}
          onChange={(event) => { if (event.target.value) show(Number(event.target.value)); }}>
          <option value="">{evaluations.isSuccess ? (rows.length ? 'Phạm vi: chọn evaluation' : 'Chưa có evaluation') : `Phạm vi: ${placeholder(evaluations, '')}`}</option>
          {id !== null && ev && !rows.some((row) => row.id === id) && <option value={id}>Quality Control Run #QC-{ev.run_id} · Evaluation #{id}</option>}
          {rows.map((row) => <option key={row.id} value={row.id}>Quality Control Run #QC-{row.run_id} · Evaluation #{row.id} · {formatDateTime(row.created_at)}</option>)}
        </select>
        <select className="lx-select lx-select--inline" aria-label="Benchmark" value={reference ?? ''}
          disabled={!references.isSuccess} title={references.isError ? errorMessage(references.error) : undefined}
          onChange={(event) => {
            const next = event.target.value ? Number(event.target.value) : null;
            setReferenceFilter(next);
            const first = evaluations.data?.results.find((row) => next === null || row.reference_id === next);
            if (first && first.id !== id) show(first.id);
          }}>
          <option value="">{references.isSuccess ? 'Mọi reference đã khoá' : `Reference: ${placeholder(references, '')}`}</option>
          {reference !== null && !references.data?.results.some((row) => row.id === reference) && <option value={reference}>Reference #{reference}</option>}
          {(references.data?.results ?? []).map((row) => <option key={row.id} value={row.id}>Reference #{row.id} · Snapshot #{row.snapshot_id} · {row.mapping_version}</option>)}
        </select>
      </div>
    </div>
  );
}

function EvaluationSource({ current }: { current: number | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const { session, datasetId } = useAuth();
  const [lookup, setLookup] = useState(current ? String(current) : '');
  const [runId, setRunId] = useState('');
  const [referenceId, setReferenceId] = useState('');
  const { references, evaluations } = useScopeOptions();
  const [scoreVersion, setScoreVersion] = useState('');
  const [key, setKey] = useState(newIdempotencyKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canCreate = hasDatasetPermission(session, datasetId, (role) => ['qa_lead', 'super_admin', 'product_owner'].includes(role));
  const show = (id: number) => router.replace(`${pathname}?evaluation=${id}`);
  const lookupId = Number(lookup);
  const run = Number(runId);
  const reference = Number(referenceId);
  const ready = run > 0 && reference > 0 && scoreVersion.trim() !== '' && !busy;

  async function create() {
    if (!ready) return;
    setBusy(true); setError(null);
    try {
      const detail = await getRun(run);
      const ev = await createEvaluation({ snapshot_id: detail.snapshot_id, run_id: run, reference_id: reference,
        score_version: scoreVersion.trim(), parameters: {} }, key);
      setKey(newIdempotencyKey());
      setLookup(String(ev.id));
      void evaluations.refetch();
      show(ev.id);
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  return (
    <section className="lx-card" aria-label="Nguồn đánh giá">
      <div className="lx-card__head"><h2 className="lx-h2">Nguồn đánh giá</h2><span className="lx-hint">KPI evaluation trên reference đã khoá</span></div>
      <div className="lx-card__body lx-grid lx-grid--2">
        <form className="lx-stack lx-stack--2" onSubmit={(e) => { e.preventDefault(); if (lookupId > 0) show(lookupId); }}>
          <div className="lx-field">
            <label className="lx-label" htmlFor="evaluation-id">Mã evaluation</label>
            <input id="evaluation-id" className="lx-input" inputMode="numeric" value={lookup} onChange={(e) => setLookup(e.target.value.replace(/\D/g, ''))} />
          </div>
          <div><button type="submit" className="lx-btn" disabled={!(lookupId > 0)}>Xem kết quả</button></div>
        </form>
        {canCreate ? (
          <form className="lx-stack lx-stack--2" onSubmit={(e) => { e.preventDefault(); void create(); }}>
            <div className="lx-grid lx-grid--2">
              <div className="lx-field">
                <label className="lx-label" htmlFor="evaluation-run">Quality Control Run</label>
                <input id="evaluation-run" className="lx-input" inputMode="numeric" value={runId} onChange={(e) => setRunId(e.target.value.replace(/\D/g, ''))} />
              </div>
              <div className="lx-field">
                <label className="lx-label" htmlFor="evaluation-reference">Reference đã khoá</label>
                <select id="evaluation-reference" className="lx-select" value={referenceId} disabled={!references.isSuccess}
                  title={references.isError ? errorMessage(references.error) : undefined} onChange={(e) => setReferenceId(e.target.value)}>
                  <option value="">{references.isPending ? 'Đang tải…' : references.isError ? 'Không tải được' : references.data?.results.length ? 'Chọn reference' : 'Chưa có reference đã khoá'}</option>
                  {(references.data?.results ?? []).map((row) => <option key={row.id} value={row.id}>Reference #{row.id} · Snapshot #{row.snapshot_id} · {row.mapping_version}</option>)}
                </select>
              </div>
            </div>
            <div className="lx-field">
              <label className="lx-label" htmlFor="evaluation-score">Score version</label>
              <input id="evaluation-score" className="lx-input" value={scoreVersion} onChange={(e) => setScoreVersion(e.target.value)} />
            </div>
            <div><button type="submit" className="lx-btn lx-btn--primary" disabled={!ready}>{busy ? 'Đang gửi…' : 'Chạy đánh giá'}</button></div>
            {error && <p role="alert" className="lx-callout lx-callout--compact lx-m-0">{error}</p>}
          </form>
        ) : (
          <p className="lx-muted lx-m-0 lx-text-13">Chỉ Quality Assurance Lead, Super Admin hoặc Product Owner được chạy đánh giá mới.</p>
        )}
      </div>
    </section>
  );
}

export function PerformanceBody() {
  const { session } = useAuth();
  const id = useEvaluationId();
  const evaluation = useEvaluation(id);
  const ev = evaluation.data;
  const report = useQuery({
    queryKey: ['kpi-report', session?.user.id, id],
    queryFn: ({ signal }) => getEffectivenessReport(id!, signal),
    enabled: !!ev && !['queued', 'running'].includes(ev.status),
    retry: false,
  });
  const rep = report.data;
  const metrics = rep?.metrics ?? ev?.metrics ?? undefined;
  const agreement = metrics?.['G-3'];
  const residual = metrics?.['G-4'];
  const precision = metrics?.['P-1'];
  const coverage = metrics?.['C-1'];
  const p = metricText(precision);
  const c = metricText(coverage);
  const coverageProgress = coverage?.status === 'computed' && coverage.value != null ? Math.max(0, Math.min(100, coverage.value * 100)) : null;
  const a = metricText(agreement);
  const r = metricText(residual);
  const waitingNote = id === null ? 'Chọn evaluation để xem' : evaluation.isLoading ? 'Đang tải…' : '';
  const streams = rep ? [
    { name: 'Kiểm tra ngẫu nhiên', q: rep.random_queue, use: 'Ước lượng chất lượng toàn dataset' },
    { name: 'Lấy mẫu theo rủi ro', q: rep.risk_queue, use: 'Tìm lỗi · không suy ra tỷ lệ chung' },
  ] : [];
  const num = (v: unknown) => (typeof v === 'number' ? v : 0);

  return (
    <>
      <EvaluationSource key={id ?? 'none'} current={id} />
      {evaluation.isError && (
        <div className="lx-callout lx-row" role="alert">
          <span>{errorMessage(evaluation.error)}</span>
          <button type="button" className="lx-btn lx-btn--sm" onClick={() => void evaluation.refetch()}>Thử lại</button>
        </div>
      )}
      {report.isError && (
        <div className="lx-callout lx-row" role="alert">
          <span>{errorMessage(report.error)}</span>
          <button type="button" className="lx-btn lx-btn--sm" onClick={() => void report.refetch()}>Thử lại</button>
        </div>
      )}
      {ev && (
        <div className="lx-row lx-text-13">
          <span className={badgeClass(EVALUATION_STATUS[ev.status].tone)}>{EVALUATION_STATUS[ev.status].label}</span>
          <span className="lx-muted">Evaluation <span className="lx-mono">#{ev.id}</span> · Snapshot <span className="lx-mono">#{ev.snapshot_id}</span> · Score {ev.score_version} · Leakage {ev.leakage_check ?? 'not_checked'} · {formatDateTime(ev.created_at)}</span>
          {rep && <span className="lx-muted">· Số liệu vận hành theo run <span className="lx-mono">#QC-{rep.source_run_id}</span> ({sourceReasonLabel(rep.source_reason)})</span>}
        </div>
      )}

      <div className="lx-grid lx-grid--4">
        <div className="lx-metric">
          <span className="lx-metric__k">Mức thống nhất của reviewer</span>
          <span className={`lx-metric__v${a.tone ? ` ${a.tone}` : ''}`}>{a.value}</span>
          <span className="lx-metric__n">{agreement ? `So với adjudicator trên ${agreement.sample_size} case · ${agreement.method}` : waitingNote}</span>
        </div>
        <div className="lx-metric">
          <span className="lx-metric__k">Độ chính xác của candidate</span>
          <span className={`lx-metric__v${p.tone ? ` ${p.tone}` : ''}`}>{p.value}</span>
          <span className="lx-metric__n">{precision ? `Trên ${precision.sample_size} Issue từ candidate đã có quyết định · ${precision.method}` : waitingNote}</span>
        </div>
        <div className="lx-metric">
          <span className="lx-metric__k">Tỷ lệ lỗi còn sót</span>
          <span className={`lx-metric__v${r.tone ? ` ${r.tone}` : ''}${residual?.status === 'computed' && (residual.value ?? 0) > 0.05 ? ' is-warn' : ''}`}>{r.value}</span>
          <span className="lx-metric__n">{residual ? `Từ ${residual.sample_size} frame kiểm tra ngẫu nhiên · ${residual.method}` : waitingNote}</span>
        </div>
        <div className="lx-metric">
          <span className="lx-metric__k">Benchmark coverage</span>
          <span className={`lx-metric__v${c.tone ? ` ${c.tone}` : ''}`}>{c.value}</span>
          {coverageProgress !== null && <div className="lx-progress" role="progressbar" aria-label="Benchmark coverage" aria-valuemin={0} aria-valuemax={100} aria-valuenow={coverageProgress}><i style={{ width: `${coverageProgress}%` }} /></div>}
          <span className="lx-metric__n">{coverage ? `${coverage.sample_size} / ${coverage.denominator} frame Snapshot có trong Benchmark · ${coverage.method}` : waitingNote}</span>
        </div>
      </div>

      <div className="lx-cols">
        <section className="lx-card lx-main" aria-label="Kết quả theo luồng lấy mẫu">
          <div className="lx-card__head"><h2 className="lx-h2">Kết quả theo luồng lấy mẫu</h2></div>
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-520">
              <thead><tr><th>Luồng lấy mẫu</th><th className="r">Số mẫu</th><th className="r">Lỗi đã xác nhận</th><th className="r">Tỷ lệ</th><th>Dùng để</th></tr></thead>
              <tbody>
                {id === null && <tr><td colSpan={5} className="lx-muted">Chọn evaluation để xem kết quả theo luồng lấy mẫu.</td></tr>}
                {id !== null && (evaluation.isLoading || report.isLoading) && <tr><td colSpan={5}>Đang tải…</td></tr>}
                {streams.map((s) => {
                  const reviewed = num(s.q.frames_reviewed);
                  const errors = num(s.q.open_issues);
                  return (
                    <tr key={s.name}>
                      <td><div className="lx-cell__main">{s.name}</div><div className="lx-cell__sub">{reviewed} / {num(s.q.frames_ranked)} frame xếp hạng đã review</div></td>
                      <td className="r">{reviewed}</td>
                      <td className="r">{errors}</td>
                      <td className="r">{reviewed > 0 ? percent(errors / reviewed) : <span className="lx-subtle">—</span>}</td>
                      <td className="lx-muted">{s.use}</td>
                    </tr>
                  );
                })}
                <tr>
                  <td><div className="lx-cell__main">{PERF_BENCHMARK_STREAM.name}</div><SampleDataBadge /></td>
                  <td className="r">{PERF_BENCHMARK_STREAM.n}</td><td className="r">{PERF_BENCHMARK_STREAM.errors}</td><td className="r">{PERF_BENCHMARK_STREAM.rate}</td>
                  <td className="lx-muted">{PERF_BENCHMARK_STREAM.use}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="lx-card__foot lx-stack lx-stack--2">
            <span>Hai luồng ngẫu nhiên và theo rủi ro được báo cáo riêng, không gộp. Lỗi đã xác nhận là issue chưa đóng trong các frame đã review.</span>
            {/* TODO(backend): luồng Benchmark cần API benchmark (GET /api/benchmarks/). */}
            <NotConnectedNotice detail="Dòng Benchmark chưa có API" />
          </div>
        </section>
        <section className="lx-card lx-side" aria-label="Việc hiệu chỉnh đang chạy">
          <div className="lx-card__head"><h2 className="lx-h2">Việc hiệu chỉnh đang chạy</h2><SampleDataBadge /><Link className="lx-link lx-text-13" href="/calibration/calibration">Mở Calibration</Link></div>
          {/* TODO(backend): GET /api/calibration/reviewers/, GET /api/calibration/models/ */}
          <div className="lx-card__body"><NotConnectedNotice /></div>
          <ul className="lx-list">
            {ACTIVE_CALIBRATIONS.map((item) => (
              <li key={item.name}>
                {item.progress ? (
                  <>
                    <div className="lx-row lx-row--between"><span className="lx-cell__main">{item.name}</span><span className="lx-num">{item.progress.label}</span></div>
                    <div className="lx-progress lx-mt-6"><i style={{ width: `${item.progress.pct}%` }} /></div>
                  </>
                ) : (
                  <><div className="lx-cell__main">{item.name}</div><div className="lx-cell__sub">{item.sub}</div></>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
