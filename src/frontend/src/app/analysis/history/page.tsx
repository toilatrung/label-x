'use client';

import React, { Suspense, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { FlowNav } from '@/components/layout/FlowNav';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, hasDatasetPermission } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import { DatasetPicker } from '@/lib/execution/DatasetPicker';
import { formatDateTime, snapshotCode } from '@/lib/format';
import { AnalysisProgress } from '@/components/execution/AnalysisProgress';
import { CandidateEvidenceList } from '@/components/execution/CandidateEvidenceList';
import { getSnapshot } from '@/lib/snapshots/api';
import { cancelRun, cursorFrom, engineStatusLabel, getLedger, getRun, listCandidates, listRuns, listShards, retryRun, runStatusLabel, type LedgerEntry } from '@/lib/execution/api';

function exclusionText(row: LedgerEntry) {
  return Object.entries(row.not_checked_reasons).filter(([reason, count]) => count > 0 && ['not_applicable', 'not_triggered'].includes(reason)).map(([reason, count]) => `${reason}: ${count}`).join(' · ');
}

const engineName: Record<string, string> = {
  schema: 'Schema / Taxonomy',
  geometry: 'Geometry',
  duplicate: 'Duplicate / Overlap',
  detector: 'Mô hình độc lập',
  vlm: 'Mô hình thị giác – ngôn ngữ',
  metric: 'Metric',
};

function statusBadge(status: string) {
  if (status === 'completed' || status === 'checked') return 'lx-badge--success';
  if (status === 'partial') return 'lx-badge--warning';
  if (status === 'failed') return 'lx-badge--danger';
  if (status === 'running' || status === 'queued') return 'lx-badge--info';
  return '';
}

function runDuration(createdAt: string, finishedAt?: string | null) {
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const minutes = Math.max(0, Math.round((end - new Date(createdAt).getTime()) / 60_000));
  if (minutes < 60) return `${minutes} phút`;
  return `${Math.floor(minutes / 60)} giờ ${minutes % 60} phút`;
}

