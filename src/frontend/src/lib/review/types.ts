import type { components } from '@/lib/api/contract';

export type QueueName = components['schemas']['QueueName'];
export type IssueFamily = components['schemas']['IssueFamily'];
export type IssueOrigin = components['schemas']['IssueOrigin'];
export type FrameReviewState = components['schemas']['FrameReviewState'];
export type RankedFrame = components['schemas']['RankedFrame'];
export type PaginatedRankedFrameList = components['schemas']['PaginatedRankedFrameList'];
export type Lease = components['schemas']['Lease'];
export type FrameSummary = components['schemas']['FrameSummary'];
export type LeaseGrant = components['schemas']['LeaseGrant'];
export type Run = components['schemas']['Run'];

export interface ReviewQueueFilters {
  family?: IssueFamily;
  origin?: IssueOrigin;
  review_state?: FrameReviewState;
}

export type ClaimResult =
  | { type: 'success'; grant: LeaseGrant }
  | { type: 'empty_queue_204' }
  | { type: 'conflict_409'; message: string }
  | { type: 'error'; message: string; code?: string };
