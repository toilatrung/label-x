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
  const recentLocked = recent.data?.pages
    .flatMap(page => page.results)
    .find(item => item.dataset_id === datasetId && item.status === 'locked');

  const [paginationError, setPaginationError] = React.useState<string | null>(null);
  const visitedCursorsRef = React.useRef<Set<string>>(new Set());
  const prevDatasetIdRef = React.useRef<number | null>(datasetId);

  React.useEffect(() => {
    if (prevDatasetIdRef.current !== datasetId) {
      prevDatasetIdRef.current = datasetId;
      visitedCursorsRef.current.clear();
      setPaginationError(null);
    }
  }, [datasetId]);

  // R-1 / F-2: Auto-fetch next pages of snapshot history until locked snapshot is found or all pages exhausted
  React.useEffect(() => {
    if (
      !canRead ||
      datasetId === null ||
      recentLocked ||
      recent.isError ||
      recent.isFetchingNextPage ||
      !recent.hasNextPage ||
      paginationError
    ) {
      return;
    }
    const pages = recent.data?.pages;
    if (!pages || pages.length === 0) return;
    const lastPage = pages[pages.length - 1];
    const nextCursor = lastPage?.next;
    if (!nextCursor) return;

    if (visitedCursorsRef.current.has(nextCursor)) {
      setPaginationError('Phát hiện vòng lặp cursor từ máy chủ.');
      return;
    }
    visitedCursorsRef.current.add(nextCursor);
    void recent.fetchNextPage();
  }, [
    canRead,
    datasetId,
    recentLocked,
    recent.isError,
    recent.isFetchingNextPage,
    recent.hasNextPage,
    recent.data?.pages,
    paginationError,
    recent,
  ]);

  React.useEffect(() => { if (!isLoading && !session) router.replace('/login'); }, [isLoading, session, router]);

  const item = detail.data && hasDatasetPermission(session, detail.data.dataset_id, canAccessAnalysis) ? detail.data : null;

  // F-1: Resolve dataset context from Snapshot detail when deep-linked
  const snapshotDataset = allDatasets.find(d => d.id === item?.dataset_id);

  // If viewing a snapshot whose dataset is on a subsequent page, load next pages to resolve name
  React.useEffect(() => {
    if (item && !snapshotDataset && datasetQuery.hasNextPage && !datasetQuery.isFetchingNextPage) {
      void datasetQuery.fetchNextPage();
    }
  }, [item, snapshotDataset, datasetQuery.hasNextPage, datasetQuery.isFetchingNextPage, datasetQuery]);

  const displayDatasetName = item ? snapshotDataset?.name : selectedDataset?.name;
  const displayGuideline = item ? (item.guideline_version ?? snapshotDataset?.guideline_version ?? undefined)
    : (selectedDataset?.guideline_version ?? undefined);
  const displayTaxonomy = item ? (item.taxonomy_version ?? snapshotDataset?.taxonomy_version ?? undefined)
    : (selectedDataset?.taxonomy_version ?? undefined);

  if (isLoading || !session) return <p role="status">Đang tải phiên làm việc…</p>;
  if (!canEnter) return <ForbiddenView requiredPermission="QA Lead / QC Admin / Super Admin" />;

  const isSearchingLocked =
    !recentLocked &&
    !paginationError &&
    !recent.isError &&
    (recent.isPending || recent.isFetchingNextPage || recent.hasNextPage);

  return <AppShell activeKey="analysis" flowStep={1}
    context={{
      datasetName: displayDatasetName,
      datasetIdOverride: item?.dataset_id,
      snapshotName: item ? `SNP-${item.id} · ${item.status}` : undefined,
      guidelineVersion: displayGuideline,
      taxonomyVersion: displayTaxonomy,
    }}
    pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Snapshot</h1>
      <p className="lx-lead">Chốt phiên bản annotation để kiểm tra. Annotation thay đổi sẽ tạo Snapshot mới.</p></div>
      <div className="lx-actions"><Link className="lx-btn" href="/analysis/snapshots">Lịch sử Snapshot</Link>
        <Link className="lx-btn" href="/analysis/config">Cấu hình và tạo QC run</Link>
        <Link className="lx-btn" href="/analysis/history">Lịch sử thực thi</Link>
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
          {datasetQuery.isSuccess && !allDatasets.length && (
            <p className="lx-muted">Chưa có Dataset nào trong phạm vi tài khoản của bạn.</p>
          )}
          {datasetQuery.hasNextPage && <button className="lx-btn" type="button" disabled={datasetQuery.isFetchingNextPage}
            onClick={() => void datasetQuery.fetchNextPage()}>Tải thêm Dataset</button>}
          {datasetId === null && <p className="lx-muted">Vui lòng chọn một Dataset để tạo Snapshot.</p>}
          {datasetId !== null && !selectedDataset && datasetQuery.isSuccess && (
            <div className="lx-callout" role="alert">Dataset không tồn tại hoặc bạn không có quyền truy cập.</div>
          )}
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
        : paginationError ? <div className="lx-callout" role="alert">{paginationError}</div>
        : recentLocked ? <dl className="lx-kv">
          <dt>Mã</dt><dd><Link href={`/analysis?snapshotId=${recentLocked.id}`}>SNP-{recentLocked.id}</Link></dd>
          <dt>Hash</dt><dd className="lx-mono" style={{ overflowWrap: 'anywhere' }}>{recentLocked.revision_hash || '—'}</dd>
          <dt>Shape bỏ qua</dt><dd>{recentLocked.out_of_scope_shapes ?? '—'}</dd>
        </dl> : isSearchingLocked && datasetId ? (
          <p className="lx-muted" role="status">Đang tải…</p>
        ) : (
          <p className="lx-muted">{datasetId === null ? 'Vui lòng chọn một Dataset để tạo Snapshot.' : 'Chưa có Snapshot đã khóa.'}</p>
        )}</div>
      </section>
    </div>}
  </AppShell>;
}

export default function AnalysisPage() {
  return <Suspense fallback={<p role="status">Đang mở Snapshot…</p>}><SnapshotWorkspace /></Suspense>;
}
