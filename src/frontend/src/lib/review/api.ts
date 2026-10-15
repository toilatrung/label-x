import { apiClient, ApiRequestError } from '@/lib/api/client';
import type {
  QueueName,
  IssueFamily,
  IssueOrigin,
  FrameReviewState,
  PaginatedRankedFrameList,
  LeaseGrant,
  Lease,
  Run,
} from './types';
import type { components } from '@/lib/api/contract';

export type QueueSummary = components['schemas']['QueueSummary'];
export type RankingPriority = NonNullable<components['schemas']['RankedFrame']['priority']>;

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.data) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}

export function cursorFrom(link: string | null | undefined): string | null {
  if (!link) return null;
  try {
    return new URL(link, 'http://localhost').searchParams.get('cursor');
  } catch {
    return null;
  }
}

async function csrf() {
  const result = await apiClient.GET('/api/auth/csrf/');
  if (!result.response.ok) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
}

export async function getRunDetails(runId: number, signal?: AbortSignal): Promise<Run> {
  const result = await apiClient.GET('/api/runs/{id}/', {
    params: { path: { id: runId } },
    signal,
  });
  return unwrap(result);
}

export interface GetRunRankingOptions {
  queue?: QueueName;
  family?: IssueFamily;
  origin?: IssueOrigin;
  review_state?: FrameReviewState;
  /** Tìm theo frame_key (cvat_task_id hoặc frame_number), MBE-02. */
  q?: string;
  priority?: RankingPriority;
  cursor?: string | null;
  signal?: AbortSignal;
}

export async function getRunRanking(
  runId: number,
  options: GetRunRankingOptions = {}
): Promise<PaginatedRankedFrameList> {
  const { queue, family, origin, review_state, q, priority, cursor, signal } = options;
  const search = q?.trim();
  const result = await apiClient.GET('/api/runs/{id}/ranking/', {
    params: {
      path: { id: runId },
      query: {
        ...(queue ? { queue } : {}),
        ...(family ? { family } : {}),
        ...(origin ? { origin } : {}),
        ...(review_state ? { review_state } : {}),
        ...(search ? { q: search } : {}),
        ...(priority ? { priority } : {}),
        ...(cursor ? { cursor } : {}),
      },
    },
    signal,
  });
  return unwrap(result);
}

/** GET /api/queues/{name}/?run_id= — tổng số frame và số đếm theo FrameReviewState (MBE-02). */
export async function getQueueSummary(
  queueName: QueueName,
  runId: number,
  signal?: AbortSignal
): Promise<QueueSummary> {
  const result = await apiClient.GET('/api/queues/{name}/', {
    params: { path: { name: queueName }, query: { run_id: runId } },
    signal,
  });
  return unwrap(result);
}

export type ClaimNextFrameResponse =
  | { status: 200; grant: LeaseGrant }
  | { status: 204 };

export async function claimNextFrame(
  queueName: QueueName,
  runId: number,
  signal?: AbortSignal,
  frameId?: number,
  previousLeaseId?: number
): Promise<ClaimNextFrameResponse> {
  await csrf();
  const result = await apiClient.POST('/api/queues/{name}/next/', {
    params: { path: { name: queueName } },
    // frame_id (MBE-02): nhận đúng frame này; không có thì nhận frame kế tiếp của hàng đợi.
    body: { run_id: runId, ...(frameId ? { frame_id: frameId } : {}), ...(previousLeaseId ? { previous_lease_id: previousLeaseId } : {}) },
    signal,
  });

  if (result.response.status === 204) {
    return { status: 204 };
  }

  if (result.error || !result.data) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }

  return { status: 200, grant: result.data };
}

export async function renewLease(leaseId: number, signal?: AbortSignal): Promise<Lease> {
  await csrf();
  const result = await apiClient.POST('/api/leases/{id}/renew/', {
    params: { path: { id: leaseId } },
    signal,
  });
  return unwrap(result);
}
