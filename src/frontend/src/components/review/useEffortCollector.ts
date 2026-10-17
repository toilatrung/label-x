'use client';

import { useEffect, useRef, useCallback } from 'react';
import type { components } from '@/lib/api/contract';
import { ReviewEffortSession } from '@/lib/effort/reviewSession';
import type { EffortActivity, EffortCollectorOptions } from '@/lib/effort/collector';

type LeaseGrant = components['schemas']['LeaseGrant'];
type IssueDecision = components['schemas']['IssueDecision'];
type FrameSummary = components['schemas']['FrameSummary'];

export interface EffortCollectorStatus {
  isAvailable: boolean;
  status: 'INTEGRATED_T036';
  dependencyIssue: 'https://github.com/toilatrung/label-x/issues/103';
  idlePolicy: 'pending_po_approval' | 'configured';
  reason: string;
}

export const effortCollectorStatus: EffortCollectorStatus = {
  isAvailable: true,
  status: 'INTEGRATED_T036',
  dependencyIssue: 'https://github.com/toilatrung/label-x/issues/103',
  idlePolicy: 'pending_po_approval',
  reason:
    'Module T-036 (PR133) đã tích hợp vào baseline. Ngưỡng idle cutoff đang chờ PO phê duyệt cấu hình (TBD-09); idleAfterMs đặt là null.',
};

export interface UseEffortCollectorOptions {
  grant: LeaseGrant | null;
  currentUserId?: number | null;
  enabled?: boolean;
  collectorOptions?: Partial<EffortCollectorOptions>;
}

export interface UseEffortCollectorResult {
  setActivity: (activity: EffortActivity) => void;
  decisionSaved: (decision: IssueDecision) => void;
  completeAfter: (request: Promise<FrameSummary>) => Promise<FrameSummary>;
  stopOnLeaseConflict: (error: unknown) => Promise<boolean>;
  loseLease: () => Promise<void>;
  pause: () => void;
  resume: () => void;
}

function isValidUserId(userId: unknown): userId is number {
  return typeof userId === 'number' && Number.isSafeInteger(userId) && userId > 0;
}

function getSessionStorage(): Storage | undefined {
  if (typeof window === 'undefined') return undefined;
  try {
    const s = window.sessionStorage;
    const testKey = '__labelx_probe__';
    s.setItem(testKey, '1');
    s.removeItem(testKey);
    return s;
  } catch {
    return undefined;
  }
}

function createSafeStorage(underlying?: Storage): Pick<Storage, 'getItem' | 'setItem'> | undefined {
  if (!underlying) return undefined;
  return {
    getItem(key: string): string | null {
      try {
        return underlying.getItem(key);
      } catch {
        return null;
      }
    },
    setItem(key: string, value: string): void {
      try {
        underlying.setItem(key, value);
      } catch {
        // QuotaExceededError or security exceptions swallowed safely
      }
    },
  };
}

