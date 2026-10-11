'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { apiClient } from '@/lib/api/client';
import { readErrorDetail, ApiRequestError } from '@/lib/api/errors';
import type { components } from '@/lib/api/contract';
import { useAuth } from '@/lib/auth/auth-context';
import { useLeaseManager } from './useLeaseManager';
import { useEffortCollector, effortCollectorStatus } from './useEffortCollector';
import { ReviewCanvas } from './ReviewCanvas';
import { ReviewEvidenceTable } from './ReviewEvidenceTable';
import { ReviewGuidelineLookup } from './ReviewGuidelineLookup';
import { ReviewDecisionForm } from './ReviewDecisionForm';
import { ReviewManualIssueModal } from './ReviewManualIssueModal';
import { DecisionCaseLookup } from '@/components/escalations/DecisionCaseLookup';

type FrameIssues = components['schemas']['FrameIssues'];
type Issue = components['schemas']['Issue'];
type Lease = components['schemas']['Lease'];
type LeaseGrant = components['schemas']['LeaseGrant'];
type BBox = components['schemas']['BBox'];
type ObjectRef = components['schemas']['ObjectRef'];

export interface ReviewWorkspaceProps {
  frameId: number;
  initialLease: Lease | null;
  grant?: LeaseGrant | null;
  snapshotRevision?: string | null;
  anchorPolicyVersion?: string | null;
  runId?: number | null;
  datasetId?: number | null;
  onFrameCompleted?: () => void;
  onBackToQueue?: () => void;
  onLeaseUpdated?: (lease: Lease) => void;
  onLeaseConflict?: () => void;
}

/**
 * Resolves verified anchor policy according to T-035 inspection:
 * - Only 'anchor-v1' is supported.
 * - If context prop provided, verifies against 'anchor-v1' and checks against existing issues.
 * - If not provided, inspects existing issues: consistent 'anchor-v1' allows manual issues.
 * - Zero-issue frame or conflicting policy stays unavailable without hardcoded fallback.
 */
export function resolveAnchorPolicy(
  propPolicy: string | null | undefined,
  issues: Issue[]
): { policy: string | null; error?: string } {
  const SUPPORTED_POLICY = 'anchor-v1';

  if (propPolicy) {
    const trimmed = propPolicy.trim();
    if (trimmed !== SUPPORTED_POLICY) {
      return {
        policy: null,
        error: `Chính sách neo "${trimmed}" không được hỗ trợ (chỉ hỗ trợ ${SUPPORTED_POLICY}).`,
      };
    }
    if (issues.length > 0) {
      const conflicting = issues.some((i) => i.anchor.policy_version !== trimmed);
      if (conflicting) {
        return {
          policy: null,
          error: 'Xung đột chính sách neo: Context policy khác với policy của các issue hiện tại.',
        };
      }
    }
    return { policy: trimmed };
  }

  // No prop policy provided: inspect existing issues
  if (!issues || issues.length === 0) {
    return {
      policy: null,
      error: 'Tạo manual issue tạm khóa: Thiếu anchor policy_version đã duyệt từ T-035 (zero-issue gap).',
    };
  }

  const firstPolicy = issues[0].anchor.policy_version;
  if (!firstPolicy || firstPolicy !== SUPPORTED_POLICY) {
    return {
      policy: null,
      error: `Tạo manual issue tạm khóa: Thiếu anchor policy_version đã duyệt từ T-035 (server: ${firstPolicy || 'none'}).`,
    };
  }

  const allMatch = issues.every((i) => i.anchor.policy_version === firstPolicy);
  if (!allMatch) {
    return {
      policy: null,
      error: 'Tạo manual issue tạm khóa: Thiếu anchor policy_version đã duyệt từ T-035 (xung đột policy).',
    };
  }

  return { policy: firstPolicy };
}

