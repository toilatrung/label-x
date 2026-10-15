'use client';

import React, { useState, useRef, useEffect } from 'react';
import { apiClient } from '@/lib/api/client';
import { readErrorDetail, ApiRequestError } from '@/lib/api/errors';
import type { components } from '@/lib/api/contract';

type Issue = components['schemas']['Issue'];
type Lease = components['schemas']['Lease'];
type IssueFamily = components['schemas']['IssueFamily'];
type Severity = components['schemas']['Severity'];

export const ISSUE_STATE_LABELS: Record<string, string> = {
  pending_review: 'Chờ review',
  in_review: 'Đang review',
  confirmed: 'Đã xác nhận',
  rejected: 'Đã bác bỏ',
  escalated: 'Đã chuyển cấp trên',
  fix_pending: 'Chờ sửa',
  recheck_pending: 'Chờ kiểm tra lại',
  resolved: 'Đã xử lý',
  reopened: 'Mở lại',
};

export type DirectDecisionAction = 'confirm' | 'reject' | 'uncertain' | 'escalate';

export interface ReviewDecisionFormProps {
  issue: Issue;
  lease: Lease | null;
  snapshotRevision?: string | null;
  revisionUnavailableReason?: string | null;
  revisionLoading?: boolean;
  isLeaseExpired: boolean;
  currentUserId?: number | null;
  isSuperAdmin?: boolean;
  onDecisionSaved: (updatedIssue: Issue, rawDecision?: components['schemas']['IssueDecision']) => void;
  onLeaseConflict?: (serverError?: unknown) => void;
  onFormStateChange?: (dirty: boolean, busy: boolean) => void;
  onNextIssue?: () => void;
  onPrevIssue?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
}

/**
 * Generates an RFC 4122 v4 canonical UUID for Idempotency-Key headers.
 * Does not use timestamps or non-standard prefixes.
 */
