import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components, operations } from '@/lib/api/contract';

export type ReworkStatus = NonNullable<
  operations['rework_list']['parameters']['query']['status']
>;
export type ReworkItem = components['schemas']['ReworkRead'];
export type ReworkPage = components['schemas']['PaginatedReworkList'];
export type ReworkDetail = components['schemas']['ReworkDetail'];
export type ReworkCurrentRevision = components['schemas']['ReworkCurrentRevision'];
export type ReworkCreateInput = components['schemas']['ReworkCreate'];
export type ReworkSubmissionInput = components['schemas']['ReworkSubmission'];
export type ReworkVerificationInput = components['schemas']['ReworkVerification'];
export type ReworkRequest = components['schemas']['ReworkRequest'];

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.data) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}

async function ensureCsrf(): Promise<void> {
  const result = await apiClient.GET('/api/auth/csrf/', { cache: 'no-store' });
  if (!result.response.ok) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
}

export async function getReworks(
  datasetId: number,
  status: ReworkStatus,
  signal?: AbortSignal,
): Promise<ReworkPage> {
  const result = await apiClient.GET('/api/rework/', {
    params: { query: { dataset_id: datasetId, status } },
    signal,
    cache: 'no-store',
  });
  return unwrap(result);
}

export async function getRework(id: number, signal?: AbortSignal): Promise<ReworkDetail> {
  return unwrap(await apiClient.GET('/api/rework/{id}/', {
    params: { path: { id } },
    signal,
    cache: 'no-store',
  }));
}

export async function getReworkCurrentRevision(
  id: number,
  signal?: AbortSignal,
): Promise<ReworkCurrentRevision> {
  return unwrap(await apiClient.GET('/api/rework/{id}/current-revision/', {
    params: { path: { id } },
    signal,
    cache: 'no-store',
  }));
}

export async function createRework(
  body: ReworkCreateInput,
  idempotencyKey: string,
): Promise<ReworkRequest> {
  await ensureCsrf();
  return unwrap(await apiClient.POST('/api/rework/', {
    params: { header: { 'Idempotency-Key': idempotencyKey } },
    body,
  }));
}

export async function submitRework(
  id: number,
  body: ReworkSubmissionInput,
  idempotencyKey: string,
): Promise<ReworkRequest> {
  await ensureCsrf();
  return unwrap(await apiClient.POST('/api/rework/{id}/submitted/', {
    params: { path: { id }, header: { 'Idempotency-Key': idempotencyKey } },
    body,
  }));
}

export async function verifyRework(
  id: number,
  body: ReworkVerificationInput,
  idempotencyKey: string,
): Promise<ReworkRequest> {
  await ensureCsrf();
  return unwrap(await apiClient.POST('/api/rework/{id}/verify/', {
    params: { path: { id }, header: { 'Idempotency-Key': idempotencyKey } },
    body,
  }));
}