export function useEffortCollector({
  grant,
  currentUserId,
  enabled = true,
  collectorOptions,
}: UseEffortCollectorOptions): UseEffortCollectorResult {
  const sessionRef = useRef<ReviewEffortSession | null>(null);
  const activeGrantKeyRef = useRef<string | null>(null);

  const isValidUser = isValidUserId(currentUserId);
  const isGrantStructurallyValid = Boolean(
    enabled &&
      isValidUser &&
      grant &&
      grant.frame &&
      grant.lease &&
      grant.lease.frame_id === grant.frame.id &&
      grant.lease.holder_user_id === currentUserId &&
      Number.isFinite(new Date(grant.lease.expires_at).getTime())
  );

  // Identity key for the current grant; stays identical across legitimate renewals of same lease
  const grantIdentityKey =
    isGrantStructurallyValid && grant && isValidUser
      ? `${grant.frame.id}:${grant.frame.run_id ?? 0}:${grant.lease.id}:${grant.lease.holder_user_id}`
      : null;

  // Session lifecycle management
  useEffect(() => {
    // If context changed (different grant identity or invalid/disabled), destroy previous session
    if (activeGrantKeyRef.current !== grantIdentityKey) {
      if (sessionRef.current) {
        sessionRef.current.destroy();
        sessionRef.current = null;
      }
      activeGrantKeyRef.current = null;

      if (isGrantStructurallyValid && grant && isValidUser) {
        // Expiry check evaluated inside effect lifecycle to preserve render purity
        const now = collectorOptions?.now ? collectorOptions.now() : Date.now();
        const expiry = new Date(grant.lease.expires_at).getTime();
        if (expiry <= now) {
          // Lease already expired; do not start session
          return;
        }

        // Safe per-user storage key (no fallback to global storage)
        const safeStorageKey = `labelx:pending-effort-events:u${currentUserId}:v1`;
        const storageInstance =
          collectorOptions?.storage ?? createSafeStorage(getSessionStorage());

        const session = new ReviewEffortSession({
          idleAfterMs: null, // explicit null = TBD per T-036 specification (TBD-09)
          window:
            collectorOptions?.window ?? (typeof window !== 'undefined' ? window : undefined),
          document:
            collectorOptions?.document ?? (typeof document !== 'undefined' ? document : undefined),
          storage: storageInstance,
          storageKey: safeStorageKey,
          ...collectorOptions,
        });

        session.start(grant);
        sessionRef.current = session;
        activeGrantKeyRef.current = grantIdentityKey;
      }
    }
  }, [grantIdentityKey, isGrantStructurallyValid, grant, isValidUser, currentUserId, collectorOptions]);

  // Terminal loss of lease upon actual expiry of current lease
  useEffect(() => {
    if (!isGrantStructurallyValid || !grant || !grantIdentityKey) return;
    const now = collectorOptions?.now ? collectorOptions.now() : Date.now();
    const expiry = new Date(grant.lease.expires_at).getTime();
    const remainingMs = expiry - now;

    if (remainingMs <= 0) {
      if (sessionRef.current) {
        void sessionRef.current.collector.loseLease();
      }
      return;
    }

    // Browsers and Node clamp a timeout to a signed 32-bit integer. Tests can
    // intentionally pin `now` far in the past, and a long-lived lease from an
    // API fixture must not overflow into an immediate one-millisecond timer.
    const maxTimeoutMs = 2_147_483_647;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const scheduleExpiry = () => {
      const currentNow = collectorOptions?.now ? collectorOptions.now() : Date.now();
      const currentRemainingMs = expiry - currentNow;
      if (currentRemainingMs <= 0) {
        if (sessionRef.current) {
          void sessionRef.current.collector.loseLease();
        }
        return;
      }
      timer = setTimeout(scheduleExpiry, Math.min(currentRemainingMs, maxTimeoutMs));
    };
    scheduleExpiry();

    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [isGrantStructurallyValid, grant, grantIdentityKey, collectorOptions]);

  // Clean up on component unmount
  useEffect(() => {
    return () => {
      if (sessionRef.current) {
        sessionRef.current.destroy();
        sessionRef.current = null;
        activeGrantKeyRef.current = null;
      }
    };
  }, []);

  const setActivity = useCallback((activity: EffortActivity) => {
    try {
      sessionRef.current?.setActivity(activity);
    } catch {
      // Ignored if session has not started or is terminal
    }
  }, []);

  const decisionSaved = useCallback((decision: IssueDecision) => {
    try {
      sessionRef.current?.decisionSaved(decision);
    } catch {
      // Ignored if session has not started or is terminal
    }
  }, []);

  const completeAfter = useCallback(
    async (request: Promise<FrameSummary>): Promise<FrameSummary> => {
      if (sessionRef.current) {
        return sessionRef.current.completeAfter(request);
      }
      return request;
    },
    []
  );

  const stopOnLeaseConflict = useCallback(async (error: unknown): Promise<boolean> => {
    if (sessionRef.current) {
      return sessionRef.current.stopOnLeaseConflict(error);
    }
    return false;
  }, []);

  const loseLease = useCallback(async (): Promise<void> => {
    if (sessionRef.current) {
      await sessionRef.current.collector.loseLease();
    }
  }, []);

  const pause = useCallback(() => {
    sessionRef.current?.collector.pause();
  }, []);

  const resume = useCallback(() => {
    sessionRef.current?.collector.resume();
  }, []);

  return {
    setActivity,
    decisionSaved,
    completeAfter,
    stopOnLeaseConflict,
    loseLease,
    pause,
    resume,
  };
}