export function generateCanonicalUUID(): string {
  if (typeof crypto !== 'undefined') {
    if (typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
    if (typeof crypto.getRandomValues === 'function') {
      const bytes = new Uint8Array(16);
      crypto.getRandomValues(bytes);
      bytes[6] = (bytes[6] & 0x0f) | 0x40; // Version 4
      bytes[8] = (bytes[8] & 0x3f) | 0x80; // Variant 10xx
      const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }
  }
  throw new Error('Môi trường không hỗ trợ crypto UUID chuẩn (RFC 4122).');
}

export function ReviewDecisionForm({
  issue,
  lease,
  currentUserId: currentUserIdProp,
  snapshotRevision,
  revisionUnavailableReason,
  revisionLoading = false,
  isLeaseExpired,
  isSuperAdmin = false,
  onDecisionSaved,
  onFormStateChange,
  onLeaseConflict,
  onNextIssue,
  onPrevIssue,
  hasPrev = false,
  hasNext = false,
}: ReviewDecisionFormProps) {
  const currentUserId = currentUserIdProp ?? lease?.holder_user_id ?? null;
  const [action, setAction] = useState<DirectDecisionAction>('confirm');
  const [family, setFamily] = useState<IssueFamily>(issue.family || 'E2');
  const [severity, setSeverity] = useState<Severity>(issue.severity || 'medium');
  const [reason, setReason] = useState<string>('');
  const [ruleId, setRuleId] = useState<string>(issue.rule_ids?.[0] || '');
  const [overrideReason, setOverrideReason] = useState<string>('');

  const [submitMode, setSubmitMode] = useState<'save' | 'save_advance' | null>(null);
  const isSubmitting = submitMode !== null;
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Real POST receipt state: retained when save succeeds on server but GET reconciliation fails
  const [savedReceipt, setSavedReceipt] = useState<components['schemas']['IssueDecision'] | null>(null);
  const [isRefreshingIssue, setIsRefreshingIssue] = useState<boolean>(false);

  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    onFormStateChange?.(dirty, isSubmitting || isRefreshingIssue);
  }, [dirty, isSubmitting, isRefreshingIssue, onFormStateChange]);
  const notifyDecisionSaved = (...args: Parameters<ReviewDecisionFormProps['onDecisionSaved']>) => {
    setDirty(false);
    onDecisionSaved(...args);
  };

  // Reset form inputs when active issue changes
  const [prevIssueId, setPrevIssueId] = useState(issue.id);
  if (issue.id !== prevIssueId) {
    setDirty(false);
    setPrevIssueId(issue.id);
    setAction('confirm');
    setFamily(issue.family || 'E2');
    setSeverity(issue.severity || 'medium');
    setReason('');
    setRuleId(issue.rule_ids?.[0] || '');
    setOverrideReason('');
    setFormError(null);
    setSuccessMessage(null);
    setSavedReceipt(null);
    setIsRefreshingIssue(false);
  }

  const idempotencyKeyRef = useRef<string | null>(null);
  const lastPayloadSignatureRef = useRef<string | null>(null);
  const advanceOnSuccessRef = useRef<boolean>(false);
  const opSeqRef = useRef<number>(0);
  const generationRef = useRef<number>(0);

  const contextRef = useRef({
    issueId: issue.id,
    leaseId: lease?.id ?? null,
    currentUserId,
    isMounted: true,
  });

  const isMountedRef = useRef<boolean>(true);
  useEffect(() => {
    isMountedRef.current = true;
    contextRef.current.isMounted = true;
    return () => {
      isMountedRef.current = false;
      contextRef.current.isMounted = false;
      generationRef.current += 1;
      opSeqRef.current += 1;
    };
  }, []);

  useEffect(() => {
    const prev = contextRef.current;
    const isSameLeaseId = prev.leaseId === (lease?.id ?? null);
    const isMeaningfulChange =
      prev.issueId !== issue.id ||
      prev.currentUserId !== currentUserId ||
      !isSameLeaseId;

    if (isMeaningfulChange) {
      generationRef.current += 1;
      opSeqRef.current += 1;
      contextRef.current = {
        issueId: issue.id,
        leaseId: lease?.id ?? null,
        currentUserId,
        isMounted: true,
      };
      idempotencyKeyRef.current = null;
      lastPayloadSignatureRef.current = null;
      setSubmitMode(null);
      advanceOnSuccessRef.current = false;
      setIsRefreshingIssue(false);
      if (prev.issueId !== issue.id) {
        setSavedReceipt(null);
      }
    } else {
      contextRef.current = {
        ...contextRef.current,
        leaseId: lease?.id ?? null,
        currentUserId,
      };
    }
  }, [issue.id, lease?.id, currentUserId]);

  const currentIssueIdRef = useRef(issue.id);
  useEffect(() => {
    currentIssueIdRef.current = issue.id;
  }, [issue.id]);

  const trimmedRevision = snapshotRevision?.trim();
  const hasVerifiedRevision = Boolean(trimmedRevision);
  const isDecisionBlocked =
    isLeaseExpired ||
    !hasVerifiedRevision ||
    issue.state !== 'in_review' ||
    isSubmitting ||
    Boolean(savedReceipt);

  // Client validation matching backend contract & T-035 inspected rules
  const validateForm = (): string | null => {
    if (savedReceipt) {
      return 'Quyết định đã được lưu thành công trên máy chủ. Vui lòng làm mới dữ liệu issue trước khi gửi quyết định mới.';
    }
    if (isLeaseExpired || !lease) {
      return 'Chế độ xem hoặc lease đã hết hạn. Không có quyền ghi quyết định.';
    }

    if (!hasVerifiedRevision) {
      return (
        revisionUnavailableReason ||
        'Chưa có revision của Snapshot đã xác thực nên chưa thể gửi quyết định.'
      );
    }

    if (issue.state !== 'in_review') {
      return `Issue đang ở trạng thái "${ISSUE_STATE_LABELS[issue.state] ?? issue.state}". Chỉ issue ở trạng thái "Đang review" mới lưu được quyết định trực tiếp.`;
    }

    if (['reject', 'uncertain', 'escalate'].includes(action)) {
      if (!reason.trim()) {
        return `Hành động "${action}" yêu cầu phải nhập lý do cụ thể.`;
      }
    }

    if (action === 'confirm') {
      if (family !== issue.family) {
        return `Loại lỗi xác nhận (${family}) phải khớp với nhóm lỗi của issue (${issue.family}).`;
      }
      if (!severity) {
        return 'Vui lòng chọn mức độ nghiêm trọng (Severity).';
      }
    }


    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSuccessMessage(null);

    const validationErr = validateForm();
    if (validationErr) {
      advanceOnSuccessRef.current = false;
      setFormError(validationErr);
      return;
    }

    if (!lease || !trimmedRevision) {
      advanceOnSuccessRef.current = false;
      return;
    }

    const opSeq = ++opSeqRef.current;
    const opGen = generationRef.current;
    const opIssueId = issue.id;
    const opLeaseId = lease.id;
    const opUserId = currentUserId;
    setSubmitMode(advanceOnSuccessRef.current ? 'save_advance' : 'save');

    const isCurrentContext = () =>
      isMountedRef.current &&
      contextRef.current.isMounted &&
      opGen === generationRef.current &&
      opSeq === opSeqRef.current &&
      contextRef.current.issueId === opIssueId &&
      contextRef.current.leaseId === opLeaseId &&
      contextRef.current.currentUserId === opUserId;

    const payloadSignature = `${issue.id}:${action}:${action === 'confirm' ? family : ''}:${action === 'confirm' ? severity : ''}:${reason.trim()}:${ruleId.trim()}:${isSuperAdmin ? overrideReason.trim() : ''}:${trimmedRevision}`;

    let idempotencyKey = idempotencyKeyRef.current;
    if (!idempotencyKey || lastPayloadSignatureRef.current !== payloadSignature) {
      try {
        idempotencyKey = generateCanonicalUUID();
      } catch (err: unknown) {
        advanceOnSuccessRef.current = false;
        setFormError(err instanceof Error ? err.message : 'Không thể sinh canonical UUID cho Idempotency-Key.');
        setSubmitMode(null);
        return;
      }
      idempotencyKeyRef.current = idempotencyKey;
      lastPayloadSignatureRef.current = payloadSignature;
    }

    try {
      const { data, error, response } = await apiClient.POST('/api/issues/{id}/decisions/', {
        params: {
          path: { id: opIssueId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        body: {
          lease_id: opLeaseId,
          action,
          revision: trimmedRevision,
          family: action === 'confirm' ? family : undefined,
          severity: action === 'confirm' ? severity : undefined,
          reason: reason.trim() || undefined,
          rule_id: ruleId.trim() || undefined,
          override_reason: isSuperAdmin ? overrideReason.trim() : undefined,
        },
      });

      // Context guard: discard response if unmounted or context (issue/lease/user) changed while in flight
      if (!isCurrentContext()) {
        return;
      }

      if (response.status === 409) {
        advanceOnSuccessRef.current = false;
        const detail = readErrorDetail(error);
        if (detail?.code === 'LEASE_CONFLICT') {
          const apiErr = new ApiRequestError(409, error, response.headers);
          onLeaseConflict?.(apiErr);
          setFormError('Xung đột lease (409 Conflict - LEASE_CONFLICT): Quyền giữ frame đã hết hạn hoặc thuộc người khác.');
        } else if (detail?.code === 'INVALID_TRANSITION') {
          setFormError(`(409 INVALID_TRANSITION) ${detail?.message || 'Chuyển đổi trạng thái không hợp lệ, kiểm tra revision snapshot.'}`);
        } else if (detail?.code === 'IDEMPOTENCY_KEY_REUSED') {
          setFormError(`(409 IDEMPOTENCY_KEY_REUSED) ${detail?.message || 'Khóa Idempotency-Key đã được tái sử dụng với nội dung khác.'}`);
        } else if (detail?.code === 'ISSUE_EXISTS') {
          setFormError(`(409 ISSUE_EXISTS) ${detail?.message || 'Issue đã tồn tại trên khung hình.'}`);
        } else {
          setFormError(detail?.message || 'Xung đột dữ liệu khi lưu quyết định (409 Conflict).');
        }
        return;
      }

      if (response.status === 400) {
        advanceOnSuccessRef.current = false;
        const detail = readErrorDetail(error);
        setFormError(detail?.message || 'Dữ liệu không hợp lệ theo kiểm tra máy chủ (400 VALIDATION_ERROR).');
        return;
      }

      if (response.status === 403) {
        advanceOnSuccessRef.current = false;
        const detail = readErrorDetail(error);
        if (detail?.code === 'SELF_REVIEW_FORBIDDEN') {
          setFormError('Bạn không được review annotation do chính mình thực hiện (Anti-self-review FR-REV-03).');
        } else if (detail?.code === 'IDENTITY_MAPPING_MISSING') {
          setFormError('Tài khoản của bạn chưa được liên kết định danh CVAT (IDENTITY_MAPPING_MISSING).');
        } else if (detail?.code === 'OUT_OF_SCOPE') {
          setFormError('Dataset nằm ngoài phạm vi phân quyền của bạn (OUT_OF_SCOPE).');
        } else {
          setFormError(detail?.message || 'Không có quyền lưu quyết định (403 Forbidden).');
        }
        return;
      }

      if (response.status === 422 || error) {
        advanceOnSuccessRef.current = false;
        const detail = readErrorDetail(error);
        setFormError(detail?.message || 'Dữ liệu quyết định không hợp lệ theo quy tắc nghiệp vụ (422 BUSINESS_RULE_UNMET).');
        return;
      }

      if (data) {
        setSavedReceipt(data);
        setSuccessMessage('Quyết định đã được lưu thành công trên máy chủ.');
        // Reset idempotency key for next distinct operation
        idempotencyKeyRef.current = null;
        lastPayloadSignatureRef.current = null;

        // Fetch approved GET /api/issues/{id}/ to reconcile actual Issue, state and decisions
        try {
          const { data: refreshedIssue } = await apiClient.GET('/api/issues/{id}/', {
            params: { path: { id: opIssueId } },
          });

          // Guard against stale response if active issue changed while in flight
          if (!isCurrentContext()) {
            return;
          }

          if (refreshedIssue && refreshedIssue.id === opIssueId) {
            setSavedReceipt(null);
            notifyDecisionSaved(refreshedIssue, data);
            if (advanceOnSuccessRef.current) {
              advanceOnSuccessRef.current = false;
              if (hasNext && onNextIssue) {
                onNextIssue();
              }
            }
          } else {
            advanceOnSuccessRef.current = false;
            // Retain real POST receipt in state; preserve authoritative history unchanged.
            // Do NOT fabricate ReviewDecision (actor_role, new Date(), reference_match_status).
            // Deliver actual raw decision callback to collector even when GET fails.
            notifyDecisionSaved(issue, data);
            setFormError('Quyết định đã lưu thành công trên máy chủ, nhưng không thể làm mới dữ liệu issue từ máy chủ.');
          }
        } catch {
          advanceOnSuccessRef.current = false;
          if (isCurrentContext()) {
            // Retain real POST receipt in state; preserve authoritative history unchanged.
            // Do NOT fabricate ReviewDecision (actor_role, new Date(), reference_match_status).
            // Deliver actual raw decision callback to collector even when GET fails.
            notifyDecisionSaved(issue, data);
            setFormError('Quyết định đã lưu thành công trên máy chủ, nhưng gặp lỗi mạng khi làm mới dữ liệu issue.');
          }
        }
      }
    } catch {
      advanceOnSuccessRef.current = false;
      if (isCurrentContext()) {
        setFormError('Lỗi kết nối mạng khi gửi quyết định.');
      }
    } finally {
      if (isCurrentContext()) {
        setSubmitMode(null);
      }
    }
  };

  const handleRetryRefresh = async () => {
    if (!savedReceipt) return;
    const opSeq = ++opSeqRef.current;
    const opGen = generationRef.current;
    const opIssueId = issue.id;
    setIsRefreshingIssue(true);
    setFormError(null);

    const isCurrentContext = () =>
      isMountedRef.current &&
      contextRef.current.isMounted &&
      opGen === generationRef.current &&
      opSeq === opSeqRef.current &&
      contextRef.current.issueId === opIssueId;

    try {
      const { data: refreshedIssue, error: getErr } = await apiClient.GET('/api/issues/{id}/', {
        params: { path: { id: opIssueId } },
      });

      if (!isCurrentContext()) {
        return;
      }

      if (refreshedIssue && refreshedIssue.id === opIssueId) {
        const receipt = savedReceipt;
        setSavedReceipt(null);
        setSuccessMessage('Đã đồng bộ dữ liệu issue thành công từ máy chủ.');
        notifyDecisionSaved(refreshedIssue, receipt);
      } else {
        const detail = readErrorDetail(getErr);
        setFormError(detail?.message || 'Không thể làm mới dữ liệu issue từ máy chủ.');
      }
    } catch (err: unknown) {
      if (isCurrentContext()) {
        setFormError(`Lỗi kết nối khi làm mới dữ liệu issue: ${err instanceof Error ? err.message : 'Lỗi mạng'}`);
      }
    } finally {
      if (isCurrentContext()) {
        setIsRefreshingIssue(false);
      }
    }
  };

  return (
    <div className="lx-ws__decide">
      <div className="lx-row lx-row--between lx-items-center">
        <span className="lx-label">Quyết định review</span>
        {issue.review_decisions.length > 0 && (
          <span className="lx-badge lx-badge--info">
            Đã có {issue.review_decisions.length} quyết định
          </span>
        )}
      </div>

      {revisionLoading && (
        <div className="lx-callout lx-callout--info lx-callout--compact lx-text-12" role="status">
          <span className="lx-callout__text">
            Đang xác thực snapshot revision từ máy chủ...
          </span>
        </div>
      )}

      {!hasVerifiedRevision && !revisionLoading && (
        <div className="lx-callout lx-callout--warning lx-callout--compact lx-text-12" role="alert">
          <span className="lx-callout__text">
            {revisionUnavailableReason ||
              'Chưa có revision của Snapshot đã xác thực. Chức năng lưu quyết định tạm khoá.'}
          </span>
        </div>
      )}

      {issue.state !== 'in_review' && (
        <div className="lx-callout lx-callout--info lx-callout--compact lx-text-12" role="status">
          <span className="lx-callout__text">
            Issue đang ở trạng thái {ISSUE_STATE_LABELS[issue.state] ?? issue.state}. Chỉ issue ở trạng thái Đang review mới lưu được quyết định trực tiếp. Lịch sử quyết định trước đó vẫn được bảo toàn đầy đủ.
          </span>
        </div>
      )}

      {formError && (
        <div className="lx-callout lx-callout--compact lx-text-13" role="alert">
          <span className="lx-callout__text">{formError}</span>
        </div>
      )}

      {successMessage && (
        <div
          className="lx-callout lx-callout--info lx-callout--compact lx-text-13 lx-callout--success"
          role="status"
        >
          <span className="lx-callout__text lx-text-success">
            {successMessage}
          </span>
        </div>
      )}

      {/* Real POST server receipt: displayed when save succeeded on server but GET reconciliation is pending */}
      {savedReceipt && (
        <div
          className="lx-card lx-card--receipt"
          role="status"
        >
          <div className="lx-row lx-row--between lx-items-center">
            <span className="lx-label lx-text-11 lx-text-info">
              Biên nhận máy chủ (POST Receipt #{savedReceipt.id})
            </span>
            <span className="lx-subtle lx-text-11">
              {savedReceipt.created_at}
            </span>
          </div>
          <div className="lx-stack lx-gap-1 lx-mt-1">
            <div>
              <b>Hành động đã lưu:</b> {savedReceipt.action}
            </div>
            <div>
              <b>Revision snapshot:</b> <code>{savedReceipt.revision}</code>
            </div>
            <div className="lx-subtle lx-text-11">
              Thời điểm máy chủ ghi nhận: {savedReceipt.created_at}
            </div>
          </div>
          <div className="lx-mt-2">
            <button
              type="button"
              className="lx-btn lx-btn--xs lx-text-12"
              disabled={isRefreshingIssue}
              onClick={handleRetryRefresh}
            >
              {isRefreshingIssue ? 'Đang làm mới...' : 'Thử làm mới lại dữ liệu issue'}
            </button>
          </div>
        </div>
      )}

      <form onChangeCapture={() => setDirty(true)} onSubmit={handleSubmit} className="lx-stack lx-gap-3">
        {/* Choices radio group: 4 direct actions + 1 disabled rework placeholder */}
        <div className="lx-choices" role="radiogroup" aria-label="Loại quyết định">
          <label className="lx-choice">
            <input
              type="radio"
              name="decision-action"
              value="confirm"
              checked={action === 'confirm'}
              onChange={() => setAction('confirm')}
              disabled={isDecisionBlocked}
            />
            <span>Xác nhận lỗi</span>
          </label>
          <label className="lx-choice">
            <input
              type="radio"
              name="decision-action"
              value="reject"
              checked={action === 'reject'}
              onChange={() => setAction('reject')}
              disabled={isDecisionBlocked}
            />
            <span>Bác bỏ</span>
          </label>
          <label className="lx-choice">
            <input
              type="radio"
              name="decision-action"
              value="uncertain"
              checked={action === 'uncertain'}
              onChange={() => setAction('uncertain')}
              disabled={isDecisionBlocked}
            />
            <span>Chưa chắc chắn</span>
          </label>
          <label
            className="lx-choice lx-choice--disabled"
            title="Yêu cầu sửa được tạo ở luồng Rework sau khi xác nhận lỗi, không gửi cùng quyết định này."
          >
            <input
              type="radio"
              name="decision-action"
              value="request_fix"
              checked={false}
              disabled={true}
              aria-disabled="true"
            />
            <span>Yêu cầu sửa</span>
          </label>
          <label className="lx-choice">
            <input
              type="radio"
              name="decision-action"
              value="escalate"
              checked={action === 'escalate'}
              onChange={() => setAction('escalate')}
              disabled={isDecisionBlocked}
            />
            <span>Chuyển cấp trên</span>
          </label>
        </div>

        {/* Fields for confirm action */}
        {action === 'confirm' && (
          <div className="lx-grid lx-grid--2">
            <div className="lx-field">
              <label className="lx-label" htmlFor="decision-family">
                Loại lỗi đã xác nhận (phải khớp nhóm issue: {issue.family})
              </label>
              <select
                id="decision-family"
                className="lx-select"
                value={family}
                onChange={(e) => setFamily(e.target.value as IssueFamily)}
                disabled={isDecisionBlocked}
              >
                <option value={issue.family}>{issue.family} (khớp với issue)</option>
                <option value="E1">E1 · Thiếu box</option>
                <option value="E2">E2 · Sai lớp</option>
                <option value="E3">E3 · Trùng box</option>
                <option value="structural">structural · Cấu trúc</option>
              </select>
            </div>
            <div className="lx-field">
              <label className="lx-label" htmlFor="decision-severity">
                Mức độ nghiêm trọng
              </label>
              <select
                id="decision-severity"
                className="lx-select"
                value={severity}
                onChange={(e) => setSeverity(e.target.value as Severity)}
                disabled={isDecisionBlocked}
              >
                <option value="critical">Nghiêm trọng</option>
                <option value="medium">Trung bình</option>
                <option value="minor">Nhẹ</option>
              </select>
            </div>
          </div>
        )}

        {/* Rule ID field if confirming */}
        {action === 'confirm' && (
          <div className="lx-field">
            <label className="lx-label" htmlFor="decision-rule">
              Mã quy tắc liên quan (Rule ID)
            </label>
            <input
              id="decision-rule"
              type="text"
              className="lx-input"
              value={ruleId}
              onChange={(e) => setRuleId(e.target.value)}
              placeholder="Ví dụ: VEH-03"
              disabled={isDecisionBlocked}
            />
          </div>
        )}

        {/* Reason field */}
        <div className="lx-field">
          <label className="lx-label" htmlFor="decision-reason">
            Lý do {['reject', 'uncertain', 'escalate'].includes(action) && <span className="lx-text-danger">*</span>}
          </label>
          <textarea
            id="decision-reason"
            className="lx-textarea"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={
              action === 'confirm'
                ? 'Ghi chú giải thích nếu cần (không bắt buộc)'
                : 'Nhập lý do chi tiết cho quyết định này...'
            }
            disabled={isDecisionBlocked}
          />
        </div>

        {/* Optional administrative note, retained in the audit record. */}
        {isSuperAdmin && (
          <div className="lx-field lx-field--divider">
            <label className="lx-label" htmlFor="override-reason">
              Ghi chú quản trị (không bắt buộc)
            </label>
            <input
              id="override-reason"
              type="text"
              className="lx-input"
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              placeholder="Ghi chú cho nhật ký thao tác..."
              disabled={isDecisionBlocked}
            />
          </div>
        )}

        {/* Action buttons */}
        <div className="lx-row lx-row--between lx-mt-2">
          <button
            type="button"
            className="lx-btn lx-btn--ghost"
            onClick={onPrevIssue}
            disabled={!hasPrev || isSubmitting}
          >
            ‹ Issue trước
          </button>
          <div className="lx-row lx-gap-2">
            {hasNext && (
              <button
                type="submit"
                className="lx-btn"
                disabled={isDecisionBlocked}
                onClick={() => {
                  advanceOnSuccessRef.current = false;
                }}
              >
                {submitMode === 'save' ? 'Đang lưu...' : 'Lưu quyết định'}
              </button>
            )}
            <button
              type="submit"
              className="lx-btn lx-btn--primary"
              disabled={isDecisionBlocked}
              onClick={() => {
                advanceOnSuccessRef.current = hasNext;
              }}
            >
              {submitMode === 'save_advance'
                ? 'Đang lưu & chuyển...'
                : submitMode === 'save'
                  ? 'Đang lưu...'
                  : hasNext
                    ? 'Lưu và chuyển issue tiếp ›'
                    : 'Lưu quyết định'}
            </button>
          </div>
        </div>
      </form>

      {/* Decision history list */}
      {issue.review_decisions.length > 0 && (
        <div className="lx-stack lx-gap-2 lx-mt-3 lx-stack--divider">
          <span className="lx-label lx-text-11">
            Lịch sử quyết định đã lưu trên server:
          </span>
          <div className="lx-stack lx-gap-1">
            {issue.review_decisions.map((dec, idx) => (
              <div
                key={`hist-${dec.id || idx}`}
                className="lx-card lx-card--compact lx-text-12"
              >
                <div className="lx-row lx-row--between">
                  <b>{dec.decision}</b>
                  <span className="lx-subtle lx-text-11">
                    {new Date(dec.recorded_at).toLocaleTimeString('vi-VN')}
                  </span>
                </div>
                {dec.reason && <p className="lx-muted lx-mt-1">{dec.reason}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
