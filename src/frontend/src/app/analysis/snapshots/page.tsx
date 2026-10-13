'use client';

import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AppShell } from '@/components/layout/AppShell';
import { ForbiddenView } from '@/components/auth/ForbiddenView';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, hasDatasetPermission } from '@/lib/auth/roles';
import { formatCount, shortRevision, snapshotCode } from '@/lib/format';
import { snapshotStatus, type Snapshot } from '@/lib/snapshots/api';
import { errorMessage } from '@/lib/api/errors';
import { useDatasetRuns, useDatasets, useSnapshotHistory } from '@/lib/snapshots/queries';
import { latestRunBySnapshot } from '@/lib/snapshots/runs';

const statusTone = (status: Snapshot['status']) => status === 'locked' ? 'success' : status === 'failed' ? 'danger' : 'info';
const frameTotal = (item: Snapshot) => item.jobs.some(job => job.frames.length) ? item.jobs.reduce((sum, job) => sum + job.frames.length, 0) : null;

export default function SnapshotHistoryPage() {
  const { session, isLoading, datasetId, setDatasetId } = useAuth();
  const router = useRouter();
  const canEnter = !!session?.roles.some(({ role }) => canAccessAnalysis(role));
  const canRead = hasDatasetPermission(session, datasetId, canAccessAnalysis);
  const datasets = useDatasets(canEnter ? session?.user.id : undefined);
  const items = datasets.data?.pages.flatMap(page => page.results) ?? [];
  const selectedDataset = items.find(item => item.id === datasetId);
  const history = useSnapshotHistory(session?.user.id, canRead ? datasetId : null);
  const runs = useDatasetRuns(session?.user.id, datasetId, canRead && !datasets.isError);
  const latestRuns = React.useMemo(() => latestRunBySnapshot(runs.data ?? []), [runs.data]);
  const snapshots = history.data?.pages.flatMap(page => page.results) ?? [];
  React.useEffect(() => { if (!isLoading && !session) router.replace('/login'); }, [isLoading, session, router]);

  if (isLoading || !session) return <p role="status">Đang tải phiên làm việc…</p>;
  if (!canEnter) return <ForbiddenView requiredPermission="Quality Assurance Lead / Quality Control Admin / Super Admin" />;
  const loadFailed = datasets.isError || history.isError;
  const hint = loadFailed ? 'Không tải được dữ liệu' : `${snapshots.length} snapshot đã tải`;
  return <AppShell activeKey="analysis" showFlowNav={false} context={{
    datasetName: selectedDataset?.name,
  }}
    pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Lịch sử snapshot</h1>
      <p className="lx-lead">Các snapshot đã tạo, annotation revision tương ứng và Quality Control Run đã chạy trên từng snapshot. Snapshot không thể sửa.</p></div>
      <div className="lx-actions"><Link className="lx-btn" href="/analysis">Về Snapshot</Link></div></div>}>
    <section className="lx-card" aria-label="Tất cả snapshot"><div className="lx-card__head"><h2 className="lx-h2">Tất cả snapshot</h2>
      <span className="lx-hint">{hint}</span></div>
      <div className="lx-card__body lx-stack"><div className="lx-field">
        <label className="lx-label" htmlFor="history-dataset">Dataset / project CVAT</label>
        <select id="history-dataset" className="lx-select" value={datasetId ?? ''} disabled={datasets.isError || datasets.isPending}
          onChange={event => setDatasetId(event.target.value ? Number(event.target.value) : null)}>
          <option value="">Chọn Dataset</option>
          {datasetId !== null && !selectedDataset && <option value={datasetId}>Dataset #{datasetId}</option>}
          {items.map(item => <option key={item.id} value={item.id}>{item.name} · project #{item.cvat_project_id}</option>)}
        </select></div>
        {datasets.hasNextPage && <button className="lx-btn" type="button" disabled={datasets.isFetchingNextPage}
          onClick={() => void datasets.fetchNextPage()}>Tải thêm Dataset</button>}
        {datasets.isError && <div className="lx-callout" role="alert">{errorMessage(datasets.error)}
          <button type="button" className="lx-btn" onClick={() => void datasets.refetch()}>Thử lại Dataset</button></div>}
        {history.isError && <div className="lx-callout" role="alert">{errorMessage(history.error)}
          <button type="button" className="lx-btn" onClick={() => void history.refetch()}>Thử lại lịch sử Snapshot</button></div>}
        {runs.isError && <div className="lx-callout" role="alert">{errorMessage(runs.error)}
          <button type="button" className="lx-btn" onClick={() => void runs.refetch()}>Thử lại Quality Control Run</button></div>}
        {datasetId === null && <p className="lx-muted">Vui lòng chọn một Dataset để xem lịch sử Snapshot.</p>}
        {datasetId !== null && !selectedDataset && datasets.isSuccess && (
          <div className="lx-callout" role="alert">Dataset không tồn tại hoặc bạn không có quyền truy cập.</div>
        )}
        {selectedDataset && !canRead && <div className="lx-callout" role="alert">Bạn không có quyền xem Dataset này.</div>}
        {history.isPending && canRead && <p role="status">Đang tải lịch sử…</p>}
        {!loadFailed && history.isSuccess && !snapshots.length && <p className="lx-muted">Chưa có Snapshot trong Dataset này.</p>}
      </div>
      <div className="lx-scroll"><table className="lx-table lx-table--min-760"><thead><tr>
        <th>Snapshot</th><th>Dataset</th><th>Revision</th><th className="r">Frame</th><th>Quality Control Run</th><th>Trạng thái</th>
      </tr></thead><tbody>
        {!loadFailed && snapshots.map(item => <tr key={item.id}>
          <td className="lx-mono"><Link href={`/analysis?snapshotId=${item.id}`}>{snapshotCode(item.id)}</Link></td>
          <td>{selectedDataset?.name ?? `Dataset #${item.dataset_id}`}</td>
          <td className="lx-mono" title={item.revision_hash ?? undefined}>{shortRevision(item.revision_hash)}</td>
          <td className="r">{formatCount(frameTotal(item))}</td>
          <td className="lx-mono">{latestRuns.get(item.id)
            ? <Link href={`/analysis/history?run=${latestRuns.get(item.id)!.id}`}>Run #{latestRuns.get(item.id)!.id}</Link>
            : <span className="lx-subtle">{runs.isPending && canRead ? 'Đang tải…' : '—'}</span>}</td>
          <td><span className={`lx-badge lx-badge--${statusTone(item.status)}`}>{snapshotStatus(item.status)}</span></td>
        </tr>)}
      </tbody></table></div>
      {history.hasNextPage && <div className="lx-card__foot"><button className="lx-btn" type="button"
        disabled={history.isFetchingNextPage} onClick={() => void history.fetchNextPage()}>
        {history.isFetchingNextPage ? 'Đang tải…' : 'Tải thêm'}</button></div>}
    </section>
  </AppShell>;
}
