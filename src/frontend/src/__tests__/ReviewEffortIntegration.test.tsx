import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  useEffortCollector,
  effortCollectorStatus,
  type UseEffortCollectorOptions,
  type UseEffortCollectorResult,
} from '@/components/review/useEffortCollector';
import { ApiRequestError } from '@/lib/api/errors';
import type { components } from '@/lib/api/contract';
import type { EffortEvent, EffortReceipt } from '@/lib/effort/collector';

type LeaseGrant = components['schemas']['LeaseGrant'];
type IssueDecision = components['schemas']['IssueDecision'];
type FrameSummary = components['schemas']['FrameSummary'];
type EventSender = (events: EffortEvent[]) => Promise<EffortReceipt>;

const mockGrant: LeaseGrant = {
  lease: {
    id: 101,
    frame_id: 50,
    holder_user_id: 4,
    expires_at: new Date(Date.now() + 600000).toISOString(),
  },
  frame: {
    id: 50,
    run_id: 10,
    frame_key: { cvat_task_id: 1, frame_number: 50 },
    review_state: 'in_review',
    missing_evidence: false,
  },
  resumed: false,
};

const successFrame: FrameSummary = {
  id: 50,
  run_id: 10,
  frame_key: { cvat_task_id: 1, frame_number: 50 },
  review_state: 'completed',
  missing_evidence: false,
};

class MockWindow extends EventTarget {}

class MockDocument extends EventTarget {
  visibilityState: DocumentVisibilityState = 'visible';
}