export function ReviewWorkspace({
  frameId,
  initialLease,
  grant,
  snapshotRevision,
  anchorPolicyVersion,
  runId,
  datasetId,
  onFrameCompleted,
  onBackToQueue,
  onLeaseUpdated,
  onLeaseConflict,
}: ReviewWorkspaceProps) {
  const { session, datasetId: authDatasetId } = useAuth();
  const effectiveDatasetId = datasetId ?? authDatasetId ?? null;
  const currentUserId = session?.user?.id ?? null;
  const userRoles = session?.roles ?? [];
  const isSuperAdmin = userRoles.some((r) => r.role === 'super_admin');
  const isEligibleRoleForSnapshot = userRoles.some((r) =>
    ['qa_lead', 'qc_admin', 'super_admin'].includes(r.role)
  );

  const [data, setData] = useState<FrameIssues | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [forbiddenCode, setForbiddenCode] = useState<string | null>(null);

  // Active workspace state
  const [selectedIssueId, setSelectedIssueId] = useState<number | null>(null);
  const [reviewMode, setReviewMode] = useState<'issue' | 'frame'>('issue');
  const [showAnnotations, setShowAnnotations] = useState<boolean>(true);
  const [showPredictions, setShowPredictions] = useState<boolean>(true);

  // Zoom & pan
  const [zoom, setZoom] = useState<number>(1);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Manual issue creation state
  const [manualModalOpen, setManualModalOpen] = useState<boolean>(false);
  const [selectedObjectForManual, setSelectedObjectForManual] = useState<ObjectRef | null>(null);
  const [drawnRegionForManual, setDrawnRegionForManual] = useState<BBox | null>(null);

  // Complete frame state
  const [isCompleting, setIsCompleting] = useState<boolean>(false);
  const [completeError, setCompleteError] = useState<string | null>(null);
  const [undecidedIssueIds, setUndecidedIssueIds] = useState<number[]>([]);
  const [isCompleted, setIsCompleted] = useState<boolean>(false);

  // Dynamic lease conflict invalidation
  const [forcedLeaseInvalidated, setForcedLeaseInvalidated] = useState<boolean>(false);

  // Lease management
  const { lease, isExpired, isHolderMismatch, leaseError, remainingSeconds, renewLease } =
    useLeaseManager({
      frameId,
      initialLease,
      currentUserId,
      enabled: !isCompleted && !forcedLeaseInvalidated && Boolean(initialLease),
      onConflict: () => {
        handleLeaseConflict();
      },
      onLeaseUpdated,
    });

  const isReadOnly = !initialLease;
  const isMutationBlocked = isReadOnly || isExpired || forcedLeaseInvalidated || isCompleted;

  // Real T-036 Effort Collector lifecycle integration
  // Precedence: latest managed renewed lease takes precedence over stale grant prop
  const effectiveFrame = data?.frame ?? grant?.frame ?? null;
  const effectiveLease = lease ?? grant?.lease ?? null;
  const effectiveGrant: LeaseGrant | null =
    effectiveFrame && effectiveLease && effectiveLease.frame_id === effectiveFrame.id
      ? {
          frame: effectiveFrame,
          lease: effectiveLease,
          resumed: grant?.resumed ?? false,
        }
      : null;

  const {
    setActivity,
    decisionSaved,
    completeAfter,
    stopOnLeaseConflict: stopEffortOnLeaseConflict,
    loseLease: loseEffortLease,
  } = useEffortCollector({
    grant: effectiveGrant,
    currentUserId,
    enabled: !isMutationBlocked,
  });

  const handleLeaseConflict = useCallback(
    (serverError?: unknown) => {
      setForcedLeaseInvalidated(true);
      setManualModalOpen(false);
      if (serverError) {
        void stopEffortOnLeaseConflict(serverError);
      } else {
        void loseEffortLease();
      }
      onLeaseConflict?.();
    },
    [loseEffortLease, onLeaseConflict, stopEffortOnLeaseConflict]
  );

  // Track review activity (view_frame vs review_issue)
  useEffect(() => {
    if (reviewMode === 'frame' || selectedIssueId === null) {
      setActivity('view_frame');
    } else {
      setActivity('review_issue');
    }
  }, [reviewMode, selectedIssueId, setActivity]);

  // Snapshot revision resolution
  const [resolvedRevision, setResolvedRevision] = useState<string | null>(
    snapshotRevision?.trim() || null
  );
  const [revisionLoading, setRevisionLoading] = useState<boolean>(false);
  const [revisionError, setRevisionError] = useState<string | null>(null);
  const [revisionUnavailableReason, setRevisionUnavailableReason] = useState<string | null>(null);

  const revReqSeq = useRef<number>(0);
  const revAbortCtrlRef = useRef<AbortController | null>(null);
  const reqSeq = useRef<number>(0);
  const abortCtrlRef = useRef<AbortController | null>(null);

  // Reset transient frame state when frameId or authenticated user context changes
  const [prevFrameId, setPrevFrameId] = useState(frameId);
  const [prevUserId, setPrevUserId] = useState(currentUserId);
  if (frameId !== prevFrameId || (prevUserId !== null && currentUserId !== prevUserId)) {
    setPrevFrameId(frameId);
    setPrevUserId(currentUserId);
    setData(null);
    setLoading(currentUserId !== null);
    setErrorMsg(null);
    setForbiddenCode(null);
    setSelectedIssueId(null);
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setIsCompleted(false);
    setForcedLeaseInvalidated(false);
    setCompleteError(null);
    setUndecidedIssueIds([]);
    setManualModalOpen(false);
    setResolvedRevision(snapshotRevision?.trim() || null);
    setRevisionLoading(false);
    setRevisionError(null);
    setRevisionUnavailableReason(null);
  } else if (prevUserId === null && currentUserId !== null) {
    setPrevUserId(currentUserId);
    setLoading(true);
  }

  const contextRef = useRef({
    frameId,
    leaseId: initialLease?.id ?? null,
    runId: runId ?? null,
    datasetId: effectiveDatasetId,
    currentUserId,
    isMounted: true,
  });
  const generationRef = useRef<number>(0);

  const isMountedRef = useRef<boolean>(true);
  useEffect(() => {
    isMountedRef.current = true;
    contextRef.current.isMounted = true;
    return () => {
      isMountedRef.current = false;
      contextRef.current.isMounted = false;
      generationRef.current += 1;
      if (abortCtrlRef.current) abortCtrlRef.current.abort();
      if (revAbortCtrlRef.current) revAbortCtrlRef.current.abort();
    };
  }, []);

  useEffect(() => {
    const prev = contextRef.current;
    const isSameLeaseId = prev.leaseId === (initialLease?.id ?? null);
    const isUserSwitch = prev.currentUserId !== null && currentUserId !== prev.currentUserId;
    const isMeaningfulChange =
      prev.frameId !== frameId ||
      isUserSwitch ||
      prev.runId !== (runId ?? null) ||
      prev.datasetId !== effectiveDatasetId ||
      !isSameLeaseId;

    if (isMeaningfulChange) {
      generationRef.current += 1;
      if (abortCtrlRef.current) abortCtrlRef.current.abort();
      if (revAbortCtrlRef.current) revAbortCtrlRef.current.abort();
      reqSeq.current += 1;
      revReqSeq.current += 1;

      contextRef.current = {
        frameId,
        leaseId: initialLease?.id ?? null,
        runId: runId ?? null,
        datasetId: effectiveDatasetId,
        currentUserId,
        isMounted: true,
      };
    } else {
      contextRef.current = {
        ...contextRef.current,
        leaseId: initialLease?.id ?? null,
        currentUserId,
      };
    }
  }, [frameId, currentUserId, runId, effectiveDatasetId, initialLease?.id]);

  // Load FrameIssues asynchronously from API with cancellation and sequence guard
  const loadFrame = useCallback((targetFrameId: number) => {
    if (abortCtrlRef.current) {
      abortCtrlRef.current.abort();
    }
    const abortCtrl = new AbortController();
    abortCtrlRef.current = abortCtrl;
    const currentReqId = ++reqSeq.current;
    const opGen = generationRef.current;
    const reqUserId = contextRef.current.currentUserId;

    apiClient
      .GET('/api/frames/{id}/issues/', {
        params: { path: { id: targetFrameId } },
        signal: abortCtrl.signal,
      })
      .then(({ data: frameData, error, response }) => {
        // Discard stale out-of-order response or changed context
        if (
          !contextRef.current.isMounted ||
          opGen !== generationRef.current ||
          currentReqId !== reqSeq.current ||
          contextRef.current.frameId !== targetFrameId ||
          contextRef.current.currentUserId !== reqUserId
        ) {
          return;
        }

        if (response.status === 403) {
          const detail = readErrorDetail(error);
          const code = detail?.code || 'FORBIDDEN';
          setForbiddenCode(code);
          if (code === 'SELF_REVIEW_FORBIDDEN') {
            setErrorMsg('Bạn không được review annotation do chính mình thực hiện (Anti-self-review FR-REV-03).');
          } else if (code === 'IDENTITY_MAPPING_MISSING') {
            setErrorMsg('Tài khoản của bạn chưa được liên kết định danh CVAT (IDENTITY_MAPPING_MISSING).');
          } else if (code === 'OUT_OF_SCOPE') {
            setErrorMsg('Dataset nằm ngoài phạm vi được cấp quyền của bạn (OUT_OF_SCOPE).');
          } else {
            setErrorMsg(detail?.message || 'Bạn không có quyền kiểm tra khung hình này (403 Forbidden).');
          }
          setLoading(false);
          return;
        }

        if (error || !frameData) {
          const detail = readErrorDetail(error);
          setErrorMsg(detail?.message || 'Không thể tải thông tin khung hình và danh sách issue từ máy chủ.');
          setLoading(false);
          return;
        }

        // Validate frame response id and run binding against queue grant
        if (frameData.frame.id !== targetFrameId) {
          setErrorMsg(`Dữ liệu khung hình không khớp: API trả về frame #${frameData.frame.id} thay vì #${targetFrameId}.`);
          setLoading(false);
          return;
        }
        if (runId != null && frameData.frame.run_id !== runId) {
          setErrorMsg(`Dữ liệu khung hình không thuộc run đang chọn: Run #${frameData.frame.run_id} khác với Run #${runId}.`);
          setLoading(false);
          return;
        }

        setData(frameData);
        if (frameData.issues && frameData.issues.length > 0) {
          setSelectedIssueId(frameData.issues[0].id);
        }
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (
          !contextRef.current.isMounted ||
          abortCtrl.signal.aborted ||
          opGen !== generationRef.current ||
          currentReqId !== reqSeq.current ||
          contextRef.current.frameId !== targetFrameId ||
          contextRef.current.currentUserId !== reqUserId
        ) {
          return;
        }
        setErrorMsg(`Lỗi mạng khi tải dữ liệu khung hình: ${err instanceof Error ? err.message : 'Lỗi kết nối'}`);
        setLoading(false);
      });
  }, [runId]);

  useEffect(() => {
    if (currentUserId === null) {
      return;
    }
    loadFrame(frameId);
    return () => {
      if (abortCtrlRef.current) {
        abortCtrlRef.current.abort();
      }
    };
  }, [frameId, currentUserId, loadFrame]);

  // Snapshot revision resolution logic for eligible roles
  const boundRunId = runId ?? data?.frame.run_id ?? null;
  const directRevision = snapshotRevision?.trim() || null;
  const revContextKey = `${boundRunId}:${isEligibleRoleForSnapshot}:${directRevision || ''}:${effectiveDatasetId}`;
  const [prevRevContextKey, setPrevRevContextKey] = useState(revContextKey);

  if (revContextKey !== prevRevContextKey) {
    setPrevRevContextKey(revContextKey);
    if (directRevision) {
      setResolvedRevision(directRevision);
      setRevisionLoading(false);
      setRevisionError(null);
      setRevisionUnavailableReason(null);
    } else if (!isEligibleRoleForSnapshot) {
      setResolvedRevision(null);
      setRevisionLoading(false);
      setRevisionError(null);
      setRevisionUnavailableReason(
        'Chưa có snapshot revision đã xác thực từ context: Plain Reviewer chưa có nguồn snapshot revision được cấp quyền từ API (GET /api/snapshots/{id}/ chỉ cho phép qa_lead/qc_admin/super_admin). Quyết định review tạm khóa.'
      );
    } else if (boundRunId) {
      setResolvedRevision(null);
      setRevisionLoading(true);
      setRevisionError(null);
      setRevisionUnavailableReason(null);
    } else {
      setResolvedRevision(null);
      setRevisionLoading(false);
      setRevisionError(null);
      setRevisionUnavailableReason(null);
    }
  }

  useEffect(() => {
    if (revAbortCtrlRef.current) {
      revAbortCtrlRef.current.abort();
    }

    if (directRevision || !isEligibleRoleForSnapshot || !boundRunId) {
      return;
    }

    const abortCtrl = new AbortController();
    revAbortCtrlRef.current = abortCtrl;
    const currentSeq = ++revReqSeq.current;
    const opGen = generationRef.current;

    (async () => {
      try {
        const { data: runData, error: runErr } = await apiClient.GET('/api/runs/{id}/', {
          params: { path: { id: boundRunId } },
          signal: abortCtrl.signal,
        });

        if (
          !contextRef.current.isMounted ||
          opGen !== generationRef.current ||
          currentSeq !== revReqSeq.current
        ) {
          return;
        }

        if (runErr || !runData) {
          setRevisionError('Không thể tải thông tin Run để lấy snapshot_id.');
          setRevisionLoading(false);
          return;
        }

        if (runData.id !== boundRunId) {
          setRevisionError(`Dữ liệu Run trả về id #${runData.id} không khớp với Run #${boundRunId}.`);
          setRevisionLoading(false);
          return;
        }

        const snapshotId = runData.snapshot_id;
        if (!snapshotId) {
          setRevisionError(`Run #${boundRunId} không có snapshot_id.`);
          setRevisionLoading(false);
          return;
        }

        const { data: snapData, error: snapErr } = await apiClient.GET('/api/snapshots/{id}/', {
          params: { path: { id: snapshotId } },
          signal: abortCtrl.signal,
        });

        if (
          !contextRef.current.isMounted ||
          opGen !== generationRef.current ||
          currentSeq !== revReqSeq.current
        ) {
          return;
        }

        if (snapErr || !snapData) {
          setRevisionError(`Không thể tải thông tin snapshot #${snapshotId}.`);
          setRevisionLoading(false);
          return;
        }

        if (snapData.id !== snapshotId) {
          setRevisionError(`Mã snapshot không khớp: #${snapData.id} thay vì #${snapshotId}.`);
          setRevisionLoading(false);
          return;
        }

        if (effectiveDatasetId !== null && snapData.dataset_id !== effectiveDatasetId) {
          setRevisionError(`Snapshot #${snapshotId} thuộc dataset #${snapData.dataset_id}, không khớp với dataset #${effectiveDatasetId}.`);
          setRevisionLoading(false);
          return;
        }

        if (snapData.status !== 'locked') {
          setRevisionError(`Snapshot #${snapshotId} chưa ở trạng thái locked (trạng thái: ${snapData.status}).`);
          setRevisionLoading(false);
          return;
        }

        const revHash = snapData.revision_hash?.trim();
        if (!revHash) {
          setRevisionError(`Snapshot #${snapshotId} đã khóa nhưng thiếu revision_hash.`);
          setRevisionLoading(false);
          return;
        }

        setResolvedRevision(revHash);
        setRevisionLoading(false);
      } catch (err: unknown) {
        if (
          !contextRef.current.isMounted ||
          abortCtrl.signal.aborted ||
          opGen !== generationRef.current ||
          currentSeq !== revReqSeq.current
        ) {
          return;
        }
        setRevisionError(`Lỗi kết nối khi lấy revision snapshot: ${err instanceof Error ? err.message : 'Lỗi mạng'}`);
        setRevisionLoading(false);
      }
    })();

    return () => {
      if (revAbortCtrlRef.current) {
        revAbortCtrlRef.current.abort();
      }
    };
  }, [directRevision, isEligibleRoleForSnapshot, boundRunId, effectiveDatasetId]);

  const retryLoad = useCallback(() => {
    setLoading(true);
    setErrorMsg(null);
    setForbiddenCode(null);
    loadFrame(frameId);
  }, [frameId, loadFrame]);

  // Complete frame action
  const handleCompleteFrame = async () => {
    if (!lease || isMutationBlocked) {
      setCompleteError('Không thể hoàn tất review: Chế độ xem hoặc lease không hợp lệ.');
      return;
    }

    const targetFrameId = frameId;
    const targetLeaseId = lease.id;
    const opGen = generationRef.current;

    setIsCompleting(true);
    setCompleteError(null);
    setUndecidedIssueIds([]);

    const isCurrentContext = () =>
      contextRef.current.isMounted &&
      opGen === generationRef.current &&
      contextRef.current.frameId === targetFrameId &&
      contextRef.current.leaseId === targetLeaseId;

    try {
      const { data: resData, error, response } = await apiClient.POST('/api/frames/{id}/complete/', {
        params: { path: { id: targetFrameId } },
        body: { lease_id: targetLeaseId },
      });

      // Context guard: discard if frame or lease changed while complete was in flight
      if (!isCurrentContext()) {
        return;
      }

      if (response.status === 422) {
        const detail = readErrorDetail(error);
        const undecided = (detail?.details?.undecided_issue_ids as number[] | undefined) ?? [];
        setUndecidedIssueIds(undecided);
        setCompleteError(
          detail?.message ||
            `Không thể hoàn tất: Còn ${undecided.length > 0 ? undecided.length : 'một số'} issue chưa có quyết định.`
        );
        return;
      }

      if (response.status === 409) {
        const detail = readErrorDetail(error);
        if (detail?.code === 'LEASE_CONFLICT') {
          const apiErr = new ApiRequestError(409, error, response.headers);
          handleLeaseConflict(apiErr);
          setCompleteError('Xung đột lease (409 Conflict - LEASE_CONFLICT): Quyền giữ frame đã hết hạn trong lúc hoàn tất.');
        } else {
          setCompleteError(detail?.message || 'Xung đột khi hoàn tất khung hình (409 Conflict).');
        }
        return;
      }

      if (error || !resData) {
        const detail = readErrorDetail(error);
        setCompleteError(detail?.message || 'Lỗi máy chủ khi hoàn tất review khung hình.');
        return;
      }

      await completeAfter(Promise.resolve(resData));
      if (!isCurrentContext()) return;
      setIsCompleted(true);
      onFrameCompleted?.();
    } catch {
      if (isCurrentContext()) {
        setCompleteError('Lỗi kết nối khi gửi yêu cầu hoàn tất review.');
      }
    } finally {
      if (isCurrentContext()) {
        setIsCompleting(false);
      }
    }
  };

  const handleDecisionSaved = (updatedIssue: Issue, rawDecision?: components['schemas']['IssueDecision']) => {
    if (rawDecision) {
      decisionSaved(rawDecision);
    }
    setData((prev) => {
      if (!prev || prev.frame.id !== frameId) return prev;
      return {
        ...prev,
        issues: prev.issues.map((i) => (i.id === updatedIssue.id ? updatedIssue : i)),
      };
    });
  };

  const handleManualIssueCreated = (newIssue: Issue) => {
    setData((prev) => {
      if (!prev || prev.frame.id !== frameId) return prev;
      return {
        ...prev,
        issues: [...prev.issues, newIssue],
      };
    });
    setSelectedIssueId(newIssue.id);
    setReviewMode('issue');
  };

  if (loading) {
    return (
      <div className="lx-card lx-card__body" style={{ textAlign: 'center', padding: '48px' }}>
        <p className="lx-muted">Đang tải dữ liệu khung hình và issue từ API thật...</p>
      </div>
    );
  }

  if (forbiddenCode || errorMsg) {
    return (
      <div className="lx-callout" role="alert" style={{ margin: '24px 0' }}>
        <span className="lx-callout__text">
          <b>Truy cập bị chặn ({forbiddenCode || 'Lỗi'}):</b> {errorMsg}
        </span>
        <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
          {!forbiddenCode && (
            <button onClick={retryLoad} className="lx-btn">
              Thử lại
            </button>
          )}
          {onBackToQueue ? (
            <button type="button" onClick={onBackToQueue} className="lx-btn">
              Về danh sách hàng đợi
            </button>
          ) : (
            <Link href="/review" className="lx-btn">
              Về danh sách hàng đợi
            </Link>
          )}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="lx-callout" role="alert" style={{ margin: '24px 0' }}>
        <span className="lx-callout__text">Không tìm thấy dữ liệu khung hình.</span>
        <button onClick={retryLoad} className="lx-btn" style={{ marginTop: '12px' }}>
          Thử lại
        </button>
      </div>
    );
  }

  const issues = data.issues;
  const currentIssueIndex = issues.findIndex((i) => i.id === selectedIssueId);
  const activeIssue = currentIssueIndex >= 0 ? issues[currentIssueIndex] : issues[0] ?? null;
  const totalIssues = issues.length;

  // Genuine approved CVAT link only; no localhost fallback
  const cvatDeepLink = data.frame.cvat_deep_link || null;

  // Resolve anchor policy
  const { policy: effectivePolicy, error: policyError } = resolveAnchorPolicy(
    anchorPolicyVersion,
    issues
  );

  return (
    <div className="lx-stack" style={{ gap: '16px' }}>
      {/* Read-Only Notice if accessed without LeaseGrant handoff */}
      {isReadOnly && (
        <div className="lx-callout lx-callout--info" role="status" style={{ background: 'var(--neutral-soft)' }}>
          <span className="lx-callout__text" style={{ color: 'var(--ink)' }}>
            <b>Chế độ xem kiểm tra (Read-only):</b> Frame được mở trực tiếp không kèm LeaseGrant từ hàng đợi ReviewQueues (T-034 handoff). Bạn có thể xem hình ảnh, annotation và bằng chứng nhưng thao tác lưu quyết định và hoàn tất bị khóa.
          </span>
        </div>
      )}

      {/* Lease Status Banner if expired or holder mismatch */}
      {!isReadOnly && (isExpired || isHolderMismatch || leaseError || forcedLeaseInvalidated) && (
        <div className="lx-callout" role="alert" style={{ background: 'var(--warning-soft)' }}>
          <span className="lx-callout__text" style={{ color: 'var(--warning-strong, #854d0e)' }}>
            <b>Cảnh báo Lease:</b> {leaseError || 'Xung đột lease (409 Conflict): Quyền giữ frame đã hết hạn hoặc thuộc người khác.'} Quyền ghi đã bị khóa để bảo toàn dữ liệu. Các quyết định đã lưu trên server trước đó vẫn được giữ nguyên.
          </span>
          <button onClick={renewLease} className="lx-btn lx-btn--sm" style={{ marginLeft: '12px' }}>
            Thử gia hạn lease
          </button>
        </div>
      )}

      {/* Frame Completion Banner */}
      {isCompleted && (
        <div className="lx-callout lx-callout--info" role="status" style={{ background: 'var(--success-soft)' }}>
          <span className="lx-callout__text" style={{ color: 'var(--success)' }}>
            Khung hình đã hoàn tất kiểm tra review thành công. Lease đã được trả lại.
          </span>
          <Link href="/review" className="lx-btn lx-btn--sm" style={{ marginLeft: '12px' }}>
            Về hàng đợi
          </Link>
        </div>
      )}

      {/* Complete Error & Undecided Issues Navigation */}
      {completeError && (
        <div className="lx-callout" role="alert">
          <span className="lx-callout__text">{completeError}</span>
          {undecidedIssueIds.length > 0 && (
            <div className="lx-row" style={{ gap: '6px', marginTop: '6px' }}>
              <span className="lx-subtle" style={{ fontSize: '12px' }}>Chuyển đến issue chưa quyết định:</span>
              {undecidedIssueIds.map((uId) => (
                <button
                  key={`undecided-${uId}`}
                  className="lx-btn lx-btn--sm"
                  onClick={() => setSelectedIssueId(uId)}
                >
                  Issue #{uId}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Workspace Main Grid */}
      <div className="lx-ws lx-ws--reference">
        {/* Stage Viewport */}
        <section className="lx-stage" aria-label="Khung hình annotation từ CVAT">
          {/* Stage Controls Bar */}
          <div className="lx-stage__bar">
            {/* Mode switch */}
            <div className="lx-segment" role="group" aria-label="Chế độ review">
              <button
                type="button"
                aria-pressed={reviewMode === 'issue'}
                onClick={() => setReviewMode('issue')}
              >
                Issue Review
              </button>
              <button
                type="button"
                aria-pressed={reviewMode === 'frame'}
                onClick={() => setReviewMode('frame')}
              >
                Frame Review
              </button>
            </div>

            {/* Frame metadata */}
            <span>
              Frame <b className="lx-num">{String(data.frame.frame_key.frame_number).padStart(5, '0')}</b> · Task #{data.frame.frame_key.cvat_task_id}{runId != null ? ` · Run #${runId}` : ''}
            </span>

            {/* Lease countdown & manual renew while valid (follow-up-22) */}
            {lease && !isExpired && !forcedLeaseInvalidated && (
              <span className="lx-row" style={{ gap: '6px', alignItems: 'center' }}>
                <span className="lx-subtle" style={{ color: remainingSeconds < 60 ? 'var(--warning)' : '#a1a8b3' }}>
                  · Lease: {Math.floor(remainingSeconds / 60)}:{String(remainingSeconds % 60).padStart(2, '0')}
                </span>
                <button
                  type="button"
                  onClick={renewLease}
                  className="lx-btn lx-btn--ghost lx-btn--sm"
                  style={{ padding: '2px 6px', fontSize: '11px' }}
                  title="Gia hạn lease thủ công trong khi vẫn còn hiệu lực"
                >
                  Thử gia hạn lease
                </button>
              </span>
            )}

            {/* T-036 Collector status */}
            <span
              className="lx-tag"
              title={effortCollectorStatus.reason}
              style={{ fontSize: '11px', background: 'var(--neutral-soft)', color: 'var(--ink-muted)' }}
            >
              Collector: T-036 hoạt động (idle: chờ PO)
            </span>

            <span style={{ flex: 1 }} />

            {/* Layer Checkboxes */}
            <label className="lx-check">
              <input
                type="checkbox"
                checked={showAnnotations}
                onChange={(e) => setShowAnnotations(e.target.checked)}
              />
              <span>Vùng neo Issue</span>
            </label>
            <label className="lx-check">
              <input
                type="checkbox"
                checked={showPredictions}
                onChange={(e) => setShowPredictions(e.target.checked)}
              />
              <span>Đề xuất mô hình</span>
            </label>

            {/* Zoom controls */}
            <div className="lx-row" style={{ gap: '4px' }}>
              <button
                type="button"
                className="lx-ghostbtn"
                onClick={() => setZoom((z) => Math.min(5, Number((z + 0.25).toFixed(2))))}
                title="Phóng to"
              >
                +
              </button>
              <span style={{ fontSize: '11px', minWidth: '36px', textAlign: 'center' }}>
                {Math.round(zoom * 100)}%
              </span>
              <button
                type="button"
                className="lx-ghostbtn"
                onClick={() => setZoom((z) => Math.max(0.5, Number((z - 0.25).toFixed(2))))}
                title="Thu nhỏ"
              >
                -
              </button>
              <button
                type="button"
                className="lx-ghostbtn"
                onClick={() => {
                  setZoom(1);
                  setPan({ x: 0, y: 0 });
                }}
                title="Đặt lại zoom và vị trí"
              >
                Reset
              </button>
            </div>

            {/* CVAT Deep Link (read-only, genuine only) */}
            {cvatDeepLink ? (
              <a
                href={cvatDeepLink}
                target="_blank"
                rel="noopener noreferrer"
                className="lx-ghostbtn"
                style={{ textDecoration: 'none' }}
              >
                Mở trong CVAT ↗
              </a>
            ) : (
              <span className="lx-subtle" style={{ fontSize: '11px' }}>
                CVAT link: Chưa có từ API
              </span>
            )}
          </div>

          {/* Interactive Canvas View */}
          <div className="lx-stage__view" style={{ padding: 0 }}>
            <ReviewCanvas
              frame={data.frame}
              issues={issues}
              selectedIssueId={selectedIssueId}
              onSelectIssue={(id) => setSelectedIssueId(id)}
              reviewMode={reviewMode}
              showAnnotations={showAnnotations}
              showPredictions={showPredictions}
              zoom={zoom}
              pan={pan}
              onZoomChange={setZoom}
              onPanChange={setPan}
              onSelectObjectForManualIssue={(obj) => {
                if (isMutationBlocked || !effectivePolicy) return;
                setSelectedObjectForManual(obj);
                setDrawnRegionForManual(null);
                setManualModalOpen(true);
              }}
              onCreateRegionManualIssue={(bbox) => {
                if (isMutationBlocked || !effectivePolicy) return;
                setSelectedObjectForManual(null);
                setDrawnRegionForManual(bbox);
                setManualModalOpen(true);
              }}
            />
          </div>

          {/* Stage Bottom Bar */}
          <div className="lx-stage__bar" style={{ borderTop: '1px solid #343a43', borderBottom: 0 }}>
            {/* Frame navigation (disabled per lease handoff contract) */}
            <button
              type="button"
              className="lx-ghostbtn"
              disabled
              title="Chuyển frame chỉ thực hiện qua hàng đợi ReviewQueues (LeaseGrant handoff); không tự động nhận frame kế tiếp."
            >
              ‹ Frame trước
            </button>
            <button
              type="button"
              className="lx-ghostbtn"
              disabled
              title="Chuyển frame chỉ thực hiện qua hàng đợi ReviewQueues (LeaseGrant handoff); không tự động nhận frame kế tiếp."
            >
              Frame sau ›
            </button>

            <span className="lx-subtle" style={{ margin: '0 4px' }}>|</span>

            {/* In-frame issue navigation */}
            <button
              type="button"
              className="lx-ghostbtn"
              disabled={currentIssueIndex <= 0}
              onClick={() => {
                if (currentIssueIndex > 0) setSelectedIssueId(issues[currentIssueIndex - 1].id);
              }}
              title="Chuyển đến issue trước trong cùng khung hình"
            >
              ‹ Issue trước
            </button>
            <button
              type="button"
              className="lx-ghostbtn"
              disabled={currentIssueIndex >= issues.length - 1}
              onClick={() => {
                if (currentIssueIndex < issues.length - 1) setSelectedIssueId(issues[currentIssueIndex + 1].id);
              }}
              title="Chuyển đến issue tiếp theo trong cùng khung hình"
            >
              Issue tiếp ›
            </button>

            <span style={{ flex: 1 }} />

            {reviewMode === 'frame' ? (
              <span>
                {effectivePolicy
                  ? 'Nhấn vào đối tượng cvat_shape hoặc kéo vẽ vùng để tạo manual issue.'
                  : (policyError || 'Tạo manual issue tạm khóa: Thiếu anchor policy_version (anchor-v1) đã duyệt từ T-035.')}
              </span>
            ) : (
              <span>Đường liền: vùng neo của Issue · Đường đứt: đề xuất của mô hình</span>
            )}
          </div>
        </section>

        {/* Aside Panel */}
        <aside className="lx-ws__panel" aria-label="Chi tiết issue và quyết định">
          {activeIssue ? (
            <>
              {/* Issue Header Section */}
              <div className="lx-ws__sec">
                <div className="lx-row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>
                    <b className="lx-mono">QC-{String(activeIssue.id).padStart(5, '0')}</b>
                    <span className="lx-hint"> · Issue {currentIssueIndex + 1} / {totalIssues}</span>
                  </span>
                  <div className="lx-row" style={{ gap: '6px' }}>
                    {activeIssue.severity && (
                      <span
                        className={`lx-badge ${
                          activeIssue.severity === 'critical'
                            ? 'lx-badge--danger'
                            : activeIssue.severity === 'medium'
                              ? 'lx-badge--warning'
                              : 'lx-badge--info'
                        }`}
                      >
                        {activeIssue.severity}
                      </span>
                    )}
                    <span className="lx-badge">
                      {activeIssue.state}
                    </span>
                  </div>
                </div>

                <h2 className="lx-h2" style={{ fontSize: '15px' }}>
                  {activeIssue.family === 'E1'
                    ? 'Nghi vấn: Thiếu bounding box (E1)'
                    : activeIssue.family === 'E2'
                      ? `Nghi vấn sai nhãn (E2)${
                          activeIssue.evidence?.[0]?.actual && activeIssue.evidence?.[0]?.prediction_class
                            ? `: ${activeIssue.evidence[0].actual} hay ${activeIssue.evidence[0].prediction_class}`
                            : ''
                        }`
                      : activeIssue.family === 'E3'
                        ? 'Nghi vấn: Trùng lặp bounding box (E3)'
                        : `Cảnh báo cấu trúc: ${activeIssue.rule_ids?.[0] || 'structural'}`}
                </h2>

                <dl className="lx-kv">
                  <dt>Frame · Đối tượng</dt>
                  <dd>
                    {String(data.frame.frame_key.frame_number).padStart(5, '0')} · {activeIssue.anchor.objects?.[0]?.id ?? 'N/A'}
                  </dd>
                  <dt>Annotation hiện tại</dt>
                  <dd>{activeIssue.evidence?.[0]?.actual || 'Chưa cung cấp nhãn từ API (T-035 gap)'}</dd>
                  <dt>Nguồn gốc (Origin)</dt>
                  <dd>
                    {activeIssue.origin === 'engine' ? 'Mô hình tự động' : 'Reviewer tạo thủ công'}
                    {resolvedRevision ? (
                      <span> · revision <span className="lx-mono">{resolvedRevision.slice(0, 7)}</span></span>
                    ) : ''}
                  </dd>
                  <dt>Loại neo (Anchor)</dt>
                  <dd>{activeIssue.anchor.kind}</dd>
                </dl>
              </div>

              {/* Evidence Section */}
              <div className="lx-ws__sec">
                <ReviewEvidenceTable
                  evidenceList={activeIssue.evidence || []}
                  engineStatuses={data.engines || []}
                  currentAnnotationClass={activeIssue.evidence?.[0]?.actual || undefined}
                />

                <ReviewGuidelineLookup
                  ruleId={activeIssue.rule_ids?.[0] || activeIssue.anchor.rule_id}
                  guidelineVersion={data.guideline_version}
                />

                {/* Similar Cases & Lineage Links */}
                <details style={{ marginTop: '8px' }}>
                  <summary style={{ cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>
                    Case tương tự đã phân xử ({activeIssue.links?.length || 0})
                  </summary>
                  {activeIssue.links && activeIssue.links.length > 0 ? (
                    <div style={{ marginTop: '6px' }}>
                      {activeIssue.links.map((link, idx) => (
                        <p key={`link-${idx}`} className="lx-muted" style={{ margin: '4px 0', fontSize: '13px' }}>
                          Issue #{link.issue_id} · {link.kind === 'recurrence_of' ? 'Tái diễn (recurrence)' : 'Gợi ý tái diễn (suggested recurrence)'}
                          {link.run_id != null ? ` · Run #${link.run_id}` : ''}
                        </p>
                      ))}
                    </div>
                  ) : (
                    <p className="lx-subtle" style={{ margin: '8px 0 0', fontSize: '13px' }}>
                      Không có case tương tự hoặc liên kết lineage cho issue này từ máy chủ.
                    </p>
                  )}
                </details>

                <div style={{ marginTop: '12px' }}>
                  <DecisionCaseLookup initialIssueId={activeIssue.id} compact />
                </div>
              </div>

              {/* Decisions Section */}
              <ReviewDecisionForm
                issue={activeIssue}
                lease={lease}
                currentUserId={currentUserId}
                snapshotRevision={resolvedRevision}
                revisionUnavailableReason={revisionUnavailableReason || revisionError}
                revisionLoading={revisionLoading}
                isLeaseExpired={isMutationBlocked}
                isSuperAdmin={isSuperAdmin}
                onDecisionSaved={handleDecisionSaved}
                onLeaseConflict={handleLeaseConflict}
                onNextIssue={() => {
                  if (currentIssueIndex < issues.length - 1) setSelectedIssueId(issues[currentIssueIndex + 1].id);
                }}
                onPrevIssue={() => {
                  if (currentIssueIndex > 0) setSelectedIssueId(issues[currentIssueIndex - 1].id);
                }}
                hasPrev={currentIssueIndex > 0}
                hasNext={currentIssueIndex < issues.length - 1}
              />
            </>
          ) : (
            <div className="lx-ws__sec" style={{ textAlign: 'center', padding: '32px' }}>
              <p className="lx-muted">Khung hình này không có issue tự động nào.</p>
              {effectivePolicy && !isMutationBlocked ? (
                <button
                  type="button"
                  className="lx-btn lx-btn--primary"
                  onClick={() => {
                    setReviewMode('frame');
                    setManualModalOpen(true);
                  }}
                >
                  + Tạo issue thủ công
                </button>
              ) : (
                <p className="lx-subtle" style={{ fontSize: '12px' }}>
                  {policyError || 'Chức năng tạo issue thủ công tạm khóa do thiếu anchor policy_version.'}
                </p>
              )}
            </div>
          )}

          {/* Complete Frame Action Footer */}
          <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)', background: 'var(--surface)' }}>
            <button
              type="button"
              className="lx-btn lx-btn--primary"
              style={{ width: '100%', justifyContent: 'center' }}
              disabled={isCompleting || isMutationBlocked}
              onClick={handleCompleteFrame}
            >
              {isCompleting ? 'Đang hoàn tất...' : 'Hoàn tất review frame'}
            </button>
          </div>
        </aside>
      </div>

      {/* Manual Issue Creation Modal */}
      {manualModalOpen && lease && effectivePolicy && (
        <ReviewManualIssueModal
          frameId={frameId}
          leaseId={lease.id}
          anchorPolicyVersion={effectivePolicy}
          selectedObject={selectedObjectForManual}
          drawnRegion={drawnRegionForManual}
          frameWidth={data.frame.width ?? undefined}
          frameHeight={data.frame.height ?? undefined}
          isLeaseExpired={isMutationBlocked}
          onClose={() => setManualModalOpen(false)}
          onCreated={handleManualIssueCreated}
          onLeaseConflict={handleLeaseConflict}
        />
      )}
    </div>
  );
}
