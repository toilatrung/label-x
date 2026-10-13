import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components } from '@/lib/api/contract';

export type ReviewPolicy = components['schemas']['ReviewPolicy'];

export async function getReviewPolicy(
  datasetId?: number | null,
  signal?: AbortSignal,
): Promise<ReviewPolicy> {
  const result = await apiClient.GET('/api/review-policy/', {
    params: { query: datasetId ? { dataset_id: datasetId } : {} },
    signal,
    cache: 'no-store',
  });
  if (result.error || !result.data) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}
