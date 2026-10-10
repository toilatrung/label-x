import type { components } from '@/lib/api/contract';
import { apiClient, ApiRequestError } from '@/lib/api/client';
import { apiBaseUrl } from '@/lib/auth/config';

export type DemoFramePage = components['schemas']['DemoFramePage'];
export type DemoFrame = components['schemas']['DemoFrame'];
export type DemoCandidate = components['schemas']['DemoCandidate'];

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.data) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}

// DEMO-ONLY: M-DEMO01 read model. Review decisions deliberately stay out of this API.
export async function getRankedFrames(runId: number, signal?: AbortSignal): Promise<DemoFramePage> {
  return unwrap(await apiClient.GET('/api/runs/{id}/frames/', {
    params: { path: { id: runId }, query: { page_size: 100 } },
    signal,
  }));
}

export function reviewImageUrl(path: string): string {
  return new URL(path, `${apiBaseUrl()}/`).toString();
}
