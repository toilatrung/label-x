'use client';

import React, { Suspense, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, hasDatasetPermission } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import { DatasetPicker } from '@/lib/execution/DatasetPicker';
import { CandidateEvidenceList } from '@/components/execution/CandidateEvidenceList';
import { cancelRun, cursorFrom, engineStatusLabel, getLedger, getRun, listCandidates, listRuns, listShards, retryRun, runStatusLabel, type LedgerEntry } from '@/lib/execution/api';

function exclusionText(row: LedgerEntry) {
  return Object.entries(row.not_checked_reasons).filter(([reason, count]) => count > 0 && ['not_applicable', 'not_triggered'].includes(reason)).map(([reason, count]) => `${reason}: ${count}`).join(' · ');
}

function HistoryContent() {
  const params = useSearchParams();
  const { session, datasetId } = useAuth();
  const client = useQueryClient();
  const queryRunId = Number(params.get('run'));
  const [chosenId, setChosenId] = useState<number | null>(null);
  const [runCursor, setRunCursor] = useState<string | null>(null);
  const [shardCursor, setShardCursor] = useState<string | null>(null);
  const [candidateCursor, setCandidateCursor] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const selectedId = chosenId ?? (Number.isInteger(queryRunId) && queryRunId > 0 ? queryRunId : null);
  const canManage = hasDatasetPermission(session, datasetId, (role) => role === 'qa_lead' || role === 'super_admin');
  const runs = useQuery({ queryKey: ['analysis-runs', session?.user.id, datasetId, runCursor], queryFn: ({ signal }) => listRuns(datasetId!, runCursor, signal), enabled: datasetId !== null, retry: false, refetchInterval: (q) => q.state.data?.results.some((r) => ['queued', 'running'].includes(r.status)) ? 3000 : false });
  const detail = useQuery({ queryKey: ['analysis-run', session?.user.id, selectedId], queryFn: ({ signal }) => getRun(selectedId!, signal), enabled: selectedId !== null && datasetId !== null, retry: false, refetchInterval: (q) => q.state.data && ['queued', 'running'].includes(q.state.data.status) ? 3000 : false });
  const ledger = useQuery({ queryKey: ['analysis-ledger', session?.user.id, selectedId], queryFn: ({ signal }) => getLedger(selectedId!, signal), enabled: !!detail.data && selectedId !== null, retry: false, refetchInterval: detail.data && ['queued', 'running'].includes(detail.data.status) ? 3000 : false });
  const shards = useQuery({ queryKey: ['analysis-shards', session?.user.id, selectedId, shardCursor], queryFn: ({ signal }) => listShards(selectedId!, shardCursor, signal), enabled: !!detail.data && selectedId !== null, retry: false, refetchInterval: detail.data && ['queued', 'running'].includes(detail.data.status) ? 3000 : false });
  const candidates = useQuery({ queryKey: ['analysis-candidates', session?.user.id, selectedId, candidateCursor], queryFn: ({ signal }) => listCandidates(selectedId!, candidateCursor, signal), enabled: !!detail.data && selectedId !== null, retry: false, refetchInterval: detail.data && ['queued', 'running'].includes(detail.data.status) ? 3000 : false });
  const selected = detail.data;
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
  return <AppShell activeKey="analysis" flowStep={3} pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Lịch sử thực thi</h1><p className="lx-lead">Theo dõi QC run, coverage và trạng thái từng shard. Failed, Partial và Not checked không phải kết quả đạt.</p></div></div>}>
    <div className="lx-execution-nav"><Link href="/analysis/config" className="lx-btn">Tạo QC run</Link><DatasetPicker onChange={() => { setChosenId(null); setRunCursor(null); setShardCursor(null); setCandidateCursor(null); }} /></div>
    <section className="lx-card" aria-label="Các lần chạy"><header className="lx-card__head"><h2 className="lx-h2">Các lần chạy</h2></header>
      {!datasetId && <div className="lx-card__body">Chọn dataset để xem lịch sử.</div>}
      {runs.isError && <div role="alert" className="lx-card__body">{errorMessage(runs.error)}</div>}
      {runs.isLoading && datasetId && <div className="lx-card__body">Đang tải…</div>}
      {runs.data && <div className="lx-execution-scroll"><table className="lx-table"><thead><tr><th>QC run</th><th>Snapshot</th><th>Bắt đầu</th><th>Trạng thái</th><th></th></tr></thead><tbody>
        {runs.data.results.map((r) => <tr key={r.id}><td>QC-{r.id}</td><td>SNP-{r.snapshot_id}</td><td>{new Date(r.created_at).toLocaleString('vi-VN')}</td><td><span className={`lx-badge lx-run-status--${r.status}`}>{runStatusLabel[r.status]}</span></td><td><button type="button" className="lx-btn lx-btn--sm" onClick={() => { setChosenId(r.id); setShardCursor(null); setCandidateCursor(null); }}>Chi tiết</button></td></tr>)}
        {runs.data.results.length === 0 && <tr><td colSpan={5}>Chưa có run trong dataset này.</td></tr>}
      </tbody></table></div>}
      {runs.data?.next && <footer className="lx-card__foot"><button className="lx-btn lx-btn--sm" type="button" onClick={() => setRunCursor(cursorFrom(runs.data?.next))}>Trang tiếp</button></footer>}
    </section>
    {selectedId && datasetId && <section className="lx-card lx-card__body lx-stack" aria-label="Chi tiết QC run">
      <h2 className="lx-h2">Chi tiết QC-{selectedId}</h2>
      {detail.isError && <p role="alert">{errorMessage(detail.error)}</p>}
      {detail.isLoading && <p>Đang tải chi tiết…</p>}
      {selected && <><div className="lx-execution-summary"><span>Snapshot SNP-{selected.snapshot_id}</span><span>Config v{selected.config_version_id}</span><span>Seed {selected.seed}</span><strong>{runStatusLabel[selected.status]}</strong></div>
        {selected.status === 'queued' && detail.dataUpdatedAt - new Date(selected.created_at).getTime() > 120_000 && <p role="alert" className="lx-callout">Run đã chờ hơn 2 phút và chưa bắt đầu. Kiểm tra worker/dispatch; không xem trạng thái queued là kết quả QC.</p>}
        {canManage && <div className="lx-execution-actions">{['queued', 'running'].includes(selected.status) && <button className="lx-btn" type="button" disabled={acting} onClick={() => act('cancel')}>Hủy run</button>}{selected.status === 'partial' && <button className="lx-btn lx-btn--primary" type="button" disabled={acting} onClick={() => act('retry')}>Chạy lại shard lỗi</button>}</div>}
        {actionError && <p role="alert" className="lx-callout">{actionError}</p>}
        <h3>Coverage ledger theo engine</h3>
        {ledger.isError && <p role="alert">{errorMessage(ledger.error)}</p>}
        {ledger.data && <div className="lx-execution-scroll"><table className="lx-table"><thead><tr><th>Engine</th><th>Trạng thái</th><th>Coverage</th><th>Completed</th><th>Failed</th><th>Pending</th><th>Not checked</th></tr></thead><tbody>{ledger.data.map((row) => <React.Fragment key={row.engine}><tr><td>{row.engine}{row.required ? ' · required' : ''}</td><td><span className={`lx-badge lx-engine-status--${row.status}`}>{engineStatusLabel[row.status]}</span>{selected.engines.find((e) => e.engine === row.engine)?.reason && <small> · {selected.engines.find((e) => e.engine === row.engine)?.reason}</small>}</td><td>{row.coverage === null ? 'N/A' : `${Math.round(row.coverage * 100)}%`} ({row.completed}/{row.eligible})</td><td>{row.completed}</td><td>{row.failed}</td><td>{row.pending}</td><td>{row.not_checked}</td></tr>
          {row.excluded > 0 && <tr><td colSpan={7}><div className="lx-execution-warning" role="note">⚠ {row.excluded} {row.unit} bị loại khỏi mẫu số coverage: {exclusionText(row)}. Applicability version: {row.applicability_version}.</div></td></tr>}
          {row.not_checked > row.excluded && <tr><td colSpan={7}>Not checked: {Object.entries(row.not_checked_reasons).filter(([reason, count]) => count > 0 && !['not_applicable', 'not_triggered'].includes(reason)).map(([reason, count]) => `${reason}: ${count}`).join(' · ')}</td></tr>}
        </React.Fragment>)}</tbody></table></div>}
        <h3>Trạng thái shard</h3>
        {shards.isError && <p role="alert">{errorMessage(shards.error)}</p>}
        {shards.data && <div className="lx-execution-scroll"><table className="lx-table"><thead><tr><th>Shard</th><th>Engine</th><th>Trạng thái</th><th>Lần thử</th><th>Lỗi cuối</th></tr></thead><tbody>{shards.data.results.map((s) => <tr key={s.id}><td>{s.shard_key}</td><td>{s.engine}</td><td>{s.status}</td><td>{s.attempt}</td><td>{s.last_error || '—'}</td></tr>)}{shards.data.results.length === 0 && <tr><td colSpan={5}>Chưa có shard.</td></tr>}</tbody></table></div>}
        {shards.data?.next && <button type="button" className="lx-btn lx-btn--sm" onClick={() => setShardCursor(cursorFrom(shards.data?.next))}>Trang shard tiếp</button>}
        <h3>Danh sách candidate và evidence</h3>
        <div className="lx-execution-candidates">
          <CandidateEvidenceList
            candidates={candidates.data?.results}
            rawCount={candidates.data?.raw_count}
            dedupCount={candidates.data?.dedup_count}
            isLoading={candidates.isPending}
            error={candidates.isError ? errorMessage(candidates.error) : null}
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
    </section>}
  </AppShell>;
}

export default function ExecutionHistoryPage() {
  return <AuthGuard permissionCheck={canAccessAnalysis} requiredPermissionName="Quyền Phân tích Chất lượng"><Suspense fallback={<div>Đang tải lịch sử…</div>}><HistoryContent /></Suspense></AuthGuard>;
}
