'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import { hasDatasetPermission } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import { ReportRunPicker, useSelectedRunId } from '@/components/reports/ReportRunPicker';
import { useRunGate, useRunReport } from '@/lib/reports/queries';
import {
  approveRelease, createWaiver, decideWaiver, GATE_CONDITION_LABELS, newIdempotencyKey, percent, sourceReasonLabel,
  WAIVABLE_CONDITIONS, type GateCondition, type GateConditionName, type GateResult, type Release, type Waiver,
} from '@/lib/reports/api';

const STATUS_BADGE: Record<GateCondition['status'], { tone: string; label: string }> = {
  passed: { tone: 'success', label: 'Đạt' },
  failed: { tone: 'danger', label: 'Chưa đạt' },
  not_checked: { tone: '', label: 'Not checked' },
  waived: { tone: 'info', label: 'Waived' },
};

const GATE_BADGE: Record<GateResult['status'], { tone: string; label: string }> = {
  passed: { tone: 'success', label: 'Passed' },
  failed: { tone: 'danger', label: 'Blocked' },
  not_checked: { tone: '', label: 'Not checked' },
};

const ACTION_TEXT: Record<GateConditionName, string> = {
  coverage: 'Chạy bổ sung hoặc xin waiver',
  open_critical_issues: 'Sửa và xác minh',
  rework_verified: '',
  residual: 'Review lát kiểm tra ngẫu nhiên',
  agreement: 'Hiệu chỉnh reviewer hoặc xin waiver',
};

function badgeClass(tone: string) {
  return `lx-badge${tone ? ` lx-badge--${tone}` : ''}`;
}

function ResultCell({ c }: { c: GateCondition }) {
  if (c.observed === null || c.observed === undefined) return <span className="lx-subtle">Chưa đủ dữ liệu</span>;
  const strong = c.status === 'failed' ? 'is-bad lx-strong' : 'lx-strong';
  if (c.name === 'open_critical_issues') {
    return <><span className={strong}>{c.observed}</span> chưa đóng · ngưỡng {c.threshold}</>;
  }
  const limit = c.name === 'residual' ? 'ngưỡng tối đa' : 'ngưỡng';
  return <><span className={strong}>{percent(c.observed)}</span> / {limit} {percent(c.threshold, 0)}</>;
}

function ActionCell({ c }: { c: GateCondition }) {
  if (c.status === 'waived') return <span className="lx-muted">Waiver <span className="lx-mono">#{c.waiver_id}</span> đã duyệt</span>;
  if (c.status === 'passed') return <span className="lx-subtle">—</span>;
  if (c.name === 'rework_verified') return <Link className="lx-link" href="/review/rework">Mở Rework Tracking</Link>;
  if (c.status === 'not_checked') return <>{WAIVABLE_CONDITIONS.includes(c.name) ? 'Bổ sung dữ liệu hoặc xin waiver' : 'Bổ sung dữ liệu'}</>;
  return <>{ACTION_TEXT[c.name]}</>;
}

