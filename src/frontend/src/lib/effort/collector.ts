import type { components } from '@/lib/api/contract';
import { apiClient, ApiRequestError } from '@/lib/api/client';

export type EffortEvent = components['schemas']['EffortEvent'];
export type EffortActivity = EffortEvent['activity'];
export type EffortReceipt = components['schemas']['EffortEventReceipt'];

export async function sendEffortEvents(events: EffortEvent[]): Promise<EffortReceipt> {
  const result = await apiClient.POST('/api/effort-events/', { body: { events } });
  if (result.error || !result.data) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}

type ActiveContext = { frameId: number; activity: EffortActivity };
type EventSender = (events: EffortEvent[]) => Promise<EffortReceipt>;

export interface EffortCollectorOptions {
  send?: EventSender;
  idleAfterMs: number | null;
  batchSize?: number;
  flushEveryMs?: number;
  retryAfterMs?: number;
  now?: () => number;
  makeId?: () => string;
  storage?: Pick<Storage, 'getItem' | 'setItem'>;
  storageKey?: string;
  window?: Window;
  document?: Document;
}

const DEFAULT_STORAGE_KEY = 'labelx:pending-effort-events:v1';

/**
 * Collects mutually-exclusive activity intervals and retries the exact same UUID batch.
 * `idleAfterMs=null` deliberately means “TBD, do not invent a threshold”.
 */
export class EffortCollector {
  private readonly send: EventSender;
  private readonly idleAfterMs: number | null;
  private readonly batchSize: number;
  private readonly retryAfterMs: number;
  private readonly now: () => number;
  private readonly makeId: () => string;
  private readonly storage?: Pick<Storage, 'getItem' | 'setItem'>;
  private readonly storageKey: string;
  private readonly targetWindow?: Window;
  private readonly targetDocument?: Document;
  private queue: EffortEvent[] = [];
  private context: ActiveContext | null = null;
  private activeStartedAt: number | null = null;
  private lastActivityAt: number | null = null;
  private focused = true;
  private paused = true;
  private terminal = false;
  private idleTimer: ReturnType<typeof setTimeout> | null = null;
  private flushTimer: ReturnType<typeof setInterval> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private inFlight: Promise<void> | null = null;

  constructor(options: EffortCollectorOptions) {
    if (options.idleAfterMs !== null && options.idleAfterMs <= 0) {
      throw new Error('idleAfterMs must be null or greater than zero');
    }
    this.send = options.send ?? sendEffortEvents;
    this.idleAfterMs = options.idleAfterMs;
    this.batchSize = options.batchSize ?? 20;
    this.retryAfterMs = options.retryAfterMs ?? 1_000;
    this.now = options.now ?? Date.now;
    this.makeId = options.makeId ?? (() => crypto.randomUUID());
    this.storage = options.storage;
    this.storageKey = options.storageKey ?? DEFAULT_STORAGE_KEY;
    this.targetWindow = options.window;
    this.targetDocument = options.document;
    this.restoreQueue();
    this.targetWindow?.addEventListener('blur', this.onBlur);
    this.targetWindow?.addEventListener('focus', this.onFocus);
    this.targetWindow?.addEventListener('pointerdown', this.onActivity);
    this.targetWindow?.addEventListener('keydown', this.onActivity);
    this.targetDocument?.addEventListener('visibilitychange', this.onVisibilityChange);
    const flushEveryMs = options.flushEveryMs ?? 5_000;
    if (flushEveryMs > 0) this.flushTimer = setInterval(() => void this.flush(), flushEveryMs);
  }

  begin(frameId: number, activity: EffortActivity): void {
    if (!Number.isInteger(frameId) || frameId <= 0) throw new Error('frameId must be positive');
    if (this.terminal) throw new Error('collector is complete or its lease was lost');
    const now = this.now();
    this.closeActive(now);
    this.context = { frameId, activity };
    this.paused = false;
    this.startIfForeground(now);
  }

  setActivity(activity: EffortActivity): void {
    if (!this.context || this.terminal) return;
    const now = this.now();
    this.closeActive(now);
    this.context = { ...this.context, activity };
    this.startIfForeground(now);
  }

  recordActivity(): void {
    if (!this.context || this.paused || this.terminal || !this.isForeground()) return;
    const now = this.now();
    if (this.activeStartedAt === null) this.activeStartedAt = now;
    this.lastActivityAt = now;
    this.armIdleTimer();
  }

  pause(): void {
    if (this.paused) return;
    this.closeActive(this.now());
    this.paused = true;
  }

