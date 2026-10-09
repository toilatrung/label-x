import createClient from 'openapi-fetch';
import type { paths } from './contract';
import { ApiRequestError, readErrorDetail } from './errors';
import { apiBaseUrl } from '@/lib/auth/config';

export const AUTH_EXPIRED_EVENT = 'labelx:auth-expired';

export { ApiRequestError } from './errors';

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
      if (response.ok) return;
      const detail = readErrorDetail(await response.clone().json().catch(() => undefined));
      if (request.signal.aborted) return;
      // HTML, empty and malformed error bodies must keep the status and trace header.
      if (!detail && response.status !== 401) {
        throw new ApiRequestError(response.status, undefined, response.headers);
      }
      const expired = response.status === 401 ||
        (response.status === 403 && detail?.code === 'NOT_AUTHENTICATED');
      // Operation-level 403 errors stay with the caller; they must not replace the page.
      if (!expired) return;
      if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail }));
      throw new ApiRequestError(response.status, detail, response.headers);
    },
  });
  return client;
}

export const apiClient = createApiClient();
