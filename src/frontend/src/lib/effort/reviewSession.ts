import type { components } from '@/lib/api/contract';
import { ApiRequestError } from '@/lib/api/errors';

import {
  EffortCollector,
  type EffortCollectorOptions,
  type EffortActivity,
} from './collector';

type LeaseGrant = components['schemas']['LeaseGrant'];
type IssueDecision = components['schemas']['IssueDecision'];
type FrameSummary = components['schemas']['FrameSummary'];

/**
 * Connects the shared collector to the real T-033 lease and T-035 decision lifecycle.
 * A successful complete stops collection; a rejected complete leaves it running so the
 * reviewer can resolve the remaining issues. A lease conflict is terminal.
 */
export class ReviewEffortSession {
  readonly collector: EffortCollector;
  private frameId: number | null = null;

  constructor(options: EffortCollectorOptions) {
    this.collector = new EffortCollector(options);
  }

  start(grant: LeaseGrant): void {
    if (grant.lease.frame_id !== grant.frame.id) {
      throw new Error('Lease grant frame identity is inconsistent');
    }
    this.frameId = grant.frame.id;
    this.collector.begin(grant.frame.id, 'view_frame');
  }

  setActivity(activity: EffortActivity): void {
    if (this.frameId === null) throw new Error('Review session has not started');
    this.collector.setActivity(activity);
  }

  decisionSaved(decision: IssueDecision): void {
    if (this.frameId === null) throw new Error('Review session has not started');
    if (!Number.isInteger(decision.id) || decision.id <= 0) {
      throw new Error('Persisted decision identity is invalid');
    }
    this.collector.setActivity('view_frame');
  }

  async completeAfter(request: Promise<FrameSummary>): Promise<FrameSummary> {
    const frame = await request;
    if (frame.id !== this.frameId) throw new Error('Completed frame does not match effort session');
    await this.collector.complete();
    return frame;
  }

  async stopOnLeaseConflict(error: unknown): Promise<boolean> {
    if (
      error instanceof ApiRequestError &&
      error.status === 409 &&
      error.detail?.code === 'LEASE_CONFLICT'
    ) {
      await this.collector.loseLease();
      return true;
    }
    return false;
  }

  destroy(): void {
    this.collector.destroy();
  }
}