export function QualityGateHeader() {
  const runId = useSelectedRunId();
  const gate = useRunGate(runId);
  const badge = gate.data ? GATE_BADGE[gate.data.status] : null;
  return (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Quality Gate</h1>
        <p className="lx-lead">
          Điều kiện bắt buộc trước khi phát hành{runId ? <> theo Quality Control Run <span className="lx-mono">#QC-{runId}</span></> : null}.
          {' '}Chỉ phát hành khi mọi điều kiện đạt hoặc có waiver được người có thẩm quyền duyệt.
        </p>
      </div>
      <div className="lx-actions">{badge && <span className={badgeClass(badge.tone)}>{badge.label}</span>}</div>
    </div>
  );
}

function defaultExpiry(): string {
  return new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString().slice(0, 10);
}

function WaiverRequestForm({ runId, gate, canRequest }: { runId: number; gate: GateResult; canRequest: boolean }) {
  const { session } = useAuth();
  const client = useQueryClient();
  const open = gate.conditions.filter((c) => WAIVABLE_CONDITIONS.includes(c.name) && c.status !== 'passed' && c.status !== 'waived');
  const [condition, setCondition] = useState<GateConditionName | ''>('');
  const [reason, setReason] = useState('');
  const [evidence, setEvidence] = useState('');
  const [expires, setExpires] = useState(defaultExpiry);
  const [key, setKey] = useState(newIdempotencyKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Waiver | null>(null);
  const chosen = condition && open.some((c) => c.name === condition) ? condition : open[0]?.name ?? '';
  const ready = canRequest && !!chosen && reason.trim() !== '' && evidence.trim() !== '' && expires !== '' && !busy;

  async function submit() {
    if (!ready || !chosen) return;
    setBusy(true); setError(null); setCreated(null);
    try {
      const waiver = await createWaiver({
        run_id: runId, condition: chosen, reason: reason.trim(), evidence: evidence.trim(),
        expires_at: new Date(`${expires}T23:59:59`).toISOString(),
      }, key);
      setCreated(waiver); setReason(''); setEvidence(''); setKey(newIdempotencyKey());
      await client.invalidateQueries({ queryKey: ['report-gate', session?.user.id, runId] });
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  return (
    <div className="lx-stack lx-stack--2 lx-stack--divided">
      <span className="lx-label">Hoặc xin waiver cho điều kiện chưa đạt</span>
      {open.length === 0 && <p className="lx-muted lx-m-0 lx-text-13">Không có điều kiện nào cần waiver. Chỉ Coverage và Mức thống nhất của reviewer được waiver.</p>}
      <div className="lx-field">
        <label className="lx-label" htmlFor="waiver-condition">Điều kiện</label>
        <select id="waiver-condition" className="lx-select" value={chosen} disabled={open.length === 0} onChange={(e) => setCondition(e.target.value as GateConditionName)}>
          {open.map((c) => <option key={c.name} value={c.name}>{GATE_CONDITION_LABELS[c.name]}</option>)}
        </select>
      </div>
      <div className="lx-field">
        <label className="lx-label" htmlFor="waiver-reason">Lý do (bắt buộc)</label>
        <textarea id="waiver-reason" className="lx-textarea" value={reason} onChange={(e) => setReason(e.target.value)}
          placeholder="Nêu rõ người chịu trách nhiệm và căn cứ. Mọi waiver đều được ghi vào nhật ký kiểm toán." />
      </div>
      <div className="lx-field">
        <label className="lx-label" htmlFor="waiver-evidence">Bằng chứng (bắt buộc)</label>
        <textarea id="waiver-evidence" className="lx-textarea" value={evidence} onChange={(e) => setEvidence(e.target.value)}
          placeholder="Liên kết hoặc mô tả căn cứ đi kèm." />
      </div>
      <div className="lx-field">
        <label className="lx-label" htmlFor="waiver-expires">Hiệu lực đến</label>
        <input id="waiver-expires" type="date" className="lx-input" value={expires} onChange={(e) => setExpires(e.target.value)} />
      </div>
      <button type="button" className="lx-btn" disabled={!ready} onClick={() => void submit()}>{busy ? 'Đang gửi…' : 'Gửi xin waiver'}</button>
      {!canRequest && <span className="lx-hint">Chỉ Reviewer hoặc Quality Assurance Lead của Dataset được xin waiver.</span>}
      {error && <p role="alert" className="lx-callout lx-callout--compact lx-m-0">{error}</p>}
      {created && (
        <p className="lx-callout lx-callout--info lx-callout--compact lx-m-0" aria-live="polite">
          Server đã ghi waiver <span className="lx-mono">#{created.id}</span> ({GATE_CONDITION_LABELS[created.condition]}), đang chờ một Quality Assurance Lead khác duyệt.
        </p>
      )}
    </div>
  );
}

function WaiverDecisionForm({ runId }: { runId: number }) {
  const { session } = useAuth();
  const client = useQueryClient();
  const [waiverId, setWaiverId] = useState('');
  const [reason, setReason] = useState('');
  const [key, setKey] = useState(newIdempotencyKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [decided, setDecided] = useState<Waiver | null>(null);
  const id = Number(waiverId);
  const ready = Number.isInteger(id) && id > 0 && reason.trim() !== '' && !busy;

  async function decide(approved: boolean) {
    if (!ready) return;
    setBusy(true); setError(null); setDecided(null);
    try {
      const waiver = await decideWaiver(id, { approved, reason: reason.trim() }, key);
      setDecided(waiver); setReason(''); setKey(newIdempotencyKey());
      await client.invalidateQueries({ queryKey: ['report-gate', session?.user.id, runId] });
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  return (
    <div className="lx-stack lx-stack--2 lx-stack--divided">
      <span className="lx-label">Duyệt waiver</span>
      {/* Contract chưa có GET danh sách waiver chờ duyệt, nên người duyệt nhập mã waiver do người đề nghị gửi. */}
      <div className="lx-field">
        <label className="lx-label" htmlFor="waiver-id">Mã waiver</label>
        <input id="waiver-id" className="lx-input" inputMode="numeric" value={waiverId} onChange={(e) => setWaiverId(e.target.value.replace(/\D/g, ''))} />
      </div>
      <div className="lx-field">
        <label className="lx-label" htmlFor="waiver-decision-reason">Lý do quyết định (bắt buộc)</label>
        <textarea id="waiver-decision-reason" className="lx-textarea" value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <div className="lx-row">
        <button type="button" className="lx-btn" disabled={!ready} onClick={() => void decide(true)}>Duyệt waiver</button>
        <button type="button" className="lx-btn" disabled={!ready} onClick={() => void decide(false)}>Từ chối waiver</button>
      </div>
      <span className="lx-hint">{session?.roles.some(r => r.role === 'super_admin' && r.dataset_id === null)
        ? 'Super Admin có thể duyệt cả waiver do chính mình đề nghị.'
        : 'Người duyệt phải khác người đề nghị.'}</span>
      {error && <p role="alert" className="lx-callout lx-callout--compact lx-m-0">{error}</p>}
      {decided && (
        <p className="lx-callout lx-callout--info lx-callout--compact lx-m-0" aria-live="polite">
          Server đã ghi quyết định cho waiver <span className="lx-mono">#{decided.id}</span>: {decided.status === 'approved' ? 'duyệt' : decided.status === 'rejected' ? 'từ chối' : decided.status}.
        </p>
      )}
    </div>
  );
}

function ReleaseApproveForm({ runId, gate }: { runId: number; gate: GateResult | undefined }) {
  const { session } = useAuth();
  const client = useQueryClient();
  const report = useRunReport(runId);
  const releaseId = report.data?.release_id ?? null;
  const canApprove = session?.roles.some((r) => r.role === 'product_owner' || r.role === 'super_admin') ?? false;
  const [note, setNote] = useState('');
  const [key, setKey] = useState(newIdempotencyKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [approved, setApproved] = useState<Release | null>(null);
  const ready = releaseId !== null && canApprove && !busy;

  async function approve() {
    if (!ready || releaseId === null) return;
    setBusy(true); setError(null); setApproved(null);
    try {
      const release = await approveRelease(releaseId, note.trim(), key);
      setApproved(release); setNote(''); setKey(newIdempotencyKey());
      await Promise.all([
        client.invalidateQueries({ queryKey: ['run-report', session?.user.id, runId] }),
        client.invalidateQueries({ queryKey: ['releases', session?.user.id] }),
        client.invalidateQueries({ queryKey: ['report-gate', session?.user.id, runId] }),
      ]);
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  return (
    <>
      {report.isLoading && <span className="lx-hint">Đang tải release của run…</span>}
      {report.isError && (
        <span className="lx-hint" role="alert">
          {errorMessage(report.error)} <button type="button" className="lx-btn lx-btn--sm" onClick={() => void report.refetch()}>Thử lại</button>
        </span>
      )}
      {releaseId !== null && (
        <div className="lx-field">
          <label className="lx-label" htmlFor="release-note">Ghi chú phê duyệt release <span className="lx-mono">#{releaseId}</span></label>
          <textarea id="release-note" className="lx-textarea" value={note} disabled={!canApprove} onChange={(e) => setNote(e.target.value)} />
        </div>
      )}
      <button type="button" className="lx-btn lx-btn--primary lx-btn--block" disabled={!ready} onClick={() => void approve()}>
        {busy ? 'Đang gửi…' : 'Phê duyệt phát hành'}
      </button>
      {report.data && releaseId === null && (
        <span className="lx-hint">Server chưa có release chờ duyệt cho run này. Contract chưa có endpoint tạo release, nên chưa thể phê duyệt từ đây.</span>
      )}
      {releaseId !== null && !canApprove && <span className="lx-hint">Chỉ Product Owner hoặc Super Admin được phê duyệt phát hành.</span>}
      {releaseId !== null && gate && gate.status !== 'passed' && (
        <span className="lx-hint">Server sẽ từ chối nếu gate chưa đạt và không có waiver đã duyệt.</span>
      )}
      {error && <p role="alert" className="lx-callout lx-callout--compact lx-m-0">{error}</p>}
      {approved && (
        <p className="lx-callout lx-callout--info lx-callout--compact lx-m-0" aria-live="polite">
          Server đã ghi phê duyệt release <span className="lx-mono">#{approved.id}</span> ({approved.version_tag}).
        </p>
      )}
    </>
  );
}

export function QualityGateBody() {
  const { session, datasetId } = useAuth();
  const runId = useSelectedRunId();
  const gate = useRunGate(runId);
  const data = gate.data;
  const count = (s: GateCondition['status']) => data?.conditions.filter((c) => c.status === s).length ?? 0;
  const summary = data
    ? [`${count('passed')} đạt`, `${count('failed')} chưa đạt`, count('not_checked') ? `${count('not_checked')} chưa kiểm tra` : '',
      count('waived') ? `${count('waived')} có waiver` : ''].filter(Boolean).join(' · ')
    : '';
  const blocking = count('failed') + count('not_checked');
  const canRequest = hasDatasetPermission(session, datasetId, (role) => role === 'reviewer' || role === 'qa_lead');
  const canDecide = hasDatasetPermission(session, datasetId, (role) => role === 'qa_lead');
  const viaOrigin = data && (data.source_run_id !== data.run_id || data.source_reason !== 'selected_final');

  return (
    <div className="lx-cols">
      <section className="lx-card lx-main" aria-label="Điều kiện phát hành">
        <div className="lx-card__head"><h2 className="lx-h2">Điều kiện phát hành</h2>{summary && <span className="lx-hint">{summary}</span>}</div>
        <div className="lx-card__body"><ReportRunPicker /></div>
        {runId === null && <div className="lx-card__body lx-muted">Chọn Quality Control Run để xem kết quả gate.</div>}
        {gate.isLoading && <div className="lx-card__body">Đang tải kết quả gate…</div>}
        {gate.isError && (
          <div className="lx-card__body lx-row" role="alert">
            <span>{errorMessage(gate.error)}</span>
            <button type="button" className="lx-btn lx-btn--sm" onClick={() => void gate.refetch()}>Thử lại</button>
          </div>
        )}
        {data && (
          <>
            {viaOrigin && (
              <div className="lx-card__body">
                <p className="lx-callout lx-callout--warning lx-callout--compact lx-m-0">
                  Gate tính theo run <span className="lx-mono">#QC-{data.source_run_id}</span>: {sourceReasonLabel(data.source_reason)}.
                </p>
              </div>
            )}
            <div className="lx-scroll">
              <table className="lx-table lx-table--min-720">
                <thead><tr><th>Điều kiện</th><th>Kết quả</th><th>Trạng thái</th><th>Cần làm</th></tr></thead>
                <tbody>
                  {data.conditions.map((c) => {
                    const b = STATUS_BADGE[c.status];
                    return (
                      <tr key={c.name}>
                        <td className="lx-cell__main">{GATE_CONDITION_LABELS[c.name] ?? c.name}</td>
                        <td className="lx-muted"><ResultCell c={c} />{c.reason ? <div className="lx-cell__sub">{sourceReasonLabel(c.reason)}</div> : null}</td>
                        <td><span className={badgeClass(b.tone)}>{b.label}</span></td>
                        <td><ActionCell c={c} /></td>
                      </tr>
                    );
                  })}
                  {data.conditions.length === 0 && <tr><td colSpan={4}>Server chưa trả điều kiện gate cho run này.</td></tr>}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <aside className="lx-card lx-side" aria-label="Phê duyệt phát hành">
        <div className="lx-card__head"><h2 className="lx-h2">Phê duyệt phát hành</h2></div>
        <div className="lx-card__body lx-stack">
          <p className="lx-muted lx-m-0 lx-text-13">
            {data && data.status === 'passed' && 'Mọi điều kiện đã đạt. Hệ thống không tự quyết định phát hành.'}
            {data && data.status !== 'passed' && `Chưa thể phát hành vì còn ${blocking} điều kiện chưa đạt hoặc chưa kiểm tra. Hệ thống không tự quyết định phát hành.`}
            {!data && 'Hệ thống không tự quyết định phát hành.'}
          </p>
          {runId !== null
            ? <ReleaseApproveForm key={`approve-${runId}`} runId={runId} gate={data} />
            : <button type="button" className="lx-btn lx-btn--primary lx-btn--block" disabled>Phê duyệt phát hành</button>}
          {runId !== null && data && <WaiverRequestForm key={runId} runId={runId} gate={data} canRequest={canRequest} />}
          {runId !== null && data && canDecide && <WaiverDecisionForm key={`decide-${runId}`} runId={runId} />}
        </div>
      </aside>
    </div>
  );
}
