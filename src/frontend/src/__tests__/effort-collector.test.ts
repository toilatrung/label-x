import { afterEach, describe, expect, it, vi } from 'vitest';

import { EffortCollector, type EffortEvent } from '@/lib/effort/collector';
import { ReviewEffortSession } from '@/lib/effort/reviewSession';
import { ApiRequestError } from '@/lib/api/errors';
import type { components } from '@/lib/api/contract';

afterEach(() => vi.useRealTimers());

function ids() {
  let value = 0;
  return () => `00000000-0000-4000-8000-${String(++value).padStart(12, '0')}`;
}

describe('EffortCollector', () => {
  it('keeps the same client ids and batch when a network error is retried', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-11T02:00:00Z'));
    const batches: EffortEvent[][] = [];
    const send = vi.fn(async (events: EffortEvent[]) => {
      batches.push(structuredClone(events));
      if (batches.length === 1) throw new TypeError('network failed');
      return { accepted: events.length, duplicates: 0 };
    });
    const collector = new EffortCollector({
      send,
      idleAfterMs: null,
      retryAfterMs: 100,
      flushEveryMs: 0,
      makeId: ids(),
    });
    collector.begin(340, 'review_issue');
    vi.advanceTimersByTime(2_000);
    collector.pause();

    await collector.flush();
    expect(collector.pendingEvents()).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(100);

    expect(send).toHaveBeenCalledTimes(2);
    expect(batches[1]).toEqual(batches[0]);
    expect(collector.pendingEvents()).toHaveLength(0);
    collector.destroy();
  });

  it('excludes idle time and starts a new interval on later activity', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-11T02:00:00Z'));
    const collector = new EffortCollector({
      idleAfterMs: 1_000,
      flushEveryMs: 0,
      makeId: ids(),
      send: async () => ({ accepted: 0, duplicates: 0 }),
    });
    collector.begin(340, 'view_frame');
    vi.advanceTimersByTime(400);
    collector.recordActivity();
    vi.advanceTimersByTime(1_000);
    expect(collector.pendingEvents()[0]).toMatchObject({
      started_at: '2026-10-11T02:00:00.000Z',
      ended_at: '2026-10-11T02:00:00.400Z',
    });

    vi.advanceTimersByTime(5_000);
    collector.recordActivity();
    vi.advanceTimersByTime(250);
    collector.pause();
    expect(collector.pendingEvents()[1]).toMatchObject({
      started_at: '2026-10-11T02:00:06.400Z',
      ended_at: '2026-10-11T02:00:06.650Z',
    });
    collector.destroy();
  });

  it('stops on blur, pause, complete and lease loss', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-11T02:00:00Z'));
    const sent: EffortEvent[] = [];
    const collector = new EffortCollector({
      idleAfterMs: null,
      flushEveryMs: 0,
      makeId: ids(),
      window,
      document,
      send: async (events) => {
        sent.push(...events);
        return { accepted: events.length, duplicates: 0 };
      },
    });
    collector.begin(340, 'review_issue');
    vi.advanceTimersByTime(100);
    window.dispatchEvent(new Event('blur'));
    vi.advanceTimersByTime(5_000);
    collector.resume();
    expect(collector.pendingEvents()).toHaveLength(1);

    window.dispatchEvent(new Event('focus'));
    vi.advanceTimersByTime(100);
    await collector.complete();
    expect(sent).toHaveLength(2);
    expect(() => collector.begin(340, 'review_issue')).toThrow(/complete|lease/);
    collector.destroy();

    const lost = new EffortCollector({ idleAfterMs: null, flushEveryMs: 0, makeId: ids(), send: async () => ({ accepted: 1, duplicates: 0 }) });
    lost.begin(340, 'review_issue');
    vi.advanceTimersByTime(100);
    await lost.loseLease();
    expect(() => lost.begin(340, 'review_issue')).toThrow(/complete|lease/);
    lost.destroy();
  });

  it('persists unsent events for a later collector instance', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-11T02:00:00Z'));
    const first = new EffortCollector({ idleAfterMs: null, flushEveryMs: 0, makeId: ids(), storage: localStorage, send: async () => ({ accepted: 0, duplicates: 0 }) });
    first.begin(340, 'adjudicate');
    vi.advanceTimersByTime(100);
    first.pause();
    first.destroy();

    const restored = new EffortCollector({ idleAfterMs: null, flushEveryMs: 0, storage: localStorage, send: async () => ({ accepted: 0, duplicates: 0 }) });
    expect(restored.pendingEvents()).toHaveLength(1);
    restored.destroy();
  });
});

describe('ReviewEffortSession', () => {
  const grant = {
    lease: { id: 9, frame_id: 340, holder_user_id: 7, expires_at: '2026-10-11T02:05:00Z' },
    frame: { id: 340 },
  } as components['schemas']['LeaseGrant'];

  it('uses the real lease frame and stops only after a successful T-035 complete', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-11T02:00:00Z'));
    const sent: EffortEvent[] = [];
    const session = new ReviewEffortSession({
      idleAfterMs: null,
      flushEveryMs: 0,
      makeId: ids(),
      send: async (events) => {
        sent.push(...events);
        return { accepted: events.length, duplicates: 0 };
      },
    });
    session.start(grant);
    vi.advanceTimersByTime(100);
    session.setActivity('review_issue');
    vi.advanceTimersByTime(200);
    session.decisionSaved({ id: 12 } as components['schemas']['IssueDecision']);
    vi.advanceTimersByTime(100);

    await expect(
      session.completeAfter(Promise.reject(new Error('issues remain')))
    ).rejects.toThrow('issues remain');
    session.collector.recordActivity();
    vi.advanceTimersByTime(100);
    await session.completeAfter(Promise.resolve({ id: 340 } as components['schemas']['FrameSummary']));

    expect(sent.map((event) => [event.frame_id, event.activity])).toEqual([
      [340, 'view_frame'],
      [340, 'review_issue'],
      [340, 'view_frame'],
    ]);
    expect(() => session.collector.begin(340, 'view_frame')).toThrow(/complete|lease/);
    session.destroy();
  });

  it('stops collection when the T-033 lease endpoint reports a conflict', async () => {
    vi.useFakeTimers();
    const session = new ReviewEffortSession({
      idleAfterMs: null,
      flushEveryMs: 0,
      makeId: ids(),
      send: async (events) => ({ accepted: events.length, duplicates: 0 }),
    });
    session.start(grant);
    vi.advanceTimersByTime(100);
    const stopped = await session.stopOnLeaseConflict(
      new ApiRequestError(409, { code: 'LEASE_CONFLICT' })
    );
    expect(stopped).toBe(true);
    expect(() => session.collector.begin(340, 'view_frame')).toThrow(/complete|lease/);
    session.destroy();
  });
});
