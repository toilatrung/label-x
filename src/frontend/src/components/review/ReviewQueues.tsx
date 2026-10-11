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
import { ApiRequestError, errorMessage } from '@/lib/api/errors';

export function ReviewQueues() {
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
  } else if (runParam !== prevRunParam) {
    setPrevRunParam(runParam);
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
  const contextRef = useRef({ datasetId, activeRunId: effectiveRunId });
  useEffect(() => {
    contextRef.current = { datasetId, activeRunId: effectiveRunId };
  }, [datasetId, effectiveRunId]);

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
      };
    },
    mutationFn: async () => {
      return claimNextFrame(activeQueue, effectiveRunId!);
    },
    onSuccess: (result, _variables, context) => {
      // Discard if context switched while mutation was pending
      if (
        contextRef.current.activeRunId !== context?.targetRunId ||
        contextRef.current.datasetId !== context?.targetDatasetId
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
        contextRef.current.datasetId !== context?.targetDatasetId
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
      };
    },
    mutationFn: async (leaseId: number) => {
      return renewLease(leaseId);
    },
    onSuccess: (lease, _variables, context) => {
      // Discard if context switched while mutation was pending
      if (
        contextRef.current.activeRunId !== context?.targetRunId ||
        contextRef.current.datasetId !== context?.targetDatasetId
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
        contextRef.current.datasetId !== context?.targetDatasetId
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
    setIsLeaseConflict(false);
    setActiveGrant(null);
    setClaimError(null);
    setRenewMessage(null);
    setClaimStatus204(false);
    queryClient.invalidateQueries({ queryKey: ['review', 'run', datasetId, effectiveRunId] });
    queryClient.invalidateQueries({ queryKey: ['review', 'ranking', datasetId, effectiveRunId] });
  };

  const nextCursor = cursorFrom(rankingQuery.data?.next);
  const prevCursor = cursorFrom(rankingQuery.data?.previous);

  return (
    <div className="lx-stack">
      {/* Context Bar / Controls */}
      <div className="lx-card lx-card__body lx-stack">
        <div className="lx-cols" style={{ alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 250px' }}>
            <ReviewDatasetPicker
              onChange={() => {
                setCursor(null);
              }}
            />
          </div>

          <form
            onSubmit={handleRunSubmit}
            style={{ flex: '2 1 300px', display: 'flex', gap: '8px', alignItems: 'flex-end' }}
          >
            <div className="lx-field" style={{ flex: 1 }}>
              <label htmlFor="review-run-id" className="lx-label">
                Mã QC Run (Run ID)
              </label>
              <input
                id="review-run-id"
                className="lx-input"
                type="number"
                min={1}
                placeholder="Nhập ID Run (vd: 12)"
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
              Vui lòng chọn bộ dữ liệu (dataset) để xem hàng đợi kiểm tra.
            </div>
          </div>
        )}

        {datasetId && !effectiveRunId && (
          <div role="status" className="lx-callout lx-callout--info">
            <div className="lx-callout__text">
              Vui lòng nhập Mã QC Run để tải hàng đợi kiểm tra.
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
          className="lx-card"
          style={{ borderColor: isLeaseConflict ? 'var(--danger)' : 'var(--primary)' }}
          aria-label="Khung ngữ cảnh kiểm tra hiện tại"
        >
          <div
            className="lx-card__head"
            style={{
              background: isLeaseConflict ? 'var(--danger-soft)' : 'var(--surface-selected)',
            }}
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

            <div className="lx-row" style={{ justifyContent: 'space-between' }}>
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
                  disabled={renewMutation.isPending || isLeaseConflict}
                >
                  {renewMutation.isPending ? 'Đang gia hạn...' : 'Gia hạn lease (Renew)'}
                </button>
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
                Ngữ cảnh lease đã sẵn sàng cho không gian làm việc T-037.
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
              <span className="lx-badge lx-badge--danger" style={{ marginLeft: '8px' }}>
                {claimError.code}
              </span>
            )}
            {claimError.code === 'LEASE_CONFLICT' && (
              <div style={{ marginTop: '6px' }}>
                <p style={{ margin: '0 0 6px', fontSize: '13px' }}>
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

      {/* Review Queues Panel: Only shown when runQuery succeeds */}
      {datasetId && effectiveRunId && runQuery.isSuccess && (
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
          <div className="lx-toolbar" style={{ flexWrap: 'wrap', justifyContent: 'space-between' }}>
            <div className="lx-row" style={{ flexWrap: 'wrap' }}>
              <div className="lx-field">
                <select
                  id="filter-family"
                  aria-label="Lọc theo nhóm lỗi (family)"
                  className="lx-select lx-select--inline"
                  value={filters.family ?? ''}
                  onChange={(e) =>
                    handleFilterChange({
                      family: (e.target.value as IssueFamily) || undefined,
                    })
                  }
                >
                  <option value="">-- Nhóm lỗi (Family) --</option>
                  <option value="E1">E1 (Thiếu nhãn)</option>
                  <option value="E2">E2 (Sai lớp)</option>
                  <option value="E3">E3 (Trùng nhãn)</option>
                  <option value="structural">Cấu trúc (structural)</option>
                </select>
              </div>

              <div className="lx-field">
                <select
                  id="filter-origin"
                  aria-label="Lọc theo nguồn gốc (origin)"
                  className="lx-select lx-select--inline"
                  value={filters.origin ?? ''}
                  onChange={(e) =>
                    handleFilterChange({
                      origin: (e.target.value as IssueOrigin) || undefined,
                    })
                  }
                >
                  <option value="">-- Nguồn gốc (Origin) --</option>
                  <option value="engine">Máy (engine)</option>
                  <option value="reviewer">Reviewer</option>
                </select>
              </div>

              <div className="lx-field">
                <select
                  id="filter-review-state"
                  aria-label="Lọc theo trạng thái review (review_state)"
                  className="lx-select lx-select--inline"
                  value={filters.review_state ?? ''}
                  onChange={(e) =>
                    handleFilterChange({
                      review_state: (e.target.value as FrameReviewState) || undefined,
                    })
                  }
                >
                  <option value="">-- Trạng thái (Review State) --</option>
                  <option value="unreviewed">Chưa review (unreviewed)</option>
                  <option value="in_review">Đang review (in_review)</option>
                  <option value="incomplete">Đang dở (incomplete)</option>
                  <option value="reviewed">Đã review (reviewed)</option>
                  <option value="awaiting_followup">Chờ theo dõi (awaiting_followup)</option>
                  <option value="completed">Hoàn tất (completed)</option>
                </select>
              </div>

              {(filters.family || filters.origin || filters.review_state) && (
                <button
                  type="button"
                  className="lx-btn lx-btn--ghost lx-btn--sm"
                  onClick={handleResetFilters}
                >
                  Xóa bộ lọc
                </button>
              )}
            </div>

            {/* Action: Claim next frame */}
            <div>
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
                className="lx-btn lx-btn--sm"
                style={{ marginTop: '8px' }}
                onClick={() => rankingQuery.refetch()}
              >
                Thử lại
              </button>
            </div>
          )}

          {rankingQuery.isSuccess && (
            <>
              {rankingQuery.data.results.length === 0 ? (
                <div className="lx-card__body lx-stack" style={{ textAlign: 'center', padding: '32px' }}>
                  <p className="lx-muted">
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
                <div className="lx-scroll">
                  <table className="lx-table" aria-label="Bảng danh sách frame xếp hạng">
                    <thead>
                      <tr>
                        <th style={{ width: '60px' }}>Rank</th>
                        <th>Frame Key</th>
                        <th>Điểm s(f) / h(f)</th>
                        <th>Nhóm lỗi (Issue counts)</th>
                        <th>Nguồn</th>
                        <th>Trạng thái</th>
                        <th>Người giữ (Holder)</th>
                        <th>Giải thích thứ hạng</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rankingQuery.data.results.map((frame: RankedFrame) => (
                        <tr
                          key={`${frame.frame_key.cvat_task_id}-${frame.frame_key.frame_number}`}
                        >
                          <td className="lx-num">
                            <strong>#{frame.rank}</strong>
                          </td>
                          <td>
                            <div className="lx-cell__main">
                              Task #{frame.frame_key.cvat_task_id} • Frame #
                              {frame.frame_key.frame_number}
                            </div>
                            <div className="lx-cell__sub lx-mono">
                              Frame ID: {frame.frame_id}
                              {frame.missing_evidence && (
                                <span
                                  className="lx-badge lx-badge--warning"
                                  style={{ marginLeft: '6px' }}
                                >
                                  Thiếu bằng chứng
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="lx-num">
                            <div>{frame.score.toFixed(3)}</div>
                            <div className="lx-cell__sub">
                              Nền: {frame.baseline_score.toFixed(3)}
                            </div>
                          </td>
                          <td>
                            <div className="lx-row">
                              {frame.issue_counts &&
                              Object.keys(frame.issue_counts).length > 0 ? (
                                Object.entries(frame.issue_counts).map(([fam, count]) => (
                                  <span key={fam} className="lx-tag">
                                    {fam}: {count}
                                  </span>
                                ))
                              ) : (
                                <span className="lx-subtle">0 issue</span>
                              )}
                            </div>
                          </td>
                          <td>
                            <span
                              className={`lx-badge ${
                                frame.source === 'risk'
                                  ? 'lx-badge--danger'
                                  : 'lx-badge--info'
                              }`}
                            >
                              {frame.source}
                            </span>
                          </td>
                          <td>
                            <span className="lx-badge lx-badge--neutral">
                              {frame.review_state}
                            </span>
                          </td>
                          <td>
                            {frame.lease_holder_user_id ? (
                              <span className="lx-mono">
                                User #{frame.lease_holder_user_id}
                              </span>
                            ) : (
                              <span className="lx-subtle">Chưa có</span>
                            )}
                          </td>
                          <td>
                            {frame.explanation && (
                              <details>
                                <summary style={{ cursor: 'pointer', fontSize: '12px' }}>
                                  Chi tiết điểm
                                </summary>
                                <pre
                                  className="lx-mono"
                                  style={{
                                    fontSize: '11px',
                                    margin: '4px 0 0',
                                    padding: '4px',
                                    background: 'var(--surface-sunken)',
                                    borderRadius: '4px',
                                    maxWidth: '240px',
                                    overflowX: 'auto',
                                  }}
                                >
                                  {JSON.stringify(frame.explanation, null, 2)}
                                </pre>
                              </details>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
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
      )}
    </div>
  );
}
