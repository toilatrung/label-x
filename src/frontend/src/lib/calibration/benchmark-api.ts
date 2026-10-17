import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components } from '@/lib/api/contract';

export type Benchmark = components['schemas']['Benchmark'];
export type BenchmarkCreate = components['schemas']['BenchmarkCreate'];

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.response.ok || result.data === undefined) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}

export async function listBenchmarks(datasetId: number, cursor?: string, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/benchmarks/', {
    params: { query: { dataset_id: datasetId, ...(cursor ? { cursor } : {}) } },
    signal, cache: 'no-store',
  }));
}

export async function createBenchmark(body: BenchmarkCreate, key: string) {
  const csrf = await apiClient.GET('/api/auth/csrf/', { cache: 'no-store' });
  if (!csrf.response.ok) throw new ApiRequestError(csrf.response.status, csrf.error, csrf.response.headers);
  return unwrap(await apiClient.POST('/api/benchmarks/', {
    body, params: { header: { 'Idempotency-Key': key } },
  }));
}
