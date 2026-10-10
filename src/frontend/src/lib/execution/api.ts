import type { components } from '@/lib/api/contract';
import { apiClient, ApiRequestError } from '@/lib/api/client';

export type Snapshot = components['schemas']['Snapshot'];
export type ConfigVersion = components['schemas']['ConfigVersion'];
export type ConfigVersionCreate = components['schemas']['ConfigVersionCreate'];
export type Run = components['schemas']['Run'];
export type LedgerEntry = components['schemas']['LedgerEntry'];
export type RunShard = components['schemas']['RunShard'];
export type RunCreate = components['schemas']['RunCreate'];
export type Candidate = components['schemas']['Candidate'];
export type PaginatedCandidateList = components['schemas']['PaginatedCandidateList'];

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.data) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  return result.data;
}

export function cursorFrom(link: string | null | undefined): string | null {
  if (!link) return null;
  try { return new URL(link, 'http://localhost').searchParams.get('cursor'); }
  catch { return null; }
}

export async function listSnapshots(datasetId: number, cursor: string | null, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/snapshots/', { params: { query: { dataset_id: datasetId, ...(cursor ? { cursor } : {}) } }, signal }));
}

export async function listConfigs(cursor: string | null, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/config-versions/', { params: { query: { status: 'published', ...(cursor ? { cursor } : {}) } }, signal }));
}

export async function listRuns(datasetId: number, cursor: string | null, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/runs/', { params: { query: { dataset: datasetId, ...(cursor ? { cursor } : {}) } }, signal }));
}

export async function getRun(id: number, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/runs/{id}/', { params: { path: { id } }, signal }));
}

export async function getLedger(id: number, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/runs/{id}/ledger/', { params: { path: { id } }, signal }));
}

export async function listShards(id: number, cursor: string | null, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/runs/{id}/shards/', { params: { path: { id }, query: cursor ? { cursor } : {} }, signal }));
}

export async function listCandidates(id: number, cursor: string | null, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/runs/{id}/candidates/', { params: { path: { id }, query: cursor ? { cursor } : {} }, signal }));
}

async function csrf() {
  const result = await apiClient.GET('/api/auth/csrf/');
  if (!result.response.ok) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
}

export async function createRun(body: RunCreate, key: string) {
  await csrf();
  return unwrap(await apiClient.POST('/api/runs/', { body, params: { header: { 'Idempotency-Key': key } } }));
}

export async function createConfig(body: ConfigVersionCreate, key: string) {
  await csrf();
  return unwrap(await apiClient.POST('/api/config-versions/', { body, params: { header: { 'Idempotency-Key': key } } }));
}

export async function publishConfig(id: number) {
  await csrf();
  return unwrap(await apiClient.POST('/api/config-versions/{id}/publish/', { params: { path: { id } } }));
}

export async function cancelRun(id: number) {
  await csrf();
  return unwrap(await apiClient.POST('/api/runs/{id}/cancel/', { params: { path: { id } } }));
}

export async function retryRun(id: number) {
  await csrf();
  return unwrap(await apiClient.POST('/api/runs/{id}/retry-failed/', { params: { path: { id } } }));
}

export const runStatusLabel: Record<Run['status'], string> = {
  queued: 'Queued', running: 'Running', completed: 'Completed', partial: 'Partial', failed: 'Failed', cancelled: 'Cancelled',
};
export const engineStatusLabel: Record<LedgerEntry['status'], string> = {
  running: 'Running', checked: 'Checked', partial: 'Partial', failed: 'Failed', not_checked: 'Not checked',
};
