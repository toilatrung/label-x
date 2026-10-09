import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components } from '@/lib/api/contract';

export type Dataset = components['schemas']['Dataset'];
export type DatasetPage = components['schemas']['PaginatedDatasetList'];
export type CvatTask = components['schemas']['CvatTask'];
export type Snapshot = components['schemas']['Snapshot'];
export type SnapshotPage = components['schemas']['PaginatedSnapshotList'];
export type SnapshotCreate = components['schemas']['SnapshotCreate'];
export type SnapshotAccepted = components['schemas']['SnapshotAccepted'];

function requireData<T>(reply: { data?: T; error?: unknown; response: Response }): T {
  if (reply.error || !reply.response.ok || reply.data === undefined) {
    throw new ApiRequestError(reply.response.status, reply.error, reply.response.headers);
  }
  return reply.data;
}

export async function getDatasets(cursor?: string, signal?: AbortSignal): Promise<DatasetPage> {
  return requireData(await apiClient.GET('/api/datasets/', {
    params: { query: cursor ? { cursor } : {} }, signal, cache: 'no-store',
  }));
}

export async function getTasks(datasetId: number, signal?: AbortSignal): Promise<CvatTask[]> {
  return requireData(await apiClient.GET('/api/datasets/{id}/tasks/', {
    params: { path: { id: datasetId } }, signal, cache: 'no-store',
  }));
}

export async function getSnapshots(datasetId: number, cursor?: string, signal?: AbortSignal): Promise<SnapshotPage> {
  return requireData(await apiClient.GET('/api/snapshots/', {
    params: { query: { dataset_id: datasetId, ...(cursor ? { cursor } : {}) } },
    signal, cache: 'no-store',
  }));
}

export async function getSnapshot(id: number, signal?: AbortSignal): Promise<Snapshot> {
  return requireData(await apiClient.GET('/api/snapshots/{id}/', {
    params: { path: { id } }, signal, cache: 'no-store',
  }));
}

export async function postSnapshot(body: SnapshotCreate, key: string): Promise<SnapshotAccepted> {
  requireData(await apiClient.GET('/api/auth/csrf/', { cache: 'no-store' }));
  const reply = await apiClient.POST('/api/snapshots/', {
    body, params: { header: { 'Idempotency-Key': key } },
  });
  if (reply.response.status !== 202) {
    throw new ApiRequestError(reply.response.status, reply.error, reply.response.headers);
  }
  return requireData(reply);
}

export function cursorFrom(next?: string | null): string | undefined {
  if (!next) return undefined;
  try { return new URL(next, 'http://localhost').searchParams.get('cursor') || undefined; }
  catch { return undefined; }
}

export function safeCvatUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null;
  } catch { return null; }
}

export function snapshotStatus(value: Snapshot['status']): string {
  return { pending: 'Đang chờ', exporting: 'Đang xuất', locked: 'Đã khóa', failed: 'Thất bại' }[value];
}
