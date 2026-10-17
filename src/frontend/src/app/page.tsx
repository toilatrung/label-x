'use client';

import React, { Suspense, useEffect, useRef, useState, useCallback } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { AppShell } from '@/components/layout/AppShell';
import { ContextBar } from '@/components/layout/ContextBar';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { useAuth } from '@/lib/auth/auth-context';
import { getDatasets, cursorFrom, type Dataset } from '@/lib/snapshots/api';
import type { Run } from '@/lib/execution/api';
import type { RunState } from '@/components/layout/ContextBar';
import { QualityControlHome } from '@/components/overview/QualityControlHome';
import { QualitySummary } from '@/components/overview/QualitySummary';
import { ApiRequestError, errorMessage } from '@/lib/api/errors';
import { useLatestRun } from '@/lib/overview/api';
import { runStatusLabel } from '@/lib/execution/api';
import { snapshotCode } from '@/lib/format';

type DatasetResolution =
  | { authUserId: number | null; requestedId: null; status: 'idle' }
  | { authUserId: number | null; requestedId: number; status: 'loading' }
  | { authUserId: number | null; requestedId: number; status: 'resolved'; dataset: Dataset }
  | { authUserId: number | null; requestedId: number; status: 'revoked' }
  | { authUserId: number | null; requestedId: number; status: 'error'; message: string; isForbidden: boolean };

function OverviewContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const viewParam = searchParams.get('view');
  const isSummary = viewParam === 'summary';

  const { user, datasetId, setDatasetId } = useAuth();
  const currentUserId = user?.id ?? null;

  const [runSelection, setRunSelection] = useState<{
    userId: number | null;
    datasetId: number | null;
    run: Run | null;
  }>({
    userId: currentUserId,
    datasetId,
    run: null,
  });

  const effectiveSelectedRun =
    runSelection.userId === currentUserId && runSelection.datasetId === datasetId
      ? runSelection.run
      : null;

  // Resolution state keyed strictly to requested datasetId AND current auth user
  const [resolution, setResolution] = useState<DatasetResolution>(() => {
    if (datasetId !== null) {
      return { authUserId: currentUserId, requestedId: datasetId, status: 'loading' };
    }
    return { authUserId: currentUserId, requestedId: null, status: 'idle' };
  });

  const [retryNonce, setRetryNonce] = useState(0);

  const [taskScopeSelection, setTaskScopeSelection] = useState<{
    userId: number | null;
    datasetId: number | null;
    scope: string | null;
  }>({
    userId: currentUserId,
    datasetId,
    scope: null,
  });

  const effectiveTaskScope =
    taskScopeSelection.userId === currentUserId &&
    taskScopeSelection.datasetId === datasetId
      ? taskScopeSelection.scope
      : null;

  const handleSetTaskScope = useCallback(
    (scope: string | null) => {
      setTaskScopeSelection({
        userId: currentUserId,
        datasetId,
        scope,
      });
    },
    [currentUserId, datasetId]
  );

  const resolveGen = useRef(0);
  const knownDataset = useRef<Dataset | null>(null);
  const lastUserId = useRef(currentUserId);

  // Derive truthful loading and resolution state: must match current datasetId AND current user
  const isResolutionCurrent =
    datasetId !== null &&
    resolution.requestedId === datasetId &&
    resolution.authUserId === currentUserId;

  const effectiveStatus: 'idle' | 'loading' | 'resolved' | 'revoked' | 'error' = (() => {
    if (datasetId === null) return 'idle';
    if (!isResolutionCurrent) return 'loading';
    return resolution.status;
  })();

  const currentDataset: Dataset | null = (() => {
    if (
      datasetId !== null &&
      isResolutionCurrent &&
      resolution.status === 'resolved' &&
      resolution.dataset.id === datasetId
    ) {
      return resolution.dataset;
    }
    return null;
  })();

  // Synchronize or resolve current dataset against real scoped paginated API
  useEffect(() => {
    if (lastUserId.current !== currentUserId) {
      lastUserId.current = currentUserId;
      knownDataset.current = null;
      Promise.resolve().then(() => {
        setRunSelection({ userId: currentUserId, datasetId, run: null });
        setTaskScopeSelection({ userId: currentUserId, datasetId, scope: null });
      });
    }

    const gen = ++resolveGen.current;
    const targetUserId = currentUserId;

    if (datasetId === null) {
      Promise.resolve().then(() => {
        if (gen === resolveGen.current) {
          setResolution({ authUserId: targetUserId, requestedId: null, status: 'idle' });
        }
      });
      return;
    }

    const resolvedTargetId: number = datasetId;

    // If already known from Home selection and ID matches, use it immediately
    if (knownDataset.current && knownDataset.current.id === resolvedTargetId) {
      const ds = knownDataset.current;
      Promise.resolve().then(() => {
        if (gen === resolveGen.current) {
          setResolution({ authUserId: targetUserId, requestedId: resolvedTargetId, status: 'resolved', dataset: ds });
        }
      });
      return;
    }

    Promise.resolve().then(() => {
      if (gen === resolveGen.current) {
        setResolution({ authUserId: targetUserId, requestedId: resolvedTargetId, status: 'loading' });
      }
    });

    let active = true;

    async function findDatasetInScopedApi() {
      try {
        let cursor: string | undefined = undefined;
        let match: Dataset | undefined = undefined;
        const seenCursors = new Set<string>();

        // Traverse scoped paginated results until match found or pages exhausted
        while (active && gen === resolveGen.current) {
          if (cursor) {
            if (seenCursors.has(cursor)) {
              setResolution({
                authUserId: targetUserId,
                requestedId: resolvedTargetId,
                status: 'error',
                message: 'Phát hiện vòng lặp phân trang từ server khi xác minh Dataset.',
                isForbidden: false,
              });
              return;
            }
            seenCursors.add(cursor);
          }

          const page = await getDatasets(cursor);
          if (!active || gen !== resolveGen.current) return;

          match = page.results?.find((d) => d.id === resolvedTargetId);
          if (match) break;

          cursor = cursorFrom(page.next);
          if (!cursor) break;
        }

        if (!active || gen !== resolveGen.current) return;

        if (match) {
          knownDataset.current = match;
          setResolution({ authUserId: targetUserId, requestedId: resolvedTargetId, status: 'resolved', dataset: match });
        } else {
          // Never fabricate dataset identity or permissions
          setResolution({ authUserId: targetUserId, requestedId: resolvedTargetId, status: 'revoked' });
        }
      } catch (err: unknown) {
        if (!active || gen !== resolveGen.current) return;
        const isForbidden = err instanceof ApiRequestError && err.status === 403;
        setResolution({
          authUserId: targetUserId,
          requestedId: resolvedTargetId,
          status: 'error',
          message: isForbidden
            ? 'Bạn không có quyền truy cập thông tin Dataset này.'
            : errorMessage(err) || 'Không thể tải thông tin Dataset từ server.',
          isForbidden,
        });
      }
    }

    void findDatasetInScopedApi();

    return () => {
      active = false;
    };
  }, [datasetId, currentUserId, retryNonce]);

  const handleDatasetSelect = useCallback(
    (ds: Dataset) => {
      knownDataset.current = ds;
      setDatasetId(ds.id);
      setRunSelection({ userId: currentUserId, datasetId: ds.id, run: null });
      setTaskScopeSelection({ userId: currentUserId, datasetId: ds.id, scope: null });
      setResolution({ authUserId: currentUserId, requestedId: ds.id, status: 'resolved', dataset: ds });
    },
    [currentUserId, setDatasetId]
  );

  const handleSelectAnother = () => {
    knownDataset.current = null;
    setDatasetId(null);
    setRunSelection({ userId: currentUserId, datasetId: null, run: null });
    setTaskScopeSelection({ userId: currentUserId, datasetId: null, scope: null });
    setResolution({ authUserId: currentUserId, requestedId: null, status: 'idle' });
    router.push('/');
  };

  const handleRetry = () => {
    if (datasetId !== null) {
      setResolution({ authUserId: currentUserId, requestedId: datasetId, status: 'loading' });
    }
    setRetryNonce((prev) => prev + 1);
  };

  // Run hiển thị ở context bar: run đã chọn, nếu chưa chọn thì run mới nhất thật của Dataset (GET /api/runs/?dataset=).
  const latestRun = useLatestRun(isSummary && currentDataset && !effectiveSelectedRun ? currentDataset.id : null);
  const contextRun = effectiveSelectedRun ?? (isSummary && currentDataset ? latestRun.data ?? null : null);
  const RUN_STATE: Partial<Record<Run['status'], RunState>> = {
    completed: 'checked', partial: 'partial', running: 'running', queued: 'running', failed: 'failed',
  };

  const contextProps: React.ComponentProps<typeof ContextBar> = {
    datasetName: currentDataset?.name,
    datasetIdOverride: effectiveStatus === 'revoked' ? null : datasetId,
    guidelineVersion: currentDataset?.guideline_version ?? '—',
    taxonomyVersion: currentDataset?.taxonomy_version ?? '—',
    activeRun: contextRun ? `#${contextRun.id} · ${runStatusLabel[contextRun.status] ?? contextRun.status}` : 'Chưa chọn',
    runState: contextRun ? RUN_STATE[contextRun.status] : undefined,
    snapshotName: contextRun ? snapshotCode(contextRun.snapshot_id) : 'Chưa chọn',
  };

  return (
    <AppShell activeKey="overview" context={contextProps}>
      {isSummary ? (
        datasetId === null ? (
          <QualitySummary currentDataset={null} />
        ) : effectiveStatus === 'loading' ? (
          <div className="lx-card lx-state--card-muted">
            Đang xác minh thông tin Dataset #{datasetId}...
          </div>
        ) : effectiveStatus === 'revoked' ? (
          <>
            <div className="lx-card lx-state--card lx-mb-4">
              <h2 className="lx-h2">Dataset không khả dụng</h2>
              <p className="lx-lead lx-mt-2">
                Dataset đã chọn không tồn tại hoặc tài khoản của bạn không còn quyền truy cập trong phạm vi này.
              </p>
              <div className="lx-mt-4">
                <button type="button" className="lx-btn lx-btn--primary" onClick={handleSelectAnother}>
                  Chọn Dataset khác
                </button>
              </div>
            </div>
            <QualitySummary currentDataset={null} />
          </>
        ) : effectiveStatus === 'error' && resolution.status === 'error' ? (
          <>
            <div className="lx-card lx-state--card lx-mb-4">
              <h2 className="lx-h2 lx-text-danger">Lỗi kiểm tra quyền Dataset</h2>
              <p className="lx-lead lx-mt-2">
                {resolution.message}
              </p>
              <div className="lx-mt-4 lx-row lx-justify-center">
                {!resolution.isForbidden && (
                  <button type="button" className="lx-btn lx-mr-3" onClick={handleRetry}>
                    Thử lại
                  </button>
                )}
                <button type="button" className="lx-btn lx-btn--primary" onClick={handleSelectAnother}>
                  Về danh sách Dataset
                </button>
              </div>
            </div>
            <QualitySummary currentDataset={null} />
          </>
        ) : (
          <QualitySummary
            key={currentUserId !== null && currentDataset?.id ? `${currentUserId}:${currentDataset.id}` : (currentDataset?.id ?? 'none')}
            currentDataset={currentDataset}
            selectedRun={effectiveSelectedRun}
            selectedTaskScope={effectiveTaskScope}
            onTaskScopeChange={handleSetTaskScope}
          />
        )
      ) : (
        <QualityControlHome onDatasetSelect={handleDatasetSelect} />
      )}
    </AppShell>
  );
}

export default function Home() {
  return (
    <AuthGuard>
      <Suspense
        fallback={
          <div className="lx lx-minh-screen lx-bg-canvas lx-p-6">
            <span className="lx-hint">Đang tải...</span>
          </div>
        }
      >
        <OverviewContent />
      </Suspense>
    </AuthGuard>
  );
}
