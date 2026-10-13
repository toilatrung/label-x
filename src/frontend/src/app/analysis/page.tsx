'use client';

import React, { Suspense } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { AppShell } from '@/components/layout/AppShell';
import { FlowNav } from '@/components/layout/FlowNav';
import { ForbiddenView } from '@/components/auth/ForbiddenView';
import { SnapshotDetail } from '@/components/snapshots/SnapshotDetail';
import { SnapshotForm } from '@/components/snapshots/SnapshotForm';
import { SnapshotInUseExtra, SnapshotRevisionFields } from '@/components/snapshots/SnapshotSample';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, hasDatasetPermission } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import { formatDateTime, shortRevision, snapshotCode } from '@/lib/format';
import { useDatasetRuns, useDatasets, usePublishedConfigs, useSnapshot, useSnapshotHistory, useTasks } from '@/lib/snapshots/queries';
import { latestRunBySnapshot } from '@/lib/snapshots/runs';

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

  const datasetRuns = useDatasetRuns(userId, datasetId, canRead && !id && !datasetQuery.isError);
  const publishedConfigs = usePublishedConfigs(userId, canRead && !id && !datasetQuery.isError);
  const inUseRun = recentLocked ? latestRunBySnapshot(datasetRuns.data ?? []).get(recentLocked.id) : undefined;
  const inUseConfig = inUseRun ? publishedConfigs.data?.results.find(config => config.id === inUseRun.config_version_id) : undefined;

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
  if (!canEnter) return <ForbiddenView requiredPermission="Quality Assurance Lead / Quality Control Admin / Super Admin" />;

  const isSearchingLocked =
    !recentLocked &&
    !paginationError &&
    !recent.isError &&
    (recent.isPending || recent.isFetchingNextPage || recent.hasNextPage);

  return <AppShell activeKey="analysis" flowStep={1} showFlowNav={false}
    context={{
      datasetName: displayDatasetName,
      datasetIdOverride: item?.dataset_id,
      snapshotName: item ? `${snapshotCode(item.id)} · ${item.status}` : undefined,
      snapshotRevision: item?.revision_hash ? shortRevision(item.revision_hash) : undefined,
      isReadOnly: item?.status === 'locked',
      guidelineVersion: displayGuideline,
      taxonomyVersion: displayTaxonomy,
    }}
    pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Snapshot</h1>
      <p className="lx-lead">Snapshot khoá một phiên bản annotation để kiểm tra. Snapshot không thể sửa; nếu annotation thay đổi, hệ thống tạo revision và snapshot mới.</p></div>
      {id ? <div className="lx-actions"><Link className="lx-btn" href="/analysis">Tạo snapshot mới</Link></div> : null}</div>}>
    {rawId && !id && <div className="lx-callout" role="alert">ID Snapshot không hợp lệ.</div>}
    {id ? <>
      <FlowNav flow="analysis" currentStep={1} variant="tabs" />
      {detail.isPending && <p role="status">Đang tải Snapshot #{id}…</p>}
      {detail.isError && <div className="lx-callout" role="alert">{errorMessage(detail.error)}
        <button className="lx-btn" type="button" onClick={() => void detail.refetch()}>Thử lại</button></div>}
      {detail.isSuccess && !item && <div className="lx-callout" role="alert">Bạn không có quyền xem Snapshot này.</div>}
      {item && <SnapshotDetail item={item} />}
    </> : <div className="lx-cols">
      <section className="lx-card lx-main" aria-label="Tạo snapshot mới">
        <FlowNav flow="analysis" currentStep={1} variant="tabs" inCard />
        <div className="lx-card__head"><h2 className="lx-h2">Tạo snapshot mới</h2></div>
        <div className="lx-card__body lx-stack">
              <SnapshotRevisionFields dataset={
                <div className="lx-field"><label className="lx-label" htmlFor="snapshot-dataset">Dataset / project CVAT</label>
                  <select id="snapshot-dataset" className="lx-select" value={datasetId ?? ''} disabled={requestLocked || datasetQuery.isPending || datasetQuery.isError}
                    onChange={event => setDatasetId(event.target.value ? Number(event.target.value) : null)}>
                    <option value="">Chọn Dataset</option>
                    {datasetId !== null && !selectedDataset && <option value={datasetId}>Dataset #{datasetId}</option>}
                    {allDatasets.map(dataset => <option key={dataset.id} value={dataset.id}>
                      {dataset.name} · project #{dataset.cvat_project_id}</option>)}
                  </select></div>} />
              {datasetQuery.isPending && <p role="status">Đang tải Dataset…</p>}
              {datasetQuery.isError && <div className="lx-callout" role="alert">{errorMessage(datasetQuery.error)}
                <button className="lx-btn" type="button" onClick={() => void datasetQuery.refetch()}>Thử lại</button></div>}
              {datasetQuery.hasNextPage && <button className="lx-btn" type="button" disabled={datasetQuery.isFetchingNextPage}
                onClick={() => void datasetQuery.fetchNextPage()}>Tải thêm Dataset</button>}
              {datasetQuery.isSuccess && !allDatasets.length && <p className="lx-muted">Chưa có Dataset trong phạm vi truy cập CVAT của bạn.</p>}
              {datasetId === null && <p className="lx-muted">Vui lòng chọn một Dataset để tạo Snapshot.</p>}
              {datasetId !== null && !selectedDataset && allDatasets.length > 0 && datasetQuery.isSuccess && (
                <div className="lx-callout" role="alert">Dataset không tồn tại hoặc bạn không có quyền truy cập.</div>
              )}
              {selectedDataset && !canRead && <div className="lx-callout" role="alert">Bạn không có quyền xem Dataset này.</div>}
              {selectedDataset && canRead && !datasetQuery.isError && <>
                {taskQuery.isPending && <p role="status">Đang tải Task/Job…</p>}
                {taskQuery.isError && <div className="lx-callout" role="alert">{errorMessage(taskQuery.error)}
                  <button className="lx-btn" type="button" onClick={() => void taskQuery.refetch()}>Thử lại</button></div>}
                {taskQuery.data && !taskQuery.isError && <SnapshotForm key={`${session.user.id}:${datasetId}`} datasetId={datasetId!}
                  tasks={taskQuery.data} canCreate={canCreate} onRequestLockChange={setRequestLocked} />}
              </>}
        </div>
      </section>
      <section className="lx-card lx-side" aria-label="Snapshot đang dùng"><div className="lx-card__head"><h2 className="lx-h2">Snapshot đang dùng</h2>
        {recentLocked && !recent.isError && !datasetQuery.isError && <span className="lx-badge lx-badge--success">Đã khoá</span>}</div>
        <div className="lx-card__body">{datasetQuery.isError ? <p className="lx-muted">Không thể tải Snapshot đang dùng khi chưa xác minh được Dataset.</p>
        : recent.isError ? <div className="lx-callout" role="alert">{errorMessage(recent.error)}
          <button className="lx-btn" type="button" onClick={() => void recent.refetch()}>Thử lại lịch sử Snapshot</button></div>
        : paginationError ? <div className="lx-callout" role="alert">{paginationError}</div>
        : recentLocked ? <div className="lx-stack"><dl className="lx-kv">
          <dt>Mã snapshot</dt><dd className="lx-mono"><Link href={`/analysis?snapshotId=${recentLocked.id}`}>{snapshotCode(recentLocked.id)}</Link></dd>
          <dt>Annotation revision</dt><dd className="lx-mono" title={recentLocked.revision_hash ?? undefined}>{shortRevision(recentLocked.revision_hash)}</dd>
          <dt>Taxonomy</dt><dd className="lx-wrap-any" title={recentLocked.taxonomy_version ?? undefined}>{recentLocked.taxonomy_version || '—'}</dd>
          <dt>Guideline</dt><dd className="lx-wrap-any">{recentLocked.guideline_version || '—'}</dd>
          <dt>Tạo bởi</dt><dd>User #{recentLocked.created_by} · {formatDateTime(recentLocked.created_at)}</dd>
        </dl>
          {datasetRuns.isError ? <SnapshotInUseExtra error={errorMessage(datasetRuns.error)} /> : <dl className="lx-kv lx-stack--divider" aria-label="Quality Control Run mới nhất của Snapshot">
            <dt>Mô hình độc lập</dt><dd>{datasetRuns.isPending ? 'Đang tải…' : inUseRun?.model_artifact ? `${inUseRun.model_artifact.name} ${inUseRun.model_artifact.version}` : '—'}</dd>
            <dt>Cấu hình kiểm tra</dt><dd>{datasetRuns.isPending ? 'Đang tải…' : inUseRun ? (inUseConfig?.name ?? `Phiên bản #${inUseRun.config_version_id}`) : '—'}</dd>
            <dt>Seed lấy mẫu</dt><dd className="lx-mono">{datasetRuns.isPending ? 'Đang tải…' : inUseRun ? inUseRun.seed : '—'}</dd>
          </dl>}
          {datasetRuns.isSuccess && !inUseRun && <p className="lx-muted lx-text-13">Snapshot này chưa có Quality Control Run nên chưa có mô hình, cấu hình và seed.</p>}
        </div> : isSearchingLocked && datasetId ? (
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
