'use client';

import React, { useState, useTransition, useRef, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import {
  getRunDetails,
  getRunRanking,
  claimNextFrame,
  renewLease,
  cursorFrom,
} from '@/lib/review/api';
import type {
  QueueName,
  IssueFamily,
  IssueOrigin,
  FrameReviewState,
  RankedFrame,
  LeaseGrant,
  ReviewQueueFilters,
} from '@/lib/review/types';
import { ReviewDatasetPicker } from './ReviewDatasetPicker';
import { ReviewWorkspace } from './ReviewWorkspace';
import { ReviewQueueSample } from './ReviewQueueSample';
import { Icon } from '@/components/ui/Icon';
import { ApiRequestError, errorMessage } from '@/lib/api/errors';

export interface ReviewQueuesProps {
  onWorkspaceStateChange?: (state: {
    isOpen: boolean;
    frameId?: number;
    runId?: number | null;
    leaseId?: number;
    taskCvatId?: number;
  }) => void;
}

export function ReviewQueues({ onWorkspaceStateChange }: ReviewQueuesProps = {}) {
  const { datasetId, session } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [, startTransition] = useTransition();

  // Run ID selection: URL is the source of truth, bound to the dataset context
  const runParam = searchParams.get('run');
  const parsedRunId =
    runParam && /^\d+$/.test(runParam.trim()) && Number(runParam) > 0
      ? Number(runParam)
      : null;

  // Track dataset binding and selected run
  const [boundDatasetId, setBoundDatasetId] = useState<number | null>(datasetId);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(parsedRunId);
  const [runInput, setRunInput] = useState<string>(parsedRunId ? String(parsedRunId) : '');
  const [prevRunParam, setPrevRunParam] = useState(runParam);

  // Queue tab selection: 'risk' vs 'random'
  const [activeQueue, setActiveQueue] = useState<QueueName>('risk');

  // Server filters
  const [filters, setFilters] = useState<ReviewQueueFilters>({});

  // Pagination cursor
  const [cursor, setCursor] = useState<string | null>(null);

  // Active Lease Grant state (from claim or resume)
  const [activeGrant, setActiveGrant] = useState<LeaseGrant | null>(null);
  const [claimStatus204, setClaimStatus204] = useState<boolean>(false);
  const [claimError, setClaimError] = useState<{ message: string; code?: string } | null>(null);
  const [renewMessage, setRenewMessage] = useState<string | null>(null);
  const [isLeaseConflict, setIsLeaseConflict] = useState<boolean>(false);
  const [isWorkspaceOpen, setIsWorkspaceOpen] = useState<boolean>(false);

  // Pure tick state for lease countdown to avoid impure Date.now() during render
  const [now, setNow] = useState<number>(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  // User context tracking: reset workspace and active lease if reviewer changes
  const currentUserId = session?.user?.id ?? null;
  const [boundUserId, setBoundUserId] = useState<number | null>(currentUserId);
  if (boundUserId !== currentUserId) {
    setBoundUserId(currentUserId);
    setIsWorkspaceOpen(false);
    setActiveGrant(null);
  }

  // Track whether initial page-load dataset binding has completed
  const [hasInitializedDataset, setHasInitializedDataset] = useState(Boolean(datasetId));

  // Synchronous state adjustment during render when datasetId or URL run changes
  // Follows official React pattern: "Adjusting some state when a prop changes"
  // (https://react.dev/learn/you-might-not-need-an-effect#adjusting-some-state-when-a-prop-changes)
  const isGenuineDatasetChange = boundDatasetId !== null && datasetId !== boundDatasetId;
  if (isGenuineDatasetChange) {
    setBoundDatasetId(datasetId);
    setSelectedRunId(null);
    setRunInput('');
    setActiveGrant(null);
    setClaimStatus204(false);
    setClaimError(null);
    setRenewMessage(null);
    setIsLeaseConflict(false);
    setCursor(null);
    setIsWorkspaceOpen(false);
  } else if (!hasInitializedDataset && datasetId !== null) {
    // Initial dataset resolution at page load: bind initial dataset and deep-linked run
    setHasInitializedDataset(true);
    setBoundDatasetId(datasetId);
    if (parsedRunId) {
      setSelectedRunId(parsedRunId);
      setRunInput(String(parsedRunId));
    }
  } else if (boundDatasetId === null && datasetId !== null) {
    // Dataset chosen after being unselected: do NOT resurrect old run from stale URL param
    setBoundDatasetId(datasetId);
    setSelectedRunId(null);
    setRunInput('');
    setIsWorkspaceOpen(false);
  } else if (runParam !== prevRunParam) {
    setPrevRunParam(runParam);
    setIsWorkspaceOpen(false);
    setActiveGrant(null);
    if (boundDatasetId === datasetId && datasetId !== null) {
      if (parsedRunId) {
        setSelectedRunId(parsedRunId);
        setRunInput(String(parsedRunId));
      } else {
        setSelectedRunId(null);
        setRunInput('');
      }
    }
  }

  // Effective run ID: immediately null on dataset change until a run is chosen for the new dataset
  const effectiveRunId = isGenuineDatasetChange ? null : selectedRunId;

  // Safe side effect: clean up URL ?run parameter when dataset has changed or run is unselected
  useEffect(() => {
    if (selectedRunId === null && runParam) {
      startTransition(() => {
        router.replace('/review');
      });
    }
  }, [selectedRunId, runParam, router]);

  // Ref tracking latest context for mutation guards, updated during commit phase
  const contextRef = useRef({ datasetId, activeRunId: effectiveRunId, currentUserId });
  useEffect(() => {
    contextRef.current = { datasetId, activeRunId: effectiveRunId, currentUserId };
  }, [datasetId, effectiveRunId, currentUserId]);

  useEffect(() => {
    onWorkspaceStateChange?.({
      isOpen: isWorkspaceOpen && Boolean(activeGrant && effectiveRunId),
      frameId: activeGrant?.frame.id,
      runId: effectiveRunId,
      leaseId: activeGrant?.lease.id,
      taskCvatId: activeGrant?.frame.frame_key.cvat_task_id,
    });
  }, [isWorkspaceOpen, activeGrant, effectiveRunId, onWorkspaceStateChange]);

  // Reset pagination cursor when queue or filters change
  const handleQueueChange = (queue: QueueName) => {
    setActiveQueue(queue);
    setCursor(null);
  };

  const handleFilterChange = (newFilters: Partial<ReviewQueueFilters>) => {
    setFilters((prev) => ({ ...prev, ...newFilters }));
    setCursor(null);
  };

  const handleResetFilters = () => {
    setFilters({});
    setCursor(null);
  };

  const handleRunSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = runInput.trim();
    if (/^\d+$/.test(trimmed)) {
      const parsed = Number(trimmed);
      if (parsed > 0) {
        setCursor(null);
        setSelectedRunId(parsed);
        setBoundDatasetId(datasetId);
        setActiveGrant(null);
        setIsWorkspaceOpen(false);
        startTransition(() => {
          router.push(`/review?run=${parsed}`);
        });
      }
    }
  };

  // 1. Fetch Run details to confirm run existence.
  // Note: In OpenAPI M-03, QCRun schema does not include dataset_id. Reviewer role cannot call
  // GET /api/runs/ (list) or GET /api/snapshots/{id}/. Therefore, the UI cannot independently verify
  // that the run belongs to the currently selected dataset; backend RBAC (HasRoleAndDatasetScope)
  // remains the sole authority for scoping and access control.
  const runQuery = useQuery({
    queryKey: ['review', 'run', datasetId, effectiveRunId],
    queryFn: ({ signal }) => getRunDetails(effectiveRunId!, signal),
    enabled: Boolean(effectiveRunId && effectiveRunId > 0 && datasetId),
  });

  // 2. Fetch Ranking data for active queue & filters.
  // Gated on runQuery.isSuccess: on 403/404 or load failure, ranking is NOT called.
  const rankingQuery = useQuery({
    queryKey: [
      'review',
      'ranking',
      datasetId,
      effectiveRunId,
      activeQueue,
      filters.family,
      filters.origin,
      filters.review_state,
      cursor,
    ],
    queryFn: ({ signal }) =>
      getRunRanking(effectiveRunId!, {
        queue: activeQueue,
        family: filters.family,
        origin: filters.origin,
        review_state: filters.review_state,
        cursor,
        signal,
      }),
    enabled: Boolean(
      datasetId &&
        effectiveRunId &&
        effectiveRunId > 0 &&
        runQuery.isSuccess &&
        session?.identity_mapping.status === 'mapped'
    ),
  });

  // 3. Mutation for Claim Next Frame
  const claimMutation = useMutation({
    onMutate: () => {
      setClaimStatus204(false);
      setClaimError(null);
      setRenewMessage(null);
      setIsLeaseConflict(false);
      return {
        targetDatasetId: datasetId,
        targetRunId: effectiveRunId,
        targetUserId: currentUserId,
      };
    },
    mutationFn: async () => {
      return claimNextFrame(activeQueue, effectiveRunId!);
    },
    onSuccess: (result, _variables, context) => {
      // Discard if context switched while mutation was pending
      if (
        contextRef.current.activeRunId !== context?.targetRunId ||
        contextRef.current.datasetId !== context?.targetDatasetId ||
        contextRef.current.currentUserId !== context?.targetUserId
      ) {
        return;
      }
      if (result.status === 204) {
        setClaimStatus204(true);
      } else {
        setActiveGrant(result.grant);
        queryClient.invalidateQueries({
          queryKey: ['review', 'ranking', context.targetDatasetId, context.targetRunId],
        });
      }
    },
    onError: (err: unknown, _variables, context) => {
      // Discard if context switched while mutation was pending
      if (
        contextRef.current.activeRunId !== context?.targetRunId ||
        contextRef.current.datasetId !== context?.targetDatasetId ||
        contextRef.current.currentUserId !== context?.targetUserId
      ) {
        return;
      }
      if (err instanceof ApiRequestError) {
        if (err.detail?.code === 'LEASE_CONFLICT' || err.status === 409) {
          setIsLeaseConflict(true);
        }
        setClaimError({
          message: err.message,
          code: err.detail?.code,
        });
      } else {
        setClaimError({
          message: errorMessage(err),
        });
      }
    },
  });

  // 4. Mutation for Renew Lease
  const renewMutation = useMutation({
    onMutate: () => {
      return {
        targetDatasetId: datasetId,
        targetRunId: effectiveRunId,
        targetUserId: currentUserId,
      };
    },
    mutationFn: async (leaseId: number) => {
      return renewLease(leaseId);
    },
    onSuccess: (lease, _variables, context) => {
      // Discard if context switched while mutation was pending
      if (
        contextRef.current.activeRunId !== context?.targetRunId ||
        contextRef.current.datasetId !== context?.targetDatasetId ||
        contextRef.current.currentUserId !== context?.targetUserId
      ) {
        return;
      }
      setActiveGrant((prev) => (prev ? { ...prev, lease } : null));
      setRenewMessage(
        `Đã gia hạn lease thành công đến ${new Date(lease.expires_at).toLocaleTimeString()}`
      );
    },
    onError: (err: unknown, _variables, context) => {
      // Discard if context switched while mutation was pending
      if (
        contextRef.current.activeRunId !== context?.targetRunId ||
        contextRef.current.datasetId !== context?.targetDatasetId ||
        contextRef.current.currentUserId !== context?.targetUserId
      ) {
        return;
      }
      if (err instanceof ApiRequestError) {
        if (err.detail?.code === 'LEASE_CONFLICT' || err.status === 409) {
          setIsLeaseConflict(true);
        }
        setClaimError({
          message: err.message,
          code: err.detail?.code,
        });
      } else {
        setClaimError({
          message: errorMessage(err),
        });
      }
    },
  });

  const handleReloadServerState = () => {
    setIsWorkspaceOpen(false);
    setIsLeaseConflict(false);
    setActiveGrant(null);
    setClaimError(null);
    setRenewMessage(null);
    setClaimStatus204(false);
    queryClient.invalidateQueries({ queryKey: ['review', 'run', datasetId, effectiveRunId] });
    queryClient.invalidateQueries({ queryKey: ['review', 'ranking', datasetId, effectiveRunId] });
  };

  const isMatchingHolder = Boolean(
    activeGrant && currentUserId !== null && activeGrant.lease.holder_user_id === currentUserId
  );
  const leaseExpiresAtMs = activeGrant ? new Date(activeGrant.lease.expires_at).getTime() : NaN;
  const isLeaseExpiryFinite = Number.isFinite(leaseExpiresAtMs);
  const isLeaseExpired = !isLeaseExpiryFinite || leaseExpiresAtMs <= now;
  const isFrameRunMatching = Boolean(
    activeGrant && effectiveRunId !== null && activeGrant.frame.run_id === effectiveRunId
  );
  const isLeaseFrameMatching = Boolean(
    activeGrant && activeGrant.lease.frame_id === activeGrant.frame.id
  );
  const canOpenWorkspace = Boolean(
    activeGrant &&
      effectiveRunId &&
      isMatchingHolder &&
      isFrameRunMatching &&
      isLeaseFrameMatching &&
      isLeaseExpiryFinite &&
      !isLeaseExpired &&
      !isLeaseConflict
  );

  const nextCursor = cursorFrom(rankingQuery.data?.next);
  const prevCursor = cursorFrom(rankingQuery.data?.previous);

  return (
    <div className="lx-stack">
      {/* Context Bar / Controls */}
      <div className="lx-card lx-card--compact lx-stack">
        <div className="lx-cols lx-review-controls">
          <div className="lx-review-controls__dataset">
            <ReviewDatasetPicker
              onChange={() => {
                setCursor(null);
              }}
            />
          </div>

          <form onSubmit={handleRunSubmit} className="lx-review-controls__run">
            <div className="lx-field">
              <label htmlFor="review-run-id" className="lx-label">
                Mã Quality Control Run
              </label>
              <input
                id="review-run-id"
                className="lx-input"
                type="number"
                min={1}
                placeholder="Nhập mã (ví dụ 12)"
                value={runInput}
                onChange={(e) => setRunInput(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className="lx-btn lx-btn--primary"
              disabled={!runInput || Number(runInput) <= 0}
            >
              Tải hàng đợi
            </button>
          </form>
        </div>

        {/* Dataset validation notices */}
        {!datasetId && (
          <div role="status" className="lx-callout lx-callout--info">
            <div className="lx-callout__text">
              Chọn Dataset để xem hàng đợi kiểm tra.
            </div>
          </div>
        )}

        {datasetId && !effectiveRunId && (
          <div role="status" className="lx-callout lx-callout--info">
            <div className="lx-callout__text">
              Nhập mã Quality Control Run để tải hàng đợi kiểm tra.
            </div>
          </div>
        )}

        {runQuery.isError && effectiveRunId && (
          <div role="alert" className="lx-callout">
            <div className="lx-callout__text">
              Không thể tải thông tin Run #{effectiveRunId}: {errorMessage(runQuery.error)}
            </div>
          </div>
        )}
      </div>

      {/* Claim / Active Lease Context Banner */}
      {activeGrant && effectiveRunId && (
        <section
          className={`lx-card ${isLeaseConflict ? 'lx-card--lease-conflict' : 'lx-card--lease'}`}
          aria-label="Khung ngữ cảnh kiểm tra hiện tại"
        >
          <div
            className={`lx-card__head ${isLeaseConflict ? 'lx-card__head--lease-conflict' : 'lx-card__head--lease'}`}
          >
            <div className="lx-row">
              <strong>Phiên kiểm tra đang giữ (Active Lease)</strong>
              {activeGrant.resumed && (
                <span className="lx-badge lx-badge--warning">
                  Khôi phục phiên (Resumed)
                </span>
              )}
              {isLeaseConflict && (
                <span className="lx-badge lx-badge--danger">
                  Đã hết hạn / Xung đột
                </span>
              )}
            </div>
            <span className="lx-mono">Lease #{activeGrant.lease.id}</span>
          </div>
          <div className="lx-card__body lx-stack">
            <div className="lx-grid lx-grid--3">
              <div>
                <span className="lx-subtle">Frame Key:</span>{' '}
                <strong>
                  Task #{activeGrant.frame.frame_key.cvat_task_id} • Frame #
                  {activeGrant.frame.frame_key.frame_number}
                </strong>
                <div className="lx-subtle lx-mono">Frame ID: {activeGrant.frame.id}</div>
              </div>
              <div>
                <span className="lx-subtle">Thời hạn lease:</span>{' '}
                <strong className="lx-num">
                  {new Date(activeGrant.lease.expires_at).toLocaleString()}
                </strong>
                <div className="lx-subtle">
                  Người giữ: User #{activeGrant.lease.holder_user_id}
                </div>
              </div>
              <div>
                <span className="lx-subtle">Trạng thái review:</span>{' '}
                <span className="lx-badge lx-badge--info">
                  {activeGrant.frame.review_state}
                </span>
              </div>
            </div>

            {renewMessage && (
              <div role="status" className="lx-callout lx-callout--info">
                <div className="lx-callout__text">{renewMessage}</div>
              </div>
            )}

            <div className="lx-row lx-row--between">
              <div className="lx-row">
                {activeGrant.frame.cvat_deep_link && !isLeaseConflict && (
                  <a
                    href={activeGrant.frame.cvat_deep_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="lx-btn lx-btn--sm"
                  >
                    Mở frame trên CVAT
                  </a>
                )}
                <button
                  type="button"
                  className="lx-btn lx-btn--sm"
                  onClick={() => renewMutation.mutate(activeGrant.lease.id)}
                  disabled={renewMutation.isPending || isLeaseConflict || isWorkspaceOpen}
                  title={isWorkspaceOpen ? 'Workspace đang tự động quản lý vòng đời lease' : undefined}
                >
                  {renewMutation.isPending ? 'Đang gia hạn...' : 'Gia hạn lease (Renew)'}
                </button>
                {canOpenWorkspace && !isWorkspaceOpen && (
                  <button
                    type="button"
                    className="lx-btn lx-btn--sm lx-btn--primary"
                    onClick={() => setIsWorkspaceOpen(true)}
                  >
                    Vào kiểm tra frame (Workspace)
                  </button>
                )}
                {isLeaseConflict && (
                  <button
                    type="button"
                    className="lx-btn lx-btn--sm lx-btn--primary"
                    onClick={handleReloadServerState}
                  >
                    Tải lại từ server
                  </button>
                )}
              </div>
              <span className="lx-hint">
                Lease đã sẵn sàng cho màn kiểm tra.
              </span>
            </div>
          </div>
        </section>
      )}

      {/* Claim 204 Status Notification */}
      {claimStatus204 && (
        <div role="status" className="lx-callout lx-callout--info" aria-label="Thông báo hàng đợi hết frame">
          <div className="lx-callout__text">
            <strong>Hàng đợi không còn frame phù hợp để nhận kiểm tra (204 No Content).</strong>
          </div>
        </div>
      )}

      {/* Claim Error Notification */}
      {claimError && (
        <div role="alert" className="lx-callout" aria-label="Lỗi nhận frame">
          <div className="lx-callout__text">
            <strong>Không thể nhận frame:</strong> {claimError.message}
            {claimError.code && (
              <span className="lx-badge lx-badge--danger">
                {claimError.code}
              </span>
            )}
            {claimError.code === 'LEASE_CONFLICT' && (
              <div className="lx-mt-1">
                <p className="lx-review-note">
                  Quyền giữ frame đã hết hạn hoặc thuộc người khác (409 LEASE_CONFLICT). Thao tác với lease cũ đã bị khóa.
                </p>
                <button
                  type="button"
                  className="lx-btn lx-btn--sm"
                  onClick={handleReloadServerState}
                >
                  Tải lại từ server
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Review Workspace inline view or Review Queues Panel */}
      {isWorkspaceOpen && activeGrant && effectiveRunId ? (
        <section className="lx-stack lx-stack--4" aria-label="Không gian kiểm tra Review Workspace">
          <div className="lx-row lx-row--between lx-row--center">
            <button
              type="button"
              className="lx-btn"
              onClick={() => setIsWorkspaceOpen(false)}
            >
              ← Quay lại danh sách hàng đợi
            </button>
            <div className="lx-row lx-row--center">
              <span className="lx-badge lx-badge--info">
                Frame #{activeGrant.frame.id}
              </span>
              <span className="lx-mono lx-subtle">
                Lease #{activeGrant.lease.id}
              </span>
            </div>
          </div>
          <ReviewWorkspace
            frameId={activeGrant.frame.id}
            initialLease={activeGrant.lease}
            grant={activeGrant}
            runId={effectiveRunId}
            datasetId={datasetId}
            onBackToQueue={() => setIsWorkspaceOpen(false)}
            onLeaseUpdated={(updatedLease) => {
              if (
                contextRef.current.datasetId !== datasetId ||
                contextRef.current.activeRunId !== effectiveRunId ||
                contextRef.current.currentUserId !== currentUserId
              ) {
                return;
              }
              setActiveGrant((prev) => {
                if (
                  !prev ||
                  prev.frame.id !== activeGrant.frame.id ||
                  prev.lease.id !== updatedLease.id
                ) {
                  return prev;
                }
                return { ...prev, lease: updatedLease };
              });
            }}
            onLeaseConflict={() => {
              if (
                contextRef.current.datasetId !== datasetId ||
                contextRef.current.activeRunId !== effectiveRunId ||
                contextRef.current.currentUserId !== currentUserId
              ) {
                return;
              }
              setIsLeaseConflict(true);
            }}
            onFrameCompleted={() => {
              if (
                contextRef.current.datasetId !== datasetId ||
                contextRef.current.activeRunId !== effectiveRunId ||
                contextRef.current.currentUserId !== currentUserId
              ) {
                return;
              }
              setIsWorkspaceOpen(false);
              setActiveGrant(null);
              queryClient.invalidateQueries({
                queryKey: ['review', 'ranking', datasetId, effectiveRunId],
              });
            }}
          />
        </section>
      ) : (
        !datasetId || !effectiveRunId ? (
          <ReviewQueueSample />
        ) : runQuery.isSuccess && (
          <section className="lx-card" aria-label="Hàng đợi kiểm duyệt">
          {/* Queue Selection Tabs */}
          <div className="lx-tabs" role="tablist" aria-label="Các hàng đợi kiểm tra">
            <button
              type="button"
              role="tab"
              className={`lx-tab ${activeQueue === 'risk' ? 'is-active' : ''}`}
              onClick={() => handleQueueChange('risk')}
              aria-selected={activeQueue === 'risk'}
            >
              <span>Hàng đợi rủi ro (Risk Queue)</span>
              {activeQueue === 'risk' && rankingQuery.data && (
                <span className="lx-count">Trang hiện tại</span>
              )}
            </button>
            <button
              type="button"
              role="tab"
              className={`lx-tab ${activeQueue === 'random' ? 'is-active' : ''}`}
              onClick={() => handleQueueChange('random')}
              aria-selected={activeQueue === 'random'}
            >
              <span>Kiểm định ngẫu nhiên (Random Audit)</span>
              {activeQueue === 'random' && rankingQuery.data && (
                <span className="lx-count">Trang hiện tại</span>
              )}
            </button>
          </div>

          {/* Filters Bar & Claim Action */}
          <div className="lx-review-filters lx-review-filters--4">
            {/* TODO(backend): tìm kiếm theo tên/mã ảnh và mức ưu tiên chưa có ở GET /api/runs/{id}/frames/ */}
            <label className="lx-field">Tìm kiếm
              <span className="lx-search">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></svg>
                <input type="search" disabled placeholder="Tìm ảnh hoặc mã công việc" aria-label="Tìm ảnh hoặc mã công việc" />
              </span>
            </label>
            <label className="lx-field">Nhóm lỗi
              <select
                id="filter-family"
                aria-label="Lọc theo nhóm lỗi (family)"
                className="lx-select"
                value={filters.family ?? ''}
                onChange={(e) => handleFilterChange({ family: (e.target.value as IssueFamily) || undefined })}
              >
                <option value="">-- Nhóm lỗi (Family) --</option>
                <option value="E1">E1 (Thiếu nhãn)</option>
                <option value="E2">E2 (Sai lớp)</option>
                <option value="E3">E3 (Trùng nhãn)</option>
                <option value="structural">Cấu trúc (structural)</option>
              </select>
            </label>
            <label className="lx-field">Nguồn
              <select
                id="filter-origin"
                aria-label="Lọc theo nguồn gốc (origin)"
                className="lx-select"
                value={filters.origin ?? ''}
                onChange={(e) => handleFilterChange({ origin: (e.target.value as IssueOrigin) || undefined })}
              >
                <option value="">-- Nguồn gốc (Origin) --</option>
                <option value="engine">Máy (engine)</option>
                <option value="reviewer">Reviewer</option>
              </select>
            </label>
            <label className="lx-field">Trạng thái
              <select
                id="filter-review-state"
                aria-label="Lọc theo trạng thái review"
                className="lx-select"
                value={filters.review_state ?? ''}
                onChange={(e) => handleFilterChange({ review_state: (e.target.value as FrameReviewState) || undefined })}
              >
                <option value="">-- Trạng thái review --</option>
                <option value="unreviewed">Chưa review</option>
                <option value="in_review">Đang review</option>
                <option value="incomplete">Đang dở</option>
                <option value="reviewed">Đã review</option>
                <option value="awaiting_followup">Chờ theo dõi</option>
                <option value="completed">Hoàn tất</option>
              </select>
            </label>
          </div>
          <div className="lx-card__head">
            <strong>Ảnh cần kiểm tra</strong>
            <div className="lx-actions">
              {(filters.family || filters.origin || filters.review_state) && (
                <button type="button" className="lx-btn lx-btn--ghost lx-btn--sm" onClick={handleResetFilters}>
                  Xóa bộ lọc
                </button>
              )}
              <button
                type="button"
                className="lx-btn lx-btn--primary"
                onClick={() => claimMutation.mutate()}
                disabled={claimMutation.isPending || !runQuery.isSuccess}
                aria-label="Nhận frame kế tiếp từ hàng đợi"
              >
                {claimMutation.isPending
                  ? 'Đang nhận frame...'
                  : `Bắt đầu kiểm tra (${activeQueue === 'risk' ? 'Risk' : 'Random'})`}
              </button>
            </div>
          </div>

          {/* Ranking Frames Table */}
          {rankingQuery.isLoading && (
            <div className="lx-card__body lx-muted" role="status">
              Đang tải danh sách frame trong hàng đợi {activeQueue}...
            </div>
          )}

          {rankingQuery.isError && (
            <div className="lx-card__body">
              <div role="alert" className="lx-callout">
                <div className="lx-callout__text">
                  Lỗi tải danh sách frame: {errorMessage(rankingQuery.error)}
                </div>
              </div>
              <button
                type="button"
                className="lx-btn lx-btn--sm lx-mt-1"
                onClick={() => rankingQuery.refetch()}
              >
                Thử lại
              </button>
            </div>
          )}

          {rankingQuery.isSuccess && (
            <>
              {rankingQuery.data.results.length === 0 ? (
                <div className="lx-review-empty">
                  <p>
                    Không có frame nào khớp với điều kiện lọc trong hàng đợi {activeQueue}.
                  </p>
                  {(filters.family || filters.origin || filters.review_state) && (
                    <div>
                      <button
                        type="button"
                        className="lx-btn lx-btn--sm"
                        onClick={handleResetFilters}
                      >
                        Đặt lại bộ lọc
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="lx-review-queue" role="list" aria-label="Danh sách frame xếp hạng">
                  {rankingQuery.data.results.map((frame: RankedFrame) => (
                    <article
                      key={`${frame.frame_key.cvat_task_id}-${frame.frame_key.frame_number}`}
                      className="lx-review-row"
                      role="listitem"
                    >
                      <span className="lx-review-rank"><strong>#{frame.rank}</strong></span>
                      {/* TODO(backend): ảnh thu nhỏ của frame chưa có ở API ranking */}
                      <span className="lx-review-thumb lx-review-thumb--empty" aria-hidden="true"><Icon name="image" className="lx-review-icon" /></span>
                      <div className="lx-review-info">
                        <div className="lx-review-title">
                          <h2 className="lx-h2">
                            Task #{frame.frame_key.cvat_task_id} • Frame #{frame.frame_key.frame_number}
                          </h2>
                          {frame.issue_counts && Object.keys(frame.issue_counts).length > 0 ? (
                            Object.entries(frame.issue_counts).map(([fam, count]) => (
                              <span key={fam} className="lx-review-badge">
                                <Icon name="alert" className="lx-review-icon" />{fam}: {count}
                              </span>
                            ))
                          ) : (
                            <span className="lx-subtle">0 issue</span>
                          )}
                          <span className={`lx-review-badge${frame.source === 'risk' ? ' lx-review-badge--danger' : ''}`}>
                            {frame.source}
                          </span>
                          {frame.missing_evidence && (
                            <span className="lx-badge lx-badge--warning">Thiếu bằng chứng</span>
                          )}
                        </div>
                        <div className="lx-mono lx-subtle">Frame ID: {frame.frame_id}</div>
                        <div className="lx-review-meta">
                          <span>{frame.score.toFixed(3)}</span>
                          <span className="lx-subtle">Nền: {frame.baseline_score.toFixed(3)}</span>
                          <span className="lx-badge lx-badge--neutral">{frame.review_state}</span>
                          {frame.lease_holder_user_id ? (
                            <span className="lx-mono">User #{frame.lease_holder_user_id}</span>
                          ) : (
                            <span className="lx-subtle">Chưa có</span>
                          )}
                        </div>
                        {frame.explanation && (
                          <details>
                            <summary className="lx-review-explain-toggle">Chi tiết điểm</summary>
                            <pre className="lx-mono lx-review-explain">{JSON.stringify(frame.explanation, null, 2)}</pre>
                          </details>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}

              {/* Server Cursor Pager */}
              <div className="lx-card__foot">
                <span className="lx-hint">
                  Hàng đợi {activeQueue === 'risk' ? 'Rủi ro' : 'Kiểm định ngẫu nhiên'} • Sắp xếp
                  theo rank tăng dần
                </span>
                <div className="lx-pager">
                  <button
                    type="button"
                    className="lx-btn lx-btn--sm"
                    disabled={!prevCursor || rankingQuery.isFetching}
                    onClick={() => setCursor(prevCursor)}
                    aria-label="Trang trước"
                  >
                    Trang trước
                  </button>
                  <button
                    type="button"
                    className="lx-btn lx-btn--sm"
                    disabled={!nextCursor || rankingQuery.isFetching}
                    onClick={() => setCursor(nextCursor)}
                    aria-label="Trang tiếp"
                  >
                    Trang tiếp
                  </button>
                </div>
              </div>
            </>
          )}
        </section>
      ))}
    </div>
  );
}