  resume(): void {
    if (!this.context || this.terminal) return;
    this.paused = false;
    this.startIfForeground(this.now());
  }

  async complete(): Promise<void> {
    this.stopTerminal();
    await this.flush();
  }

  async loseLease(): Promise<void> {
    this.stopTerminal();
    await this.flush();
  }

  pendingEvents(): readonly EffortEvent[] {
    return this.queue;
  }

  flush(): Promise<void> {
    if (this.inFlight) return this.inFlight;
    if (this.queue.length === 0) return Promise.resolve();
    const batch = this.queue.slice(0, this.batchSize);
    const ids = new Set(batch.map((event) => event.client_event_id));
    this.inFlight = this.send(batch)
      .then(() => {
        this.queue = this.queue.filter((event) => !ids.has(event.client_event_id));
        this.persistQueue();
        this.clearRetry();
      })
      .catch(() => {
        this.scheduleRetry();
      })
      .finally(() => {
        this.inFlight = null;
        if (this.queue.length > 0 && !this.retryTimer) void this.flush();
      });
    return this.inFlight;
  }

  destroy(): void {
    this.pause();
    if (this.flushTimer) clearInterval(this.flushTimer);
    this.clearIdleTimer();
    this.clearRetry();
    this.targetWindow?.removeEventListener('blur', this.onBlur);
    this.targetWindow?.removeEventListener('focus', this.onFocus);
    this.targetWindow?.removeEventListener('pointerdown', this.onActivity);
    this.targetWindow?.removeEventListener('keydown', this.onActivity);
    this.targetDocument?.removeEventListener('visibilitychange', this.onVisibilityChange);
  }

  private readonly onBlur = () => {
    this.focused = false;
    this.closeActive(this.now());
  };
  private readonly onFocus = () => {
    this.focused = true;
    this.startIfForeground(this.now());
  };
  private readonly onActivity = () => this.recordActivity();
  private readonly onVisibilityChange = () => {
    if (this.targetDocument?.visibilityState === 'hidden') this.closeActive(this.now());
    else this.startIfForeground(this.now());
  };

  private isForeground(): boolean {
    return this.focused && (!this.targetDocument || this.targetDocument.visibilityState !== 'hidden');
  }

  private startIfForeground(at: number): void {
    if (!this.context || this.paused || this.terminal || !this.isForeground()) return;
    if (this.activeStartedAt === null) this.activeStartedAt = at;
    this.lastActivityAt = at;
    this.armIdleTimer();
  }

  private closeActive(at: number): void {
    this.clearIdleTimer();
    if (this.activeStartedAt !== null && this.context && at > this.activeStartedAt) {
      this.queue.push({
        client_event_id: this.makeId(),
        frame_id: this.context.frameId,
        activity: this.context.activity,
        started_at: new Date(this.activeStartedAt).toISOString(),
        ended_at: new Date(at).toISOString(),
      });
      this.persistQueue();
      if (this.queue.length >= this.batchSize) void this.flush();
    }
    this.activeStartedAt = null;
    this.lastActivityAt = null;
  }

  private armIdleTimer(): void {
    this.clearIdleTimer();
    if (this.idleAfterMs === null || this.lastActivityAt === null) return;
    const lastActivity = this.lastActivityAt;
    this.idleTimer = setTimeout(() => {
      if (this.lastActivityAt !== lastActivity) return;
      // Exclude the whole inactive gap, not merely the part beyond the threshold.
      this.closeActive(lastActivity);
    }, this.idleAfterMs);
  }

  private clearIdleTimer(): void {
    if (this.idleTimer) clearTimeout(this.idleTimer);
    this.idleTimer = null;
  }

  private stopTerminal(): void {
    if (this.terminal) return;
    this.closeActive(this.now());
    this.paused = true;
    this.terminal = true;
    this.context = null;
  }

  private scheduleRetry(): void {
    if (this.retryTimer) return;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      void this.flush();
    }, this.retryAfterMs);
  }

  private clearRetry(): void {
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }

  private restoreQueue(): void {
    const raw = this.storage?.getItem(this.storageKey);
    if (!raw) return;
    try {
      const restored: unknown = JSON.parse(raw);
      if (Array.isArray(restored)) this.queue = restored as EffortEvent[];
    } catch {
      this.queue = [];
    }
  }

  private persistQueue(): void {
    this.storage?.setItem(this.storageKey, JSON.stringify(this.queue));
  }
}
