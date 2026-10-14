import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components } from '@/lib/api/contract';

export type VlmSettings = components['schemas']['VlmSettings'];
export type VlmSettingsUpdate = components['schemas']['VlmSettingsUpdate'];

export async function getVlmSettings(signal?: AbortSignal): Promise<VlmSettings> {
  const result = await apiClient.GET('/api/configuration/vlm/', { signal, cache: 'no-store' });
  if (result.error || !result.data) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  return result.data;
}

export async function saveVlmSettings(body: VlmSettingsUpdate): Promise<VlmSettings> {
  const csrf = await apiClient.GET('/api/auth/csrf/', { cache: 'no-store' });
  if (!csrf.response.ok) throw new ApiRequestError(csrf.response.status, csrf.error, csrf.response.headers);
  const result = await apiClient.PATCH('/api/configuration/vlm/', { body });
  if (result.error || !result.data) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  return result.data;
}
