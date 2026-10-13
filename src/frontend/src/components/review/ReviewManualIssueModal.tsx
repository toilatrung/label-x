'use client';

import React, { useState, useRef, useEffect } from 'react';
import { apiClient } from '@/lib/api/client';
import { readErrorDetail } from '@/lib/api/errors';
import type { components } from '@/lib/api/contract';
import { generateCanonicalUUID } from './ReviewDecisionForm';

type Issue = components['schemas']['Issue'];
type IssueFamily = components['schemas']['IssueFamily'];
type BBox = components['schemas']['BBox'];
type ObjectRef = components['schemas']['ObjectRef'];

export interface ReviewManualIssueModalProps {
  frameId: number;
  leaseId: number;
  anchorPolicyVersion?: string | null;
  selectedObject?: ObjectRef | null;
  drawnRegion?: BBox | null;
  frameWidth?: number;
  frameHeight?: number;
  isLeaseExpired?: boolean;
  onClose: () => void;
  onCreated: (newIssue: Issue) => void;
  onLeaseConflict?: () => void;
}

export function ReviewManualIssueModal({
  frameId,
  leaseId,
  anchorPolicyVersion,
  selectedObject,
  drawnRegion,
  frameWidth,
  frameHeight,
  isLeaseExpired = false,
  onClose,
  onCreated,
  onLeaseConflict,
}: ReviewManualIssueModalProps) {
  const [family, setFamily] = useState<IssueFamily>('E2');
  const [description, setDescription] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const operationSeqRef = useRef<number>(0);
  const idempotencyKeyRef = useRef<string | null>(null);
  const lastPayloadSignatureRef = useRef<string | null>(null);
  const contextRef = useRef({ frameId, leaseId, isMounted: true });

  const isMountedRef = useRef<boolean>(true);
  useEffect(() => {
    isMountedRef.current = true;
    contextRef.current.isMounted = true;
    return () => {
      isMountedRef.current = false;
      contextRef.current.isMounted = false;
      operationSeqRef.current += 1;
    };
  }, []);

  useEffect(() => {
    if (contextRef.current.frameId !== frameId || contextRef.current.leaseId !== leaseId) {
      operationSeqRef.current += 1;
      contextRef.current = { frameId, leaseId, isMounted: true };
    }
  }, [frameId, leaseId]);

  const anchorKind: 'manual_object' | 'manual_region' = selectedObject
    ? 'manual_object'
    : 'manual_region';

  const trimmedPolicy = anchorPolicyVersion?.trim();
  const hasPolicy = Boolean(trimmedPolicy);

  const validateManualInput = (): string | null => {
    if (isLeaseExpired) {
      return 'Lease đã hết hạn hoặc không có quyền ghi. Không thể tạo issue thủ công.';
    }

    if (!hasPolicy || !trimmedPolicy) {
      return 'Chưa có phiên bản chính sách neo đã duyệt. Không thể tạo issue thủ công.';
    }

    if (description.trim().length > 2000) {
      return 'Mô tả chi tiết không được vượt quá 2000 ký tự.';
    }

    if (anchorKind === 'manual_object') {
      if (!selectedObject) {
        return 'Vui lòng chọn đối tượng trước khi tạo issue đối tượng.';
      }
      if (selectedObject.namespace !== 'cvat_shape') {
        return 'Chỉ đối tượng cvat_shape từ khung hình mới hợp lệ làm neo manual_object.';
      }
    }

    if (anchorKind === 'manual_region') {
      if (!drawnRegion) {
        return 'Vui lòng vẽ vùng lỗi trên khung hình trước khi tạo issue vùng.';
      }
      const { x1, y1, x2, y2 } = drawnRegion;
      if (!Number.isFinite(x1) || !Number.isFinite(y1) || !Number.isFinite(x2) || !Number.isFinite(y2)) {
        return 'Tọa độ vùng vẽ không hợp lệ (không phải số hữu hạn).';
      }
      if (x2 <= x1 || y2 <= y1) {
        return 'Kích thước vùng vẽ không hợp lệ.';
      }
      if (frameWidth && frameHeight) {
        if (x1 < 0 || y1 < 0 || x2 > frameWidth || y2 > frameHeight) {
          return 'Vùng vẽ vượt ra ngoài giới hạn kích thước khung hình.';
        }
      }
    }

    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    const validationErr = validateManualInput();
    if (validationErr) {
      setErrorMsg(validationErr);
      return;
    }

    setIsSubmitting(true);

    const payloadSignature = `${frameId}:${leaseId}:${family}:${anchorKind}:${selectedObject ? selectedObject.id : ''}:${drawnRegion ? `${drawnRegion.x1},${drawnRegion.y1},${drawnRegion.x2},${drawnRegion.y2}` : ''}:${description.trim()}:${trimmedPolicy}`;

    let idempotencyKey = idempotencyKeyRef.current;
    if (!idempotencyKey || lastPayloadSignatureRef.current !== payloadSignature) {
      try {
        idempotencyKey = generateCanonicalUUID();
      } catch (err: unknown) {
        setErrorMsg(err instanceof Error ? err.message : 'Không thể sinh canonical UUID cho Idempotency-Key.');
        setIsSubmitting(false);
        return;
      }
      idempotencyKeyRef.current = idempotencyKey;
      lastPayloadSignatureRef.current = payloadSignature;
    }

    const opSeq = ++operationSeqRef.current;
    const targetFrameId = frameId;
    const targetLeaseId = leaseId;

    try {
      const { data, error, response } = await apiClient.POST('/api/issues/', {
        params: {
          header: { 'Idempotency-Key': idempotencyKey },
        },
        body: {
          frame_id: targetFrameId,
          lease_id: targetLeaseId,
          family,
          anchor: {
            kind: anchorKind,
            objects: selectedObject ? [selectedObject] : [],
            bbox: drawnRegion ?? undefined,
            policy_version: trimmedPolicy!,
          },
          description: description.trim() || undefined,
        },
      });

      const isCurrentContext = () =>
        isMountedRef.current &&
        contextRef.current.isMounted &&
        opSeq === operationSeqRef.current &&
        contextRef.current.frameId === targetFrameId &&
        contextRef.current.leaseId === targetLeaseId;

      // Context guard: discard if unmounted, generation changed, or frame/lease changed while in flight
      if (!isCurrentContext()) {
        return;
      }

      if (response.status === 409) {
        const detail = readErrorDetail(error);
        if (detail?.code === 'LEASE_CONFLICT') {
          onLeaseConflict?.();
          setErrorMsg('Xung đột lease (409 LEASE_CONFLICT): Quyền giữ frame đã hết hạn hoặc thuộc người khác.');
        } else if (detail?.code === 'ISSUE_EXISTS') {
          setErrorMsg(`(409 ISSUE_EXISTS) ${detail?.message || 'Issue đã tồn tại trên khung hình.'}`);
        } else if (detail?.code === 'IDEMPOTENCY_KEY_REUSED') {
          setErrorMsg(detail?.message || 'Khóa Idempotency-Key đã được tái sử dụng (409 IDEMPOTENCY_KEY_REUSED).');
        } else if (detail?.code === 'INVALID_TRANSITION') {
          setErrorMsg(detail?.message || 'Chuyển đổi trạng thái không hợp lệ (409 INVALID_TRANSITION).');
        } else {
          setErrorMsg(detail?.message || 'Xung đột khi tạo issue (409 Conflict).');
        }
        return;
      }

      if (response.status === 400) {
        const detail = readErrorDetail(error);
        setErrorMsg(detail?.message || 'Dữ liệu không hợp lệ (400 VALIDATION_ERROR).');
        return;
      }

      if (response.status === 403) {
        const detail = readErrorDetail(error);
        setErrorMsg(detail?.message || 'Không có quyền tạo issue thủ công (403 Forbidden).');
        return;
      }

      if (response.status === 422 || error || !data) {
        const detail = readErrorDetail(error);
        setErrorMsg(detail?.message || 'Không thỏa mãn quy tắc nghiệp vụ khi tạo issue thủ công (422).');
        return;
      }

      idempotencyKeyRef.current = null;
      lastPayloadSignatureRef.current = null;
      onCreated(data);
      onClose();
    } catch {
      if (
        isMountedRef.current &&
        contextRef.current.isMounted &&
        opSeq === operationSeqRef.current &&
        contextRef.current.frameId === targetFrameId &&
        contextRef.current.leaseId === targetLeaseId
      ) {
        setErrorMsg('Lỗi kết nối mạng khi gửi yêu cầu tạo issue.');
      }
    } finally {
      if (
        isMountedRef.current &&
        contextRef.current.isMounted &&
        opSeq === operationSeqRef.current &&
        contextRef.current.frameId === targetFrameId &&
        contextRef.current.leaseId === targetLeaseId
      ) {
        setIsSubmitting(false);
      }
    }
  };

  return (
    <div
      className="lx-backdrop"
      style={{
        display: 'grid',
        placeItems: 'center',
        background: 'rgba(0,0,0,0.5)',
        zIndex: 50,
      }}
      onClick={onClose}
    >
      <div
        className="lx-card"
        style={{
          width: '460px',
          maxWidth: '90vw',
          background: 'var(--surface)',
          padding: '20px',
        }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="manual-issue-title"
      >
        <h2 id="manual-issue-title" className="lx-h2" style={{ marginBottom: '12px' }}>
          Tạo issue thủ công ({anchorKind === 'manual_object' ? 'theo đối tượng' : 'theo vùng vẽ'})
        </h2>

        {!hasPolicy && (
          <div className="lx-callout lx-callout--warning" role="alert" style={{ marginBottom: '12px', padding: '8px 12px' }}>
            <span className="lx-callout__text">
              Thiếu phiên bản chính sách neo đã duyệt. Quyền tạo issue thủ công tạm khoá.
            </span>
          </div>
        )}

        {errorMsg && (
          <div className="lx-callout" role="alert" style={{ marginBottom: '12px', padding: '8px 12px' }}>
            <span className="lx-callout__text">{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="lx-stack" style={{ gap: '14px' }}>
          <div className="lx-field">
            <span className="lx-label">Loại neo</span>
            <span className="lx-tag lx-tag--ro">
              {anchorKind === 'manual_object'
                ? `Đối tượng: ${selectedObject?.namespace}:${selectedObject?.id}`
                : `Vùng vẽ: (${drawnRegion?.x1}, ${drawnRegion?.y1}) → (${drawnRegion?.x2}, ${drawnRegion?.y2})`}
            </span>
          </div>

          <div className="lx-field">
            <label className="lx-label" htmlFor="manual-family">
              Nhóm lỗi (Issue Family)
            </label>
            <select
              id="manual-family"
              className="lx-select"
              value={family}
              onChange={(e) => setFamily(e.target.value as IssueFamily)}
              disabled={isSubmitting || !hasPolicy || isLeaseExpired}
            >
              <option value="E1">E1 · Thiếu box</option>
              <option value="E2">E2 · Sai lớp</option>
              <option value="E3">E3 · Trùng box</option>
              <option value="structural">Cảnh báo cấu trúc</option>
            </select>
          </div>

          <div className="lx-field">
            <label className="lx-label" htmlFor="manual-desc">
              Mô tả chi tiết (Tối đa 2000 ký tự)
            </label>
            <textarea
              id="manual-desc"
              className="lx-textarea"
              maxLength={2000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Nhập mô tả nghi vấn lỗi do reviewer phát hiện..."
              disabled={isSubmitting || !hasPolicy || isLeaseExpired}
            />
            <span className="lx-hint" style={{ textAlign: 'right', fontSize: '11px' }}>
              {description.length} / 2000 ký tự
            </span>
          </div>

          <div className="lx-row" style={{ justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
            <button
              type="button"
              className="lx-btn lx-btn--ghost"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Hủy
            </button>
            <button
              type="submit"
              className="lx-btn lx-btn--primary"
              disabled={isSubmitting || !hasPolicy || isLeaseExpired}
            >
              {isSubmitting ? 'Đang tạo...' : 'Tạo issue'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
