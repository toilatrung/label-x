'use client';

import React, { Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AppShell } from '@/components/layout/AppShell';
import { ForbiddenView } from '@/components/auth/ForbiddenView';
import { SnapshotDetail } from '@/components/snapshots/SnapshotDetail';
import { SnapshotForm } from '@/components/snapshots/SnapshotForm';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, hasDatasetPermission } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import { useDatasets, useSnapshot, useSnapshotHistory, useTasks } from '@/lib/snapshots/queries';

function SnapshotWorkspace() {
  const { session, isLoading, datasetId, setDatasetId } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const rawId = search.get('snapshotId');
  const parsed = rawId && /^[1-9]\d*$/.test(rawId) ? Number(rawId) : null;
  const id = parsed && Number.isSafeInteger(parsed) ? parsed : null;
  const userId = session?.user.id;
  const [requestLocked, setRequestLocked] = React.useState(false);
  const canEnter = !!session?.roles.some(({ role }) => canAccessAnalysis(role));
  const canRead = hasDatasetPermission(session, datasetId, canAccessAnalysis);
  const canCreate = hasDatasetPermission(session, datasetId, role => role === 'qa_lead' || role === 'super_admin');
  const datasetQuery = useDatasets(canEnter ? userId : undefined);
  const allDatasets = datasetQuery.data?.pages.flatMap(page => page.results) ?? [];
  const selectedDataset = allDatasets.find(item => item.id === datasetId);
  const detail = useSnapshot(canEnter ? userId : undefined, id);
  const taskQuery = useTasks(userId, datasetId, canRead && !!selectedDataset && !id);
  const recent = useSnapshotHistory(userId, canRead ? datasetId : null);
  const recentLocked = recent.data?.pages.flatMap(page => page.results).find(item => item.status === 'locked');
  React.useEffect(() => { if (!isLoading && !session) router.replace('/login'); }, [isLoading, session, router]);

  if (isLoading || !session) return <p role="status">Đang tải phiên làm việc…</p>;
  if (!canEnter) return <ForbiddenView requiredPermission="QA Lead / QC Admin / Super Admin" />;
  const item = detail.data && hasDatasetPermission(session, detail.data.dataset_id, canAccessAnalysis) ? detail.data : null;
  return <AppShell activeKey="analysis" flowStep={1}
    context={{ datasetName: selectedDataset?.name, datasetIdOverride: item?.dataset_id,
      snapshotName: item ? `SNP-${item.id} · ${item.status}` : undefined,
      guidelineVersion: item?.guideline_version ?? selectedDataset?.guideline_version ?? undefined,
      taxonomyVersion: item?.taxonomy_version ?? selectedDataset?.taxonomy_version ?? undefined }}
    pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Snapshot</h1>
      <p className="lx-lead">Chốt phiên bản annotation để kiểm tra. Annotation thay đổi sẽ tạo Snapshot mới.</p></div>
      <div className="lx-actions"><Link className="lx-btn" href="/analysis/history">Lịch sử Snapshot</Link>
        {id && <Link className="lx-btn" href="/analysis">Tạo Snapshot mới</Link>}</div></div>}>
    {rawId && !id && <div className="lx-callout" role="alert">ID Snapshot không hợp lệ.</div>}
    {id ? <>
      {detail.isPending && <p role="status">Đang tải Snapshot #{id}…</p>}
      {detail.isError && <div className="lx-callout" role="alert">{errorMessage(detail.error)}
        <button className="lx-btn" type="button" onClick={() => void detail.refetch()}>Thử lại</button></div>}
      {detail.isSuccess && !item && <div className="lx-callout" role="alert">Bạn không có quyền xem Snapshot này.</div>}
      {item && <SnapshotDetail item={item} />}
    </> : <div className="lx-cols">
      <section className="lx-card lx-main"><div className="lx-card__head"><h2 className="lx-h2">Tạo Snapshot mới</h2></div>
        <div className="lx-card__body lx-stack">
          <div className="lx-field"><label className="lx-label" htmlFor="snapshot-dataset">Dataset / project CVAT</label>
            <select id="snapshot-dataset" className="lx-select" value={datasetId ?? ''} disabled={requestLocked}
              onChange={event => setDatasetId(event.target.value ? Number(event.target.value) : null)}>
              <option value="">Chọn Dataset</option>
              {datasetId !== null && !selectedDataset && <option value={datasetId}>Dataset #{datasetId}</option>}
              {allDatasets.map(dataset => <option key={dataset.id} value={dataset.id}>
                {dataset.name} · project #{dataset.cvat_project_id}</option>)}
            </select></div>
          {datasetQuery.isPending && <p role="status">Đang tải Dataset…</p>}
          {datasetQuery.isError && <div className="lx-callout" role="alert">{errorMessage(datasetQuery.error)}</div>}
          {datasetQuery.hasNextPage && <button className="lx-btn" type="button" disabled={datasetQuery.isFetchingNextPage}
            onClick={() => void datasetQuery.fetchNextPage()}>Tải thêm Dataset</button>}
          {selectedDataset && !canRead && <div className="lx-callout" role="alert">Bạn không có quyền xem Dataset này.</div>}
          {selectedDataset && canRead && <>
            {taskQuery.isPending && <p role="status">Đang tải Task/Job…</p>}
            {taskQuery.isError && <div className="lx-callout" role="alert">{errorMessage(taskQuery.error)}
              <button className="lx-btn" type="button" onClick={() => void taskQuery.refetch()}>Thử lại</button></div>}
            {taskQuery.data && <SnapshotForm key={`${session.user.id}:${datasetId}`} datasetId={datasetId!}
              tasks={taskQuery.data} canCreate={canCreate} onRequestLockChange={setRequestLocked} />}
          </>}
        </div></section>
      <section className="lx-card lx-side"><div className="lx-card__head"><h2 className="lx-h2">Snapshot gần nhất đã khóa</h2></div>
        <div className="lx-card__body">{recent.isError ? <div className="lx-callout" role="alert">{errorMessage(recent.error)}
          <button className="lx-btn" type="button" onClick={() => void recent.refetch()}>Thử lại</button></div>
        : recentLocked ? <dl className="lx-kv">
          <dt>Mã</dt><dd><Link href={`/analysis?snapshotId=${recentLocked.id}`}>SNP-{recentLocked.id}</Link></dd>
          <dt>Hash</dt><dd className="lx-mono" style={{ overflowWrap: 'anywhere' }}>{recentLocked.revision_hash || '—'}</dd>
          <dt>Shape bỏ qua</dt><dd>{recentLocked.out_of_scope_shapes ?? '—'}</dd>
        </dl> : <p className="lx-muted">{recent.isPending && datasetId ? 'Đang tải…' : 'Chưa có Snapshot đã khóa.'}</p>}</div>
      </section>
    </div>}
  </AppShell>;
}

export default function AnalysisPage() {
  return <Suspense fallback={<p role="status">Đang mở Snapshot…</p>}><SnapshotWorkspace /></Suspense>;
}
