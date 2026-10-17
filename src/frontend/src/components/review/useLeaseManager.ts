'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient } from '@/lib/api/client';
import { readErrorDetail } from '@/lib/api/errors';
import type { components } from '@/lib/api/contract';

type Lease = components['schemas']['Lease'];

export interface UseLeaseManagerOptions {
  frameId: number;
  initialLease: Lease | null;
  currentUserId?: number | null;
  enabled?: boolean;
  onExpired?: () => void;
  onConflict?: () => void;
  onLeaseUpdated?: (lease: Lease) => void;
  /**
   * Optional renewal threshold in seconds.
   * NOTE: Automatic lease renewal policy is pending PO approval (TBD-09 / T-044).
   * Without an explicitly supplied approved policy threshold, automatic renewal
   * is disabled and renewals are performed manually by user interaction.
   */
  renewThresholdSeconds?: number | null;
}

function computeLeaseState(
  frameId: number,
  currentUserId: number | null | undefined,
  lease: Lease | null
) {
  if (!lease) {
    return {
      validLease: null,
      isExpired: false,
      isHolderMismatch: false,
      leaseError: null,
      remainingSeconds: 0,
    };
  }

  // Cross-frame lease forbidden: lease.frame_id must match workspace frameId
  if (lease.frame_id !== frameId) {
    return {
      validLease: null,
      isExpired: true,
      isHolderMismatch: false,
      leaseError: 'Lease không khớp với frameId hiện tại (cross-frame lease forbidden).',
      remainingSeconds: 0,
    };
  }

  // Missing currentUserId can NEVER be treated as authorized holder
  if (currentUserId == null) {
    return {
      validLease: lease,
      isExpired: false,
      isHolderMismatch: true,
      leaseError: 'Thiếu thông tin người dùng: không thể xác thực quyền giữ lease.',
      remainingSeconds: 0,
    };
  }

  // Holder mismatch
  if (lease.holder_user_id !== currentUserId) {
    return {
      validLease: lease,
      isExpired: false,
      isHolderMismatch: true,
      leaseError: 'Lease thuộc về người dùng khác (holder mismatch). Quyền ghi bị khóa.',
      remainingSeconds: 0,
    };
  }

  // Validate initial expiry synchronously
  const expiresAtMs = new Date(lease.expires_at).getTime();
  if (!Number.isFinite(expiresAtMs) || expiresAtMs <= Date.now()) {
    return {
      validLease: lease,
      isExpired: true,
      isHolderMismatch: false,
      leaseError: !Number.isFinite(expiresAtMs)
        ? 'Thời hạn lease không hợp lệ (NaN/invalid date).'
        : 'Lease đã hết hạn ngay từ khi khởi tạo.',
      remainingSeconds: 0,
    };
  }
  const diff = Math.floor((expiresAtMs - Date.now()) / 1000);

  return {
    validLease: lease,
    isExpired: false,
    isHolderMismatch: false,
    leaseError: null,
    remainingSeconds: diff,
  };
}

