'use client';

import React, { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import { errorMessage } from '@/lib/api/errors';
import { rolesForDataset } from '@/lib/auth/roles';
import {
  createRework,
  getRework,
  getReworkCurrentRevision,
  getReworks,
  submitRework,
  verifyRework,
  type ReworkCreateInput,
  type ReworkItem,
  type ReworkStatus,
  type ReworkVerificationInput,
} from '@/lib/review/rework-api';

type ReworkTabKey = 'todo' | 'verify' | 'closed';

const TAB_CONFIG: Array<{
  key: ReworkTabKey;
  label: string;
  tip: string;
  statuses: ReworkStatus[];
}> = [
  { key: 'todo', label: 'Chờ sửa', tip: 'Mở yêu cầu trên CVAT', statuses: ['fix_pending', 'reopened'] },
  { key: 'verify', label: 'Chờ xác minh', tip: 'Xác minh revision mới', statuses: ['recheck_pending'] },
  { key: 'closed', label: 'Đã đóng', tip: 'Xem yêu cầu trên CVAT', statuses: ['resolved'] },
];

const SEVERITY = {
  critical: { label: 'Nghiêm trọng', tone: 'danger' },
  medium: { label: 'Trung bình', tone: 'warning' },
  minor: { label: 'Nhẹ', tone: '' },
} as const;

function countOf(counts: Record<string, number> | undefined, status: ReworkStatus) {
  return counts?.[status] ?? 0;
}

function makeRequestKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `rework-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function ReworkCreatePanel({ onCreated }: { onCreated: (id: number) => void }) {
  const [open, setOpen] = useState(false);
  const [issueId, setIssueId] = useState('');
  const [annotatorId, setAnnotatorId] = useState('');
  const [instruction, setInstruction] = useState('');
  const [dueAt, setDueAt] = useState('');
  const [severity, setSeverity] = useState<ReworkCreateInput['severity']>('medium');
  const [cvatLink, setCvatLink] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const requestRef = useRef<{ fingerprint: string; key: string } | null>(null);

  const mutation = useMutation({
    mutationFn: ({ body, key }: { body: ReworkCreateInput; key: string }) => createRework(body, key),
    retry: false,
    onSuccess: (data) => {
      setValidationError(null);
      requestRef.current = null;
      onCreated(data.id);
      setOpen(false);
    },
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!/^[1-9]\d*$/.test(issueId) || !/^[1-9]\d*$/.test(annotatorId) || !instruction.trim() || !dueAt || !cvatLink.trim()) {
      setValidationError('Vui lòng nhập đầy đủ Issue ID, Annotator ID, hướng dẫn, hạn xử lý và liên kết CVAT.');
      return;
    }
    const body: ReworkCreateInput = {
      issue_id: Number(issueId),
      annotator_user_id: Number(annotatorId),
      instruction: instruction.trim(),
      due_at: new Date(dueAt).toISOString(),
      severity,
      cvat_deep_link: cvatLink.trim(),
    };
    const fingerprint = JSON.stringify(body);
    if (!requestRef.current || requestRef.current.fingerprint !== fingerprint) {
      requestRef.current = { fingerprint, key: makeRequestKey() };
    }
    setValidationError(null);
    mutation.mutate({ body, key: requestRef.current.key });
  };

  return (
    <section className="lx-card" aria-label="Tạo yêu cầu sửa">
      <header className="lx-card__head">
        <div><h2 className="lx-h2">Tạo yêu cầu sửa</h2><span className="lx-hint">Dành cho issue đã được xác nhận.</span></div>
        <button className="lx-btn lx-btn--sm" type="button" onClick={() => setOpen(value => !value)}>
          {open ? 'Đóng biểu mẫu' : 'Tạo rework'}
        </button>
      </header>
      {open && <form className="lx-card__body lx-stack" onSubmit={submit}>
        <div className="lx-grid lx-grid--3">
          <div className="lx-field"><label className="lx-label" htmlFor="rework-issue">Issue ID *</label><input id="rework-issue" className="lx-input" inputMode="numeric" value={issueId} onChange={event => setIssueId(event.target.value)} /></div>
          <div className="lx-field"><label className="lx-label" htmlFor="rework-annotator">Annotator User ID *</label><input id="rework-annotator" className="lx-input" inputMode="numeric" value={annotatorId} onChange={event => setAnnotatorId(event.target.value)} /></div>
          <div className="lx-field"><label className="lx-label" htmlFor="rework-severity">Mức độ *</label><select id="rework-severity" className="lx-select" value={severity} onChange={event => setSeverity(event.target.value as ReworkCreateInput['severity'])}><option value="critical">Nghiêm trọng</option><option value="medium">Trung bình</option><option value="minor">Nhẹ</option></select></div>
        </div>
        <div className="lx-field"><label className="lx-label" htmlFor="rework-instruction">Việc cần sửa *</label><textarea id="rework-instruction" className="lx-textarea" value={instruction} onChange={event => setInstruction(event.target.value)} /></div>
        <div className="lx-grid lx-grid--2">
          <div className="lx-field"><label className="lx-label" htmlFor="rework-due">Hạn xử lý *</label><input id="rework-due" className="lx-input" type="datetime-local" value={dueAt} onChange={event => setDueAt(event.target.value)} /></div>
          <div className="lx-field"><label className="lx-label" htmlFor="rework-cvat">Liên kết CVAT *</label><input id="rework-cvat" className="lx-input" type="url" value={cvatLink} onChange={event => setCvatLink(event.target.value)} /></div>
        </div>
        {validationError && <div className="lx-callout" role="alert">{validationError}</div>}
        {mutation.isError && <div className="lx-callout" role="alert">{errorMessage(mutation.error)}</div>}
        <div className="lx-actions lx-actions--end"><button className="lx-btn lx-btn--primary" type="submit" disabled={mutation.isPending}>{mutation.isPending ? 'Đang tạo…' : 'Tạo yêu cầu sửa'}</button></div>
      </form>}
    </section>
  );
}

function ReworkDetailPanel({ id, canSubmit, canVerify, onChanged, onClose }: {
  id: number;
  canSubmit: boolean;
  canVerify: boolean;
  onChanged: () => void;
  onClose: () => void;
}) {
  const [verifyPassed, setVerifyPassed] = useState(true);
  const [verifyReason, setVerifyReason] = useState('');
  const detail = useQuery({ queryKey: ['rework-detail', id], queryFn: ({ signal }) => getRework(id, signal), retry: false });
  const revision = useQuery({
    queryKey: ['rework-current-revision', id],
    queryFn: ({ signal }) => getReworkCurrentRevision(id, signal),
    enabled: false,
    retry: false,
  });
  const submitMutation = useMutation({
    mutationFn: (cvatRevision: string) => submitRework(id, { cvat_revision: cvatRevision }, makeRequestKey()),
    retry: false,
    onSuccess: onChanged,
  });
  const verifyMutation = useMutation({
    mutationFn: (body: ReworkVerificationInput) => verifyRework(id, body, makeRequestKey()),
    retry: false,
    onSuccess: onChanged,
  });
  const item = detail.data;
  const actionError = submitMutation.error ?? verifyMutation.error;

  return (
    <section className="lx-card" aria-label={`Chi tiết rework ${id}`}>
      <header className="lx-card__head"><div><h2 className="lx-h2">Chi tiết RW-{String(id).padStart(4, '0')}</h2>{item && <span className="lx-badge lx-badge--info">{item.status}</span>}</div><button className="lx-btn lx-btn--sm" type="button" onClick={onClose}>Đóng</button></header>
      {detail.isPending && <div className="lx-card__body lx-muted" role="status">Đang tải chi tiết…</div>}
      {detail.isError && <div className="lx-card__body lx-callout" role="alert">{errorMessage(detail.error)}</div>}
      {item && <div className="lx-card__body lx-stack">
        <dl className="lx-kv">
          <dt>Issue</dt><dd className="lx-mono">#{item.issue_id}</dd>
          <dt>Frame</dt><dd className="lx-mono">#{item.frame_id}</dd>
          <dt>Revision gốc</dt><dd className="lx-mono">{item.original_revision}</dd>
          <dt>Revision đã nộp</dt><dd className="lx-mono">{item.submitted_revision ?? '—'}</dd>
          <dt>Trạng thái review</dt><dd>{item.review_state}</dd>
          <dt>Số vòng</dt><dd>{item.round_count}</dd>
        </dl>
        {item.timeline.length > 0 && <div className="lx-scroll"><table className="lx-table"><thead><tr><th>Vòng</th><th>Revision</th><th>Run kiểm tra lại</th><th>Kết quả</th></tr></thead><tbody>{item.timeline.map(round => <tr key={round.round}><td>{round.round}</td><td className="lx-mono">{round.revision}</td><td>#{round.recheck_run_id} · {round.recheck_run_status}</td><td>{round.result_status}</td></tr>)}</tbody></table></div>}

        {item.status === 'fix_pending' && canSubmit && <section className="lx-card lx-card--inner" aria-label="Báo đã sửa">
          <header className="lx-card__head"><h3 className="lx-h2">Báo đã sửa trên CVAT</h3><button className="lx-btn lx-btn--sm" type="button" disabled={revision.isFetching} onClick={() => void revision.refetch()}>{revision.isFetching ? 'Đang đọc…' : 'Đọc revision hiện tại'}</button></header>
          <div className="lx-card__body lx-stack">
            {revision.isError && <div className="lx-callout" role="alert">{errorMessage(revision.error)}</div>}
            {revision.data && <><dl className="lx-kv"><dt>CVAT Job</dt><dd>#{revision.data.cvat_job_id}</dd><dt>Revision</dt><dd className="lx-mono">{revision.data.revision_sha256}</dd><dt>Thay đổi</dt><dd>{revision.data.unchanged ? 'Chưa thay đổi' : 'Có revision mới'}</dd></dl><button className="lx-btn lx-btn--primary" type="button" disabled={revision.data.unchanged || submitMutation.isPending} onClick={() => submitMutation.mutate(revision.data!.revision_sha256)}>{submitMutation.isPending ? 'Đang gửi…' : 'Xác nhận đã sửa'}</button></>}
          </div>
        </section>}

        {item.status === 'recheck_pending' && canVerify && <form className="lx-card lx-card--inner" aria-label="Xác minh rework" onSubmit={event => { event.preventDefault(); if (!item.submitted_revision || (!verifyPassed && !verifyReason.trim())) return; verifyMutation.mutate({ passed: verifyPassed, revision: item.submitted_revision, ...(verifyReason.trim() ? { reason: verifyReason.trim() } : {}) }); }}>
          <header className="lx-card__head"><h3 className="lx-h2">Xác minh kết quả sửa</h3></header>
          <div className="lx-card__body lx-stack"><div className="lx-choices"><label className="lx-choice"><input type="radio" name="verify-result" checked={verifyPassed} onChange={() => setVerifyPassed(true)} /><span>Đạt</span></label><label className="lx-choice"><input type="radio" name="verify-result" checked={!verifyPassed} onChange={() => setVerifyPassed(false)} /><span>Chưa đạt</span></label></div><div className="lx-field"><label className="lx-label" htmlFor={`verify-reason-${id}`}>Lý do {!verifyPassed && '*'}</label><textarea id={`verify-reason-${id}`} className="lx-textarea" value={verifyReason} onChange={event => setVerifyReason(event.target.value)} required={!verifyPassed} /></div><button className="lx-btn lx-btn--primary" type="submit" disabled={!item.submitted_revision || verifyMutation.isPending}>{verifyMutation.isPending ? 'Đang xác minh…' : 'Lưu xác minh'}</button></div>
        </form>}
        {actionError && <div className="lx-callout" role="alert">{errorMessage(actionError)}</div>}
      </div>}
    </section>
  );
}

/** Bước 3 của Review Center theo ReworkTracking.dc.html, dùng GET /api/rework/. */
export function ReworkTracking() {
  const { datasetId, session } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<ReworkTabKey>('todo');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const current = TAB_CONFIG.find(item => item.key === tab)!;
  const activeRoles = rolesForDataset(session, datasetId);
  const canCreate = activeRoles.some(role => ['reviewer', 'qa_lead', 'super_admin'].includes(role));
  const canSubmit = activeRoles.some(role => ['annotator', 'super_admin'].includes(role));
  const canVerify = activeRoles.some(role => ['reviewer', 'super_admin'].includes(role));
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['rework'] });
    if (selectedId) void queryClient.invalidateQueries({ queryKey: ['rework-detail', selectedId] });
  };
  const query = useQuery({
    queryKey: ['rework', session?.user.id, datasetId, tab],
    queryFn: async ({ signal }) => {
      const pages = await Promise.all(current.statuses.map(status => getReworks(datasetId!, status, signal)));
      return { rows: pages.flatMap(page => page.results), counts: pages[0]?.counts ?? {} };
    },
    enabled: Boolean(session && datasetId),
    retry: false,
  });
  const counts = query.data?.counts;
  const todoCount = countOf(counts, 'fix_pending') + countOf(counts, 'reopened');
  const verifyCount = countOf(counts, 'recheck_pending');
  const closedCount = countOf(counts, 'resolved');
  const total = todoCount + verifyCount + closedCount;
  const closedRate = total > 0 ? (closedCount / total) * 100 : 0;
  const tabCount = (key: ReworkTabKey) => key === 'todo' ? todoCount : key === 'verify' ? verifyCount : closedCount;

  return (
    <>
      {canCreate && <ReworkCreatePanel onCreated={(id) => { setSelectedId(id); refresh(); }} />}
      <div className="lx-grid lx-grid--4">
        <div className="lx-metric"><span className="lx-metric__k">Tổng yêu cầu sửa</span><span className="lx-metric__v">{total.toLocaleString('vi-VN')}</span><span className="lx-metric__n">Trong phạm vi Dataset đang chọn</span></div>
        <div className="lx-metric"><span className="lx-metric__k">Chờ sửa</span><span className="lx-metric__v">{todoCount}</span><span className="lx-metric__n">Annotator chưa nộp lại</span></div>
        <div className="lx-metric"><span className="lx-metric__k">Chờ xác minh</span><span className="lx-metric__v">{verifyCount}</span><span className="lx-metric__n">Reviewer cần kiểm tra revision mới</span></div>
        <div className="lx-metric"><span className="lx-metric__k">Hoàn thành</span><span className="lx-metric__v">{closedRate.toFixed(1)}%</span>
          <div className="lx-progress" role="img" aria-label={`Hoàn thành ${Math.round(closedRate)}%`}><i style={{ width: `${closedRate}%` }} /></div>
          <span className="lx-metric__n">{closedCount} / {total} yêu cầu đã đóng</span></div>
      </div>
      <section className="lx-card" aria-label="Yêu cầu sửa">
        <div className="lx-tabs lx-tabs--inset" role="tablist" aria-label="Trạng thái yêu cầu sửa">
          {TAB_CONFIG.map(item => (
            <button key={item.key} type="button" role="tab" aria-selected={tab === item.key}
              className={`lx-tab${tab === item.key ? ' is-active' : ''}`} onClick={() => setTab(item.key)}>
              {item.label}<span className="lx-count">{tabCount(item.key)}</span>
            </button>
          ))}
        </div>
        {!datasetId && <div className="lx-card__body lx-muted">Vui lòng chọn Dataset để xem yêu cầu sửa.</div>}
        {query.isPending && datasetId && <div className="lx-card__body lx-muted" role="status">Đang tải yêu cầu sửa…</div>}
        {query.isError && (
          <div className="lx-card__body">
            <div className="lx-callout" role="alert">
              <div className="lx-callout__text"><strong>Không tải được yêu cầu sửa.</strong><div>{errorMessage(query.error)}</div></div>
              <button type="button" className="lx-btn lx-btn--sm" onClick={() => query.refetch()}>Thử lại</button>
            </div>
          </div>
        )}
        {query.isSuccess && (
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-900">
              <thead><tr><th>Mã yêu cầu</th><th>Issue</th><th>Frame · Object</th><th>Việc cần sửa</th><th>Annotator</th><th>Hạn</th><th>Mức độ</th><th></th></tr></thead>
              <tbody>
                {query.data.rows.map((item: ReworkItem) => {
                  const severity = SEVERITY[item.severity];
                  return (
                    <tr key={item.id}>
                      <td className="lx-mono">RW-{String(item.id).padStart(4, '0')}</td>
                      <td className="lx-mono">QC-{String(item.issue_id).padStart(5, '0')}</td>
                      <td className="lx-muted">Frame {String(item.frame_id).padStart(5, '0')} · —</td>
                      <td>{item.instruction}</td>
                      <td className="lx-muted">User #{item.annotator_user_id}</td>
                      <td className="lx-muted">{item.due_at.slice(0, 10)}</td>
                      <td><span className={`lx-badge${severity.tone ? ` lx-badge--${severity.tone}` : ''}`}>{severity.label}</span></td>
                      <td className="r">
                        <button className="lx-btn lx-btn--sm" type="button" onClick={() => setSelectedId(item.id)}>Chi tiết</button>{' '}
                        <a className="lx-iconbtn" href={item.cvat_deep_link} target="_blank" rel="noopener noreferrer" data-tip={current.tip} aria-label={current.tip}>
                          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" /></svg>
                        </a>
                      </td>
                    </tr>
                  );
                })}
                {query.data.rows.length === 0 && <tr><td colSpan={8} className="lx-muted">Chưa có yêu cầu sửa ở trạng thái này.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {selectedId && <ReworkDetailPanel id={selectedId} canSubmit={canSubmit} canVerify={canVerify} onChanged={refresh} onClose={() => setSelectedId(null)} />}
    </>
  );
}
