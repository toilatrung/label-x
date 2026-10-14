import { apiClient, ApiRequestError } from '@/lib/api/client';
function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || result.data === undefined || !result.response.ok) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  return result.data;
}
async function csrf() {
  const result = await apiClient.GET('/api/auth/csrf/');
  if (!result.response.ok) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
}
export async function importGuideline(content: string) {
  await csrf();
  return unwrap(await apiClient.POST('/api/guidelines/import/', { body: { content } }));
}
export async function getDatasetGuideline(id: number, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/datasets/{id}/guideline/', { params: { path: { id } }, signal }));
}
export async function setDatasetGuideline(id: number, guideline_version: string, expected_revision: number) {
  await csrf();
  return unwrap(await apiClient.PUT('/api/datasets/{id}/guideline/', {
    params: { path: { id } }, body: { guideline_version, expected_revision },
  }));
}
export async function listGuidelineVersions(cursor?: string, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/guidelines/versions/', { params: { query: cursor ? { cursor } : {} }, signal }));
}
