import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components, operations } from '@/lib/api/contract';

export type ReworkStatus = NonNullable<
  operations['rework_list']['parameters']['query']['status']
>;
export type ReworkItem = components['schemas']['ReworkRead'];
export type ReworkPage = components['schemas']['PaginatedReworkList'];

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
  if (result.error || !result.data) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}