export function useLeaseManager({
  frameId,
  initialLease,
  currentUserId,
  enabled = true,
  onExpired,
  onConflict,
  onLeaseUpdated,
  renewThresholdSeconds = null,
}: UseLeaseManagerOptions) {
  const contextKey = `${frameId}:${currentUserId ?? 'anon'}:${initialLease?.id ?? 'none'}`;
  const [prevContextKey, setPrevContextKey] = useState<string>(contextKey);

  const isMountedRef = useRef<boolean>(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const generationRef = useRef<number>(0);

  const initialComputed = computeLeaseState(frameId, currentUserId, initialLease);
  const [lease, setLease] = useState<Lease | null>(initialComputed.validLease);
  const [isExpired, setIsExpired] = useState<boolean>(initialComputed.isExpired);
  const [isHolderMismatch, setIsHolderMismatch] = useState<boolean>(initialComputed.isHolderMismatch);
  const [leaseError, setLeaseError] = useState<string | null>(initialComputed.leaseError);
  const [remainingSeconds, setRemainingSeconds] = useState<number>(initialComputed.remainingSeconds);
  const [isRenewing, setIsRenewing] = useState<boolean>(false);

  const contextRef = useRef({
    frameId,
    currentUserId,
    enabled,
    isExpired,
    isConflict: false,
  });

  // Synchronously resync state when frame, user, or initialLease context changes
  if (contextKey !== prevContextKey) {
    setPrevContextKey(contextKey);
    const updated = computeLeaseState(frameId, currentUserId, initialLease);
    setLease(updated.validLease);
    setIsExpired(updated.isExpired);
    setIsHolderMismatch(updated.isHolderMismatch);
    setLeaseError(updated.leaseError);
    setRemainingSeconds(updated.remainingSeconds);
    setIsRenewing(false);
  }

  const leaseRef = useRef<Lease | null>(lease);
  useEffect(() => {
    leaseRef.current = lease;
  }, [lease]);

  useEffect(() => {
    generationRef.current++;
    contextRef.current.isConflict = false;
  }, [contextKey]);

  useEffect(() => {
    contextRef.current = {
      frameId,
      currentUserId,
      enabled,
      isExpired,
      isConflict: contextRef.current.isConflict,
    };
  }, [frameId, currentUserId, enabled, isExpired]);

  const renewLease = useCallback(async () => {
    if (!enabled || !leaseRef.current || isExpired || isHolderMismatch || isRenewing) return;
    const reqFrameId = frameId;
    const reqUserId = currentUserId;
    const reqLeaseId = leaseRef.current.id;
    const reqGen = generationRef.current;

    setIsRenewing(true);

    try {
      const { data, error, response } = await apiClient.POST('/api/leases/{id}/renew/', {
        params: { path: { id: reqLeaseId } },
      });

      // Discard in-flight response if unmounted, generation changed, disabled, conflicted, or context switched
      if (
        !isMountedRef.current ||
        reqGen !== generationRef.current ||
        !contextRef.current.enabled ||
        contextRef.current.isConflict ||
        contextRef.current.frameId !== reqFrameId ||
        contextRef.current.currentUserId !== reqUserId ||
        leaseRef.current?.id !== reqLeaseId
      ) {
        return;
      }

      if (response.status === 409) {
        contextRef.current.isConflict = true;
        setIsExpired(true);
        setLeaseError('Xung đột lease (409 Conflict): Quyền giữ frame đã hết hạn hoặc được cấp cho người khác.');
        onConflict?.();
        onExpired?.();
        return;
      }

      if (response.status === 403) {
        setLeaseError('Truy cập bị từ chối khi gia hạn lease (403 Forbidden).');
        return;
      }

      if (error || !data) {
        const detail = readErrorDetail(error);
        setLeaseError(detail?.message || 'Lỗi mạng khi gia hạn lease.');
        return;
      }

      // Revalidate returned lease id, frame, holder, and expiry
      const returnedExpiresAtMs = new Date(data.expires_at).getTime();
      if (
        data.id !== reqLeaseId ||
        data.frame_id !== reqFrameId ||
        data.holder_user_id !== reqUserId ||
        !Number.isFinite(returnedExpiresAtMs) ||
        returnedExpiresAtMs <= Date.now()
      ) {
        setIsExpired(true);
        setLeaseError('Phản hồi gia hạn lease không hợp lệ hoặc đã hết hạn.');
        return;
      }

      // Successful renew
      setLease(data);
      setIsExpired(false);
      setLeaseError(null);
      const diff = Math.floor((returnedExpiresAtMs - Date.now()) / 1000);
      setRemainingSeconds(Math.max(0, diff));
      onLeaseUpdated?.(data);
    } catch {
      if (isMountedRef.current && reqGen === generationRef.current) {
        setLeaseError('Lỗi kết nối mạng khi gia hạn lease.');
      }
    } finally {
      if (isMountedRef.current && reqGen === generationRef.current) {
        setIsRenewing(false);
      }
    }
  }, [enabled, frameId, currentUserId, isExpired, isHolderMismatch, isRenewing, onConflict, onExpired, onLeaseUpdated]);

  // Check remaining seconds and auto-renew timer
  // Automatically stops when !enabled, expired, holder mismatched, or no lease
  useEffect(() => {
    if (!enabled || !lease || isExpired || isHolderMismatch) return;

    const interval = setInterval(() => {
      const currentExpiryMs = new Date(lease.expires_at).getTime();
      if (!Number.isFinite(currentExpiryMs) || currentExpiryMs <= Date.now()) {
        setIsExpired(true);
        setRemainingSeconds(0);
        setLeaseError('Lease đã hết hạn.');
        onExpired?.();
      } else {
        const diff = Math.floor((currentExpiryMs - Date.now()) / 1000);
        setRemainingSeconds(diff);
        if (
          renewThresholdSeconds != null &&
          Number.isFinite(renewThresholdSeconds) &&
          renewThresholdSeconds > 0 &&
          diff <= renewThresholdSeconds &&
          !isRenewing &&
          enabled
        ) {
          renewLease();
        }
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [enabled, lease, isExpired, isHolderMismatch, renewThresholdSeconds, isRenewing, renewLease, onExpired]);

  return {
    lease,
    isExpired: isExpired || isHolderMismatch,
    isHolderMismatch,
    isRenewing,
    leaseError,
    remainingSeconds,
    renewLease,
  };
}
