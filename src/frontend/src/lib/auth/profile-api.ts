import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components } from '@/lib/api/contract';

export type Profile = components['schemas']['Profile'];

export async function getProfile(signal?: AbortSignal): Promise<Profile> {
  const result = await apiClient.GET('/api/auth/profile/', { signal, cache: 'no-store' });
  if (result.error || !result.data) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  return result.data;
}

export async function saveProfile(token: string): Promise<Profile> {
  const csrf = await apiClient.GET('/api/auth/csrf/', { cache: 'no-store' });
  if (!csrf.response.ok) throw new ApiRequestError(csrf.response.status, csrf.error, csrf.response.headers);
  const result = await apiClient.PATCH('/api/auth/profile/', { body: { cvat_service_token: token } });
  if (result.error || !result.data) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  return result.data;
}

export async function deleteProfileToken(): Promise<Profile> {
  const csrf = await apiClient.GET('/api/auth/csrf/', { cache: 'no-store' });
  if (!csrf.response.ok) throw new ApiRequestError(csrf.response.status, csrf.error, csrf.response.headers);
  const result = await apiClient.DELETE('/api/auth/profile/');
  if (result.error || !result.data) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  return result.data;
}