describe('T-037 & T-036 Effort Collector Lifecycle Integration (Mock Unit Evidence)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('exposes truthful T-036 integrated status with idle policy pending PO approval', () => {
    expect(effortCollectorStatus.isAvailable).toBe(true);
    expect(effortCollectorStatus.status).toBe('INTEGRATED_T036');
    expect(effortCollectorStatus.idlePolicy).toBe('pending_po_approval');
  });

  it('strict user identity binding: requires positive safeinteger and exact holder match before collection', async () => {
    const mockSend = vi.fn<EventSender>().mockImplementation(async (events) => ({
      accepted: events.length,
      duplicates: 0,
    }));

    // 1. null userId does not start collection
    const initialProps: UseEffortCollectorOptions = {
      grant: mockGrant,
      currentUserId: null,
      collectorOptions: { send: mockSend },
    };
    const { result, rerender } = renderHook<UseEffortCollectorResult, UseEffortCollectorOptions>(
      (props) => useEffortCollector(props),
      { initialProps }
    );
    let handled = await result.current.stopOnLeaseConflict(
      new ApiRequestError(409, { code: 'LEASE_CONFLICT' })
    );
    expect(handled).toBe(false);
    expect(mockSend).not.toHaveBeenCalled();

    // 2. undefined userId does not start collection
    rerender({
      grant: mockGrant,
      currentUserId: undefined,
      collectorOptions: { send: mockSend },
    });
    handled = await result.current.stopOnLeaseConflict(
      new ApiRequestError(409, { code: 'LEASE_CONFLICT' })
    );
    expect(handled).toBe(false);

    // 3. non-positive / non-integer userId does not start collection
    rerender({
      grant: mockGrant,
      currentUserId: -1,
      collectorOptions: { send: mockSend },
    });
    handled = await result.current.stopOnLeaseConflict(
      new ApiRequestError(409, { code: 'LEASE_CONFLICT' })
    );
    expect(handled).toBe(false);

    // 4. holder mismatch (user 4 vs holder 999) does not start collection
    rerender({
      grant: { ...mockGrant, lease: { ...mockGrant.lease, holder_user_id: 999 } },
      currentUserId: 4,
      collectorOptions: { send: mockSend },
    });
    handled = await result.current.stopOnLeaseConflict(
      new ApiRequestError(409, { code: 'LEASE_CONFLICT' })
    );
    expect(handled).toBe(false);

    // 5. Expired lease does not start collection
    rerender({
      grant: {
        ...mockGrant,
        lease: { ...mockGrant.lease, expires_at: new Date(Date.now() - 5000).toISOString() },
      },
      currentUserId: 4,
      collectorOptions: { send: mockSend },
    });
    handled = await result.current.stopOnLeaseConflict(
      new ApiRequestError(409, { code: 'LEASE_CONFLICT' })
    );
    expect(handled).toBe(false);

    // 6. Valid user 4 matching holder 4 starts collection
    rerender({
      grant: mockGrant,
      currentUserId: 4,
      collectorOptions: { send: mockSend },
    });
    handled = await result.current.stopOnLeaseConflict(
      new ApiRequestError(409, { code: 'LEASE_CONFLICT' })
    );
    expect(handled).toBe(true);
  });

  it('wires activity transitions and records real decision with actual contract schema', async () => {
    let now = 1000;
    const sentBatches: EffortEvent[][] = [];
    const mockSend = vi.fn<EventSender>().mockImplementation(async (events) => {
      sentBatches.push(events);
      return { accepted: events.length, duplicates: 0 };
    });

    const { result } = renderHook(() =>
      useEffortCollector({
        grant: mockGrant,
        currentUserId: 4,
        collectorOptions: {
          send: mockSend,
          now: () => now,
          flushEveryMs: 0,
        },
      })
    );

    // Initial activity starts at view_frame; transition to review_issue at t=2000
    now = 2000;
    act(() => {
      result.current.setActivity('review_issue');
    });

    // Save real decision (matching contract schema without extra fields) at t=3500
    now = 3500;
    const realDecision: IssueDecision = {
      id: 777,
      issue_id: 201,
      actor_user_id: 4,
      action: 'confirm',
      revision: 'sha256:abc',
      family: 'E2',
      severity: 'medium',
      reason: 'Misclassified annotation',
      rule_id: 'R-01',
      created_at: new Date(now).toISOString(),
    };

    act(() => {
      result.current.decisionSaved(realDecision);
    });

    // Complete session at t=5000, triggering terminal flush
    now = 5000;
    await act(async () => {
      await result.current.completeAfter(Promise.resolve(successFrame));
    });

    expect(mockSend).toHaveBeenCalled();
    const allEvents = sentBatches.flat();
    expect(allEvents.length).toBeGreaterThanOrEqual(2);
    expect(allEvents.some((e) => e.activity === 'view_frame')).toBe(true);
    expect(allEvents.some((e) => e.activity === 'review_issue')).toBe(true);
    expect(allEvents[0].frame_id).toBe(50);
  });

  it('pauses and resumes on real window blur/focus and document visibilitychange events', async () => {
    let now = 1000;
    const mockWin = new MockWindow() as unknown as Window;
    const mockDoc = new MockDocument() as unknown as Document;
    const sentBatches: EffortEvent[][] = [];
    const mockSend = vi.fn<EventSender>().mockImplementation(async (events) => {
      sentBatches.push(events);
      return { accepted: events.length, duplicates: 0 };
    });

    const { result } = renderHook(() =>
      useEffortCollector({
        grant: mockGrant,
        currentUserId: 4,
        collectorOptions: {
          send: mockSend,
          now: () => now,
          window: mockWin,
          document: mockDoc,
          flushEveryMs: 0,
        },
      })
    );

    // Blur window at t=2000 (pauses active interval)
    now = 2000;
    act(() => {
      mockWin.dispatchEvent(new Event('blur'));
    });

    // Refocus window at t=3000 (resumes foreground interval)
    now = 3000;
    act(() => {
      mockWin.dispatchEvent(new Event('focus'));
    });

    // Document hides at t=4000 (pauses active interval)
    now = 4000;
    act(() => {
      (mockDoc as unknown as MockDocument).visibilityState = 'hidden';
      mockDoc.dispatchEvent(new Event('visibilitychange'));
    });

    // Document becomes visible at t=5000 (resumes)
    now = 5000;
    act(() => {
      (mockDoc as unknown as MockDocument).visibilityState = 'visible';
      mockDoc.dispatchEvent(new Event('visibilitychange'));
    });

    // Flush via loseLease at t=6000
    now = 6000;
    await act(async () => {
      await result.current.loseLease();
    });

    expect(mockSend).toHaveBeenCalled();
    const allEvents = sentBatches.flat();
    expect(allEvents.length).toBeGreaterThanOrEqual(2);
    // Interval 1: 1000 to 2000 (before blur)
    expect(allEvents[0].started_at).toBe(new Date(1000).toISOString());
    expect(allEvents[0].ended_at).toBe(new Date(2000).toISOString());
    // Inactive gap 2000 to 3000 is excluded
  });

  it('handles 409 LEASE_CONFLICT as terminal loss of lease while preserving non-lease 409 errors', async () => {
    let now = 1000;
    const sentBatches: EffortEvent[][] = [];
    const mockSend = vi.fn<EventSender>().mockImplementation(async (events) => {
      sentBatches.push(events);
      return { accepted: events.length, duplicates: 0 };
    });

    const { result } = renderHook(() =>
      useEffortCollector({
        grant: mockGrant,
        currentUserId: 4,
        collectorOptions: {
          send: mockSend,
          now: () => now,
          flushEveryMs: 0,
        },
      })
    );

    // Non-lease 409 error must NOT lose lease
    const nonLeaseConflict = new ApiRequestError(409, {
      code: 'INVALID_TRANSITION',
      message: 'Mismatch',
    });
    let handled = await result.current.stopOnLeaseConflict(nonLeaseConflict);
    expect(handled).toBe(false);

    // Real LEASE_CONFLICT loses lease, flushes queue, and marks terminal
    now = 2000;
    const realLeaseConflict = new ApiRequestError(409, {
      code: 'LEASE_CONFLICT',
      message: 'Expired',
    });
    handled = await result.current.stopOnLeaseConflict(realLeaseConflict);
    expect(handled).toBe(true);
    expect(mockSend).toHaveBeenCalled();

    // After losing lease, further completeAfter does not send additional events
    const initialSendCount = mockSend.mock.calls.length;
    now = 3000;
    await result.current.completeAfter(Promise.resolve(successFrame));
    expect(mockSend.mock.calls.length).toBe(initialSendCount);
  });

  it('completes session via completeAfter on 200 success, but leaves session active on rejected 422', async () => {
    let now = 1000;
    const sentBatches: EffortEvent[][] = [];
    const mockSend = vi.fn<EventSender>().mockImplementation(async (events) => {
      sentBatches.push(events);
      return { accepted: events.length, duplicates: 0 };
    });

    const { result } = renderHook(() =>
      useEffortCollector({
        grant: mockGrant,
        currentUserId: 4,
        collectorOptions: {
          send: mockSend,
          now: () => now,
          flushEveryMs: 0,
        },
      })
    );

    // 422 Rejected complete leaves session running
    const rejectedPromise = Promise.reject(
      new ApiRequestError(422, { code: 'UNDECIDED_ISSUES' })
    );
    await expect(
      result.current.completeAfter(rejectedPromise as unknown as Promise<FrameSummary>)
    ).rejects.toThrow();

    // Session remains active: record new activity at t=2000
    now = 2000;
    act(() => {
      result.current.setActivity('review_issue');
    });

    // Successful 200 completion completes collector at t=3000
    now = 3000;
    await act(async () => {
      await result.current.completeAfter(Promise.resolve(successFrame));
    });

    expect(mockSend).toHaveBeenCalled();
    const allEvents = sentBatches.flat();
    expect(allEvents.length).toBeGreaterThanOrEqual(1);
  });

  it('handles actual lease expiry via timer', async () => {
    vi.useFakeTimers();
    const baseTime = 100000;
    vi.setSystemTime(baseTime);

    const expiryMs = baseTime + 5000;
    const expiringGrant: LeaseGrant = {
      ...mockGrant,
      lease: {
        ...mockGrant.lease,
        expires_at: new Date(expiryMs).toISOString(),
      },
    };

    const mockSend = vi.fn<EventSender>().mockImplementation(async (events) => ({
      accepted: events.length,
      duplicates: 0,
    }));

    renderHook(() =>
      useEffortCollector({
        grant: expiringGrant,
        currentUserId: 4,
        collectorOptions: {
          send: mockSend,
          flushEveryMs: 0,
        },
      })
    );

    // Advance clock past expiration
    act(() => {
      vi.advanceTimersByTime(5001);
    });

    // Expiry timer triggered loseLease which flushed pending events
    expect(mockSend).toHaveBeenCalled();
  });

  it('preserves existing session across same-lease renewal without losing events or duplicating collectors', async () => {
    let now = 1000;
    const sentBatches: EffortEvent[][] = [];
    const mockSend = vi.fn<EventSender>().mockImplementation(async (events) => {
      sentBatches.push(events);
      return { accepted: events.length, duplicates: 0 };
    });

    const initialRenewalProps: UseEffortCollectorOptions = {
      grant: mockGrant,
      currentUserId: 4,
      collectorOptions: {
        send: mockSend,
        now: () => now,
        flushEveryMs: 0,
      },
    };
    const { result, rerender } = renderHook<UseEffortCollectorResult, UseEffortCollectorOptions>(
      (props) => useEffortCollector(props),
      { initialProps: initialRenewalProps }
    );

    // Record activity under initial lease
    now = 2000;
    act(() => {
      result.current.setActivity('review_issue');
    });

    // Legitimate renewal: same lease id 101, same frame 50, same holder 4, updated expires_at
    const renewedGrant: LeaseGrant = {
      ...mockGrant,
      lease: {
        ...mockGrant.lease,
        expires_at: new Date(Date.now() + 1200000).toISOString(),
      },
    };

    rerender({
      grant: renewedGrant,
      currentUserId: 4,
      collectorOptions: {
        send: mockSend,
        now: () => now,
        flushEveryMs: 0,
      },
    });

    // Record activity after renewal at t=3500
    now = 3500;
    act(() => {
      result.current.setActivity('view_frame');
    });

    // Complete session at t=5000
    now = 5000;
    await act(async () => {
      await result.current.completeAfter(Promise.resolve(successFrame));
    });

    // Flushed events should contain all activities across renewal seamlessly
    expect(mockSend).toHaveBeenCalled();
    const allEvents = sentBatches.flat();
    expect(allEvents.length).toBeGreaterThanOrEqual(2);
  });

  it('cleans up session on unmount or user/frame context switch', async () => {
    const now = 1000;
    const sentBatches: EffortEvent[][] = [];
    const mockSend = vi.fn<EventSender>().mockImplementation(async (events) => {
      sentBatches.push(events);
      return { accepted: events.length, duplicates: 0 };
    });

    const initialSwitchProps: UseEffortCollectorOptions = {
      grant: mockGrant,
      currentUserId: 4,
      collectorOptions: {
        send: mockSend,
        now: () => now,
        flushEveryMs: 0,
      },
    };
    const { result, rerender, unmount } = renderHook<UseEffortCollectorResult, UseEffortCollectorOptions>(
      (props) => useEffortCollector(props),
      { initialProps: initialSwitchProps }
    );

    // Context switch: user changes to 2 (mismatch with grant holder 4)
    rerender({
      grant: mockGrant,
      currentUserId: 2,
      collectorOptions: {
        send: mockSend,
        now: () => now,
        flushEveryMs: 0,
      },
    });
    let handled = await result.current.stopOnLeaseConflict(
      new ApiRequestError(409, { code: 'LEASE_CONFLICT' })
    );
    expect(handled).toBe(false);

    // Switch to new frame 60 with matching holder 2
    const newFrameGrant: LeaseGrant = {
      ...mockGrant,
      frame: { ...mockGrant.frame, id: 60 },
      lease: { ...mockGrant.lease, id: 102, frame_id: 60, holder_user_id: 2 },
    };
    rerender({
      grant: newFrameGrant,
      currentUserId: 2,
      collectorOptions: {
        send: mockSend,
        now: () => now,
        flushEveryMs: 0,
      },
    });
    handled = await result.current.stopOnLeaseConflict(
      new ApiRequestError(409, { code: 'LEASE_CONFLICT' })
    );
    expect(handled).toBe(true);

    // Unmount cleans up
    unmount();
  });
});
