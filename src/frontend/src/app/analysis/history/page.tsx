'use client';

import React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AppShell } from '@/components/layout/AppShell';
import { ForbiddenView } from '@/components/auth/ForbiddenView';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, hasDatasetPermission } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import { snapshotStatus } from '@/lib/snapshots/api';
import { useDatasets, useSnapshotHistory } from '@/lib/snapshots/queries';

export default function SnapshotHistoryPage() {
  const { session, isLoading, datasetId, setDatasetId } = useAuth();
  const router = useRouter();
  const canEnter = !!session?.roles.some(({ role }) => canAccessAnalysis(role));
  const canRead = hasDatasetPermission(session, datasetId, canAccessAnalysis);
  const datasets = useDatasets(canEnter ? session?.user.id : undefined);
  const items = datasets.data?.pages.flatMap(page => page.results) ?? [];
  const selectedDataset = items.find(item => item.id === datasetId);
  const history = useSnapshotHistory(session?.user.id, canRead ? datasetId : null);
  const snapshots = history.data?.pages.flatMap(page => page.results) ?? [];
  React.useEffect(() => { if (!isLoading && !session) router.replace('/login'); }, [isLoading, session, router]);

  if (isLoading || !session) return <p role="status">Đang tải phiên làm việc…</p>;
  if (!canEnter) return <ForbiddenView requiredPermission="QA Lead / QC Admin / Super Admin" />;
  return <AppShell activeKey="analysis" flowStep={1} context={{ datasetName: selectedDataset?.name }}
    pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Lịch sử Snapshot</h1>
      <p className="lx-lead">Các Snapshot đã tạo theo Dataset, hash, drift và trạng thái khóa.</p></div>
      <Link className="lx-btn" href="/analysis">Về Snapshot</Link></div>}>
    <section className="lx-card"><div className="lx-card__head"><h2 className="lx-h2">Snapshot theo Dataset</h2>
      <span className="lx-hint">{snapshots.length} Snapshot đã tải</span></div>
      <div className="lx-card__body lx-stack"><div className="lx-field">
        <label className="lx-label" htmlFor="history-dataset">Dataset / project CVAT</label>
        <select id="history-dataset" className="lx-select" value={datasetId ?? ''}
          onChange={event => setDatasetId(event.target.value ? Number(event.target.value) : null)}>
          <option value="">Chọn Dataset</option>
          {datasetId !== null && !selectedDataset && <option value={datasetId}>Dataset #{datasetId}</option>}
          {items.map(item => <option key={item.id} value={item.id}>{item.name} · project #{item.cvat_project_id}</option>)}
        </select></div>
        {datasets.isError && <div className="lx-callout" role="alert">{errorMessage(datasets.error)}</div>}
        {datasets.hasNextPage && <button className="lx-btn" type="button" disabled={datasets.isFetchingNextPage}
          onClick={() => void datasets.fetchNextPage()}>Tải thêm Dataset</button>}
        {datasetId !== null && !canRead && <div className="lx-callout" role="alert">Bạn không có quyền xem Dataset này.</div>}
        {history.isPending && canRead && <p role="status">Đang tải lịch sử…</p>}
        {history.isError && <div className="lx-callout" role="alert">{errorMessage(history.error)}
          <button className="lx-btn" type="button" onClick={() => void history.refetch()}>Thử lại</button></div>}
        {history.isSuccess && !snapshots.length && <p className="lx-muted">Chưa có Snapshot trong Dataset này.</p>}
      </div>
      {!!snapshots.length && <div className="lx-scroll"><table className="lx-table"><thead><tr>
        <th>Snapshot</th><th>Hash tổng</th><th>Cha</th><th>Job drift</th><th>Shape bỏ qua</th><th>Trạng thái</th><th>Ngày tạo</th>
      </tr></thead><tbody>{snapshots.map(item => <tr key={item.id}>
        <td><Link href={`/analysis?snapshotId=${item.id}`}>SNP-{item.id}</Link></td>
        <td className="lx-mono" style={{ overflowWrap: 'anywhere' }}>{item.revision_hash || '—'}</td>
        <td>{item.parent_snapshot_id ? <Link href={`/analysis?snapshotId=${item.parent_snapshot_id}`}>
          SNP-{item.parent_snapshot_id}</Link> : '—'}</td>
        <td>{item.drift_jobs.length ? item.drift_jobs.join(', ') : '—'}</td>
        <td>{item.out_of_scope_shapes ?? '—'}</td><td>{snapshotStatus(item.status)}</td>
        <td>{item.created_at}</td>
      </tr>)}</tbody></table></div>}
      {history.hasNextPage && <div className="lx-card__foot"><button className="lx-btn" type="button"
        disabled={history.isFetchingNextPage} onClick={() => void history.fetchNextPage()}>
        {history.isFetchingNextPage ? 'Đang tải…' : 'Tải thêm'}</button></div>}
    </section>
  </AppShell>;
}
