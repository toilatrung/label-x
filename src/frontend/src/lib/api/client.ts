import createClient from 'openapi-fetch';
import type { paths } from './contract';
import type { ApiError } from '@/types/auth';
import { apiBaseUrl } from '@/lib/auth/config';

export const AUTH_EXPIRED_EVENT = 'labelx:auth-expired';
export const ACCESS_DENIED_EVENT = 'labelx:access-denied';

export class ApiRequestError extends Error {
  constructor(public status: number, public detail?: ApiError) {
    super(detail?.message || (status === 401 ? 'Phiên đăng nhập đã hết hạn.' :
      status === 403 ? 'Bạn không có quyền thực hiện yêu cầu này.' : 'Không thể xử lý yêu cầu.'));
  }
}

function csrfCookie(): string | undefined {
  if (typeof document === 'undefined') return undefined;
  return document.cookie.split('; ').find((part) => part.startsWith('csrftoken='))?.slice(10);
}

export function createApiClient(options: { baseUrl?: string; fetch?: (request: Request) => Promise<Response> } = {}) {
  const client = createClient<paths>({ baseUrl: options.baseUrl ?? apiBaseUrl(), credentials: 'include',
    fetch: options.fetch ?? ((request) => globalThis.fetch(request)) });
  client.use({
    onRequest({ request }) {
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method)) {
        const token = csrfCookie();
        if (token) request.headers.set('X-CSRFToken', token);
      }
    },
    async onResponse({ request, response }) {
      if (response.status !== 401 && response.status !== 403) return;
      const detail: ApiError | undefined = await response.clone().json().catch(() => undefined);
      if (request.signal.aborted) return;
      const expired = response.status === 401 || detail?.code === 'NOT_AUTHENTICATED';
      if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(
        expired ? AUTH_EXPIRED_EVENT : ACCESS_DENIED_EVENT, { detail }));
      throw new ApiRequestError(response.status, detail);
    },
  });
  return client;
}

export const apiClient = createApiClient();