function HistoryContent() {
  const params = useSearchParams();
  const { session, datasetId } = useAuth();
  const client = useQueryClient();
  const queryRunId = Number(params.get('run'));
  const [chosenId, setChosenId] = useState<number | null>(null);
  const [ignoreQueryRun, setIgnoreQueryRun] = useState(false);
  const [runCursor, setRunCursor] = useState<string | null>(null);
  const [shardCursor, setShardCursor] = useState<string | null>(null);
  const [candidateCursor, setCandidateCursor] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const selectedId = chosenId ?? (!ignoreQueryRun && Number.isInteger(queryRunId) && queryRunId > 0 ? queryRunId : null);
  const canManage = hasDatasetPermission(session, datasetId, (role) => role === 'qa_lead' || role === 'super_admin');
  const runs = useQuery({ queryKey: ['analysis-runs', session?.user.id, datasetId, runCursor], queryFn: ({ signal }) => listRuns(datasetId!, runCursor, signal), enabled: datasetId !== null, retry: false, refetchInterval: (q) => q.state.data?.results.some((r) => ['queued', 'running'].includes(r.status)) ? 3000 : false });
  const detail = useQuery({ queryKey: ['analysis-run', session?.user.id, selectedId], queryFn: ({ signal }) => getRun(selectedId!, signal), enabled: selectedId !== null && datasetId !== null, retry: false, refetchInterval: (q) => q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 3000 : false });
  const ledger = useQuery({ queryKey: ['analysis-ledger', session?.user.id, selectedId], queryFn: ({ signal }) => getLedger(selectedId!, signal), enabled: !!detail.data && selectedId !== null, retry: false, refetchInterval: detail.data && ['queued', 'running'].includes(detail.data.status) ? 3000 : false });
  const shards = useQuery({ queryKey: ['analysis-shards', session?.user.id, selectedId, shardCursor], queryFn: ({ signal }) => listShards(selectedId!, shardCursor, signal), enabled: !!detail.data && selectedId !== null, retry: false, refetchInterval: detail.data && ['queued', 'running'].includes(detail.data.status) ? 3000 : false });
  const candidates = useQuery({ queryKey: ['analysis-candidates', session?.user.id, selectedId, candidateCursor], queryFn: ({ signal }) => listCandidates(selectedId!, candidateCursor, signal), enabled: !!detail.data && selectedId !== null, retry: false, refetchInterval: detail.data && ['queued', 'running'].includes(detail.data.status) ? 3000 : false });
  const selected = detail.data;
  const reviewReady = selected?.score_version === 'score_v0' && ['completed', 'partial'].includes(selected.status);
  // B-4: đánh giá lại candidate cần revision Snapshot của run (backend: revision_sha256, rỗng thì snapshot_id).
  const canReEvaluate = hasDatasetPermission(session, datasetId, (role) => ['reviewer', 'qa_lead', 'qc_admin', 'super_admin'].includes(role));
  const runSnapshot = useQuery({ queryKey: ['analysis-run-snapshot', session?.user.id, selected?.snapshot_id], queryFn: ({ signal }) => getSnapshot(selected!.snapshot_id, signal), enabled: !!selected && canReEvaluate, retry: false });
  const reEvaluateRevision = canReEvaluate && runSnapshot.data ? (runSnapshot.data.revision_hash || String(runSnapshot.data.id)) : null;
  async function act(kind: 'cancel' | 'retry') {
    if (!selectedId || !canManage || acting) return;
    setActing(true); setActionError(null);
    try {
      if (kind === 'cancel') await cancelRun(selectedId); else await retryRun(selectedId);
      await Promise.all([
        client.invalidateQueries({ queryKey: ['analysis-runs', session?.user.id] }),
        client.invalidateQueries({ queryKey: ['analysis-run', session?.user.id, selectedId] }),
        client.invalidateQueries({ queryKey: ['analysis-ledger', session?.user.id, selectedId] }),
        client.invalidateQueries({ queryKey: ['analysis-shards', session?.user.id, selectedId] }),
        client.invalidateQueries({ queryKey: ['analysis-candidates', session?.user.id, selectedId] }),
      ]);
    } catch (err) { setActionError(errorMessage(err)); }
    finally { setActing(false); }
  }
  return <AppShell activeKey="analysis" flowStep={3} showFlowNav={false} pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Execution History</h1><p className="lx-lead">Theo dõi từng lần chạy và kết quả của từng engine. Engine lỗi hoặc chưa chạy được ghi rõ là Failed, Partial hoặc Not checked.</p></div></div>}>
    <div className="lx-cols">
      <section className="lx-card lx-main" aria-label="Các lần chạy">
        <FlowNav flow="analysis" currentStep={3} variant="tabs" inCard />
        <header className="lx-card__head"><h2 className="lx-h2">Các lần chạy</h2><span className="lx-hint">{datasetId === null ? 'Chưa chọn Dataset' : `Dataset #${datasetId}`}</span></header>
        <div className="lx-card__body"><DatasetPicker onChange={(nextDatasetId) => { setChosenId(null); if (datasetId !== null && nextDatasetId !== datasetId) setIgnoreQueryRun(true); setRunCursor(null); setShardCursor(null); setCandidateCursor(null); }} /></div>
        {!datasetId && <div className="lx-card__body lx-muted">Chọn Dataset để xem lịch sử.</div>}
        {runs.isError && <div role="alert" className="lx-card__body">{errorMessage(runs.error)}</div>}
        {runs.isLoading && datasetId && <div className="lx-card__body">Đang tải…</div>}
        {runs.data && <><div className="lx-scroll"><table className="lx-table lx-table--min-520"><thead><tr><th>Quality Control Run</th><th>Snapshot</th><th>Bắt đầu</th><th className="r">Coverage</th><th>Trạng thái</th></tr></thead><tbody>
          {runs.data.results.map((r) => <tr key={r.id} aria-selected={selectedId === r.id}><td><div className="lx-cell__main lx-mono">#QC-{r.id}</div><button type="button" className="lx-btn lx-btn--sm" onClick={() => { setChosenId(r.id); setIgnoreQueryRun(true); setShardCursor(null); setCandidateCursor(null); }}>Chi tiết</button></td><td className="lx-mono">{snapshotCode(r.snapshot_id)}</td><td className="lx-muted">{formatDateTime(r.created_at)}</td><td className="r">—</td><td><span className={`lx-badge ${statusBadge(r.status)}`}>{runStatusLabel[r.status]}</span></td></tr>)}
          {runs.data.results.length === 0 && <tr><td colSpan={5}>Chưa có Quality Control Run trong Dataset này.</td></tr>}
        </tbody></table></div></>}
        {runs.data?.next && <footer className="lx-card__foot"><button className="lx-btn lx-btn--sm" type="button" onClick={() => setRunCursor(cursorFrom(runs.data?.next))}>Trang tiếp</button></footer>}
      </section>
      <section className="lx-card lx-side lx-side--wide" aria-label="Chi tiết Quality Control Run">
        <header className="lx-card__head"><h2 className="lx-h2">Chi tiết {selectedId ? <span className="lx-mono">#QC-{selectedId}</span> : null}</h2>{selected && <span className="lx-hint">Thời gian chạy {runDuration(selected.created_at, selected.finished_at)}</span>}</header>
        {!selectedId && <div className="lx-card__body lx-muted">Chọn Chi tiết tại một Quality Control Run để xem trạng thái từng engine.</div>}
        {detail.isLoading && <div className="lx-card__body">Đang tải chi tiết…</div>}
        {detail.isError && <div className="lx-card__body" role="alert">{errorMessage(detail.error)}</div>}
        {selected && <div className="lx-card__body lx-stack lx-stack--3">
          <AnalysisProgress run={selected} ledger={ledger.data} error={ledger.isError ? errorMessage(ledger.error) : null} />
          {(ledger.data ?? []).map((row) => <div key={row.engine} className="lx-stack lx-stack--2"><div className="lx-row lx-row--between"><span>{engineName[row.engine] ?? row.engine}</span><span className={`lx-badge ${statusBadge(row.status)}`}>{engineStatusLabel[row.status]}</span></div>{row.coverage !== null && <div className={row.status === 'partial' ? 'lx-progress lx-progress--warn' : 'lx-progress'}><i style={{ width: `${Math.round(row.coverage * 100)}%` }} /></div>}{selected.engines.find((engine) => engine.engine === row.engine)?.reason && <span className="lx-hint">{selected.engines.find((engine) => engine.engine === row.engine)?.reason}</span>}</div>)}
          {ledger.isLoading && <span className="lx-muted">Đang tải Coverage theo engine…</span>}
          {ledger.isError && <span role="alert">{errorMessage(ledger.error)}</span>}
          {candidates.data && <div className="lx-callout lx-callout--info"><span className="lx-callout__text">Candidate: {candidates.data.raw_count === null ? '' : `${candidates.data.raw_count} bản ghi thô → `}{candidates.data.dedup_count} sau khi gộp trùng. {reviewReady ? 'Hàng đợi Review đã sẵn sàng.' : ['queued', 'running'].includes(selected.status) ? 'Hàng đợi Review sẽ sẵn sàng khi run kết thúc.' : 'Run chưa có hàng đợi Review. Tạo run mới để phân tích lại.'}</span></div>}
          <div className="lx-actions">{canManage && selected.status === 'partial' && (reviewReady ? <Link className="lx-btn" href="/analysis/config">Tạo run mới để chạy lại engine lỗi</Link> : <button className="lx-btn" type="button" disabled={acting} onClick={() => act('retry')}>Chạy lại engine lỗi</button>)}<Link className="lx-btn lx-btn--primary" href={`/review?run=${selected.id}`}>Mở Review Queues →</Link></div>
          {actionError && <p role="alert" className="lx-callout">{actionError}</p>}
        </div>}
      </section>
    </div>
    {selectedId && datasetId && <section className="lx-card" aria-label="Dữ liệu kỹ thuật Quality Control Run">
      <div className="lx-card__body lx-stack">
      <h2 className="lx-h2">Dữ liệu kỹ thuật <span className="lx-mono">#QC-{selectedId}</span></h2>
      {detail.isError && <p role="alert">{errorMessage(detail.error)}</p>}
      {detail.isLoading && <p>Đang tải chi tiết…</p>}
      {selected && <><div className="lx-execution-summary"><span>Snapshot {snapshotCode(selected.snapshot_id)}</span><span>Phiên bản cấu hình v{selected.config_version_id}</span><span>Seed {selected.seed}</span><strong>{runStatusLabel[selected.status]}</strong></div>
        {selected.status === 'queued' && detail.dataUpdatedAt - new Date(selected.created_at).getTime() > 120_000 && <p role="alert" className="lx-callout">Quality Control Run đã chờ hơn 2 phút và chưa bắt đầu. Kiểm tra worker và việc điều phối; không xem trạng thái đang chờ là kết quả kiểm tra.</p>}
        {canManage && ['queued', 'running'].includes(selected.status) && <div className="lx-execution-actions"><button className="lx-btn" type="button" disabled={acting} onClick={() => act('cancel')}>Hủy run</button></div>}
        {actionError && <p role="alert" className="lx-callout">{actionError}</p>}
        <h3>Coverage ledger theo engine</h3>
        {ledger.isError && <p role="alert">{errorMessage(ledger.error)}</p>}
        {ledger.data && <div className="lx-execution-scroll"><table className="lx-table"><thead><tr><th>Engine</th><th>Trạng thái</th><th>Coverage</th><th>Completed</th><th>Failed</th><th>Pending</th><th>Not checked</th></tr></thead><tbody>{ledger.data.map((row) => <React.Fragment key={row.engine}><tr><td>{engineName[row.engine] ?? row.engine}{row.required ? ' · bắt buộc' : ''}</td><td><span className={`lx-badge lx-engine-status--${row.status}`}>{engineStatusLabel[row.status]}</span></td><td>{row.coverage === null ? 'N/A' : `${Math.round(row.coverage * 100)}%`} ({row.completed}/{row.eligible})</td><td>{row.completed}</td><td>{row.failed}</td><td>{row.pending}</td><td>{row.not_checked}</td></tr>
          {row.excluded > 0 && <tr><td colSpan={7}><div className="lx-execution-warning" role="note">⚠ {row.excluded} {row.unit} bị loại khỏi mẫu số coverage: {exclusionText(row)}. Applicability version: {row.applicability_version}.</div></td></tr>}
          {row.not_checked > row.excluded && <tr><td colSpan={7}>Not checked: {Object.entries(row.not_checked_reasons).filter(([reason, count]) => count > 0 && !['not_applicable', 'not_triggered'].includes(reason)).map(([reason, count]) => `${reason}: ${count}`).join(' · ')}</td></tr>}
        </React.Fragment>)}</tbody></table></div>}
        <h3>Trạng thái shard</h3>
        {shards.isError && <p role="alert">{errorMessage(shards.error)}</p>}
        {shards.data && <div className="lx-execution-scroll"><table className="lx-table"><thead><tr><th>Shard</th><th>Engine</th><th>Trạng thái</th><th>Lần thử</th><th>Lỗi cuối</th></tr></thead><tbody>{shards.data.results.map((s) => <tr key={s.id}><td>{s.shard_key}</td><td>{engineName[s.engine] ?? s.engine}</td><td>{s.status}</td><td>{s.attempt}</td><td>{s.last_error || '—'}</td></tr>)}{shards.data.results.length === 0 && <tr><td colSpan={5}>Chưa có shard.</td></tr>}</tbody></table></div>}
        {shards.data?.next && <button type="button" className="lx-btn lx-btn--sm" onClick={() => setShardCursor(cursorFrom(shards.data?.next))}>Trang shard tiếp</button>}
        <h3>Danh sách candidate và evidence</h3>
        <div className="lx-execution-candidates">
          <CandidateEvidenceList
            candidates={candidates.data?.results}
            rawCount={candidates.data?.raw_count}
            dedupCount={candidates.data?.dedup_count}
            isLoading={candidates.isPending}
            error={candidates.isError ? errorMessage(candidates.error) : null}
            reEvaluateRevision={reEvaluateRevision}
          />
          {candidates.data?.next && (
            <button
              type="button"
              className="lx-btn lx-btn--sm"
              onClick={() => setCandidateCursor(cursorFrom(candidates.data?.next))}
            >
              Trang candidate tiếp
            </button>
          )}
        </div>
      </>}
      </div>
    </section>}
  </AppShell>;
}

export default function ExecutionHistoryPage() {
  return <AuthGuard permissionCheck={canAccessAnalysis} requiredPermissionName="Quyền Phân tích Chất lượng"><Suspense fallback={<div>Đang tải lịch sử…</div>}><HistoryContent /></Suspense></AuthGuard>;
}
