import { describe, it, expect, vi } from 'vitest';
import { createApiClient, ApiRequestError, AUTH_EXPIRED_EVENT } from '@/lib/api/client';
import { SERVER_ERROR_MESSAGE } from '@/lib/api/errors';
import { GET as csrf } from '@/app/api/auth/csrf/route';
import { POST as login } from '@/app/api/auth/login/route';
import { GET as session } from '@/app/api/auth/session/route';
import { POST as logout } from '@/app/api/auth/logout/route';
import { installMockAuthApi } from './helpers/mock-api';

function writeRequest(path: string, body: unknown, cookie = 'csrftoken=test-csrf', token = 'test-csrf') {
  return new Request('http://localhost:3000/api/auth/' + path + '/', {
    method: 'POST', headers: { Cookie: cookie, 'X-CSRFToken': token, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('T-001 auth contract', () => {
  it('issues a readable CSRF cookie with an empty 204 response', async () => {
    const response = await csrf();
    expect(response.status).toBe(204);
    expect(await response.text()).toBe('');
    expect(response.headers.get('set-cookie')).toContain('csrftoken=');
    expect(response.headers.get('set-cookie')).not.toContain('HttpOnly');
  });

  it('returns the complete Session shape and an opaque HttpOnly session cookie', async () => {
    const api = installMockAuthApi();
    const response = await api.signIn('reviewer');
    const data = await response.json();
    expect(data.user).toEqual({ id: 4, username: 'reviewer', display_name: 'Người kiểm tra mẫu' });
    expect(data.roles).toEqual([{ role: 'reviewer', dataset_id: 1 }]);
    expect(data.identity_mapping.status).toBe('mapped');
    expect(data).not.toHaveProperty('token');
    expect(response.headers.get('set-cookie')).toContain('HttpOnly');
    expect(api.jar.get('sessionid')).not.toBe('4');
    const restored = await session(new Request('http://localhost:3000/api/auth/session/', {
      headers: { Cookie: 'sessionid=' + api.jar.get('sessionid') },
    }));
    expect(await restored.json()).toEqual(data);
  });

  it('rejects absent CSRF, mismatched tokens and cross-origin login', async () => {
    for (const request of [
      writeRequest('login', { username: 'admin', password: 'password123' }, '', ''),
      writeRequest('login', { username: 'admin', password: 'password123' }, 'csrftoken=correct', 'wrong'),
      new Request(writeRequest('login', { username: 'admin', password: 'password123' }), {
        headers: { Cookie: 'csrftoken=test-csrf', 'X-CSRFToken': 'test-csrf', Origin: 'https://other.example' },
      }),
    ]) {
      const response = await login(request);
      expect(response.status).toBe(403);
      expect((await response.json()).code).toBe('FORBIDDEN');
    }
  });

  it('returns 400 INVALID_CREDENTIALS and a matching request identifier', async () => {
    const response = await login(writeRequest('login', { username: 'admin', password: 'wrong' }));
    const error = await response.json();
    expect(response.status).toBe(400);
    expect(error.code).toBe('INVALID_CREDENTIALS');
    expect(error.request_id).toBe(response.headers.get('X-Request-ID'));
    expect(response.headers.get('set-cookie')).toBeNull();
  });

  it('checks browser Origin against Host even when Next normalizes the internal URL', async () => {
    const response = await login(new Request('http://localhost:3102/api/auth/login/', {
      method: 'POST', headers: { Host: '127.0.0.1:3102', Origin: 'http://127.0.0.1:3102',
        Cookie: 'csrftoken=host-csrf', 'X-CSRFToken': 'host-csrf', 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'password123' }),
    }));
    expect(response.status).toBe(200);
  });

  it('handles malformed and wrongly typed credentials as validation errors', async () => {
    for (const body of [null, { username: 12, password: 'x' }, { username: 'admin' }]) {
      const response = await login(writeRequest('login', body));
      expect(response.status).toBe(400);
      expect((await response.json()).code).toBe('VALIDATION_ERROR');
    }
    const invalidJson = new Request('http://localhost:3000/api/auth/login/', {
      method: 'POST', headers: { Cookie: 'csrftoken=x', 'X-CSRFToken': 'x' }, body: '{',
    });
    expect((await login(invalidJson)).status).toBe(400);
  });

  it('rejects forged sessions and expired sessions with 403 NOT_AUTHENTICATED', async () => {
    const forged = await session(new Request('http://localhost:3000/api/auth/session/', {
      headers: { Cookie: 'sessionid=1' },
    }));
    expect(forged.status).toBe(403);
    expect((await forged.json()).code).toBe('NOT_AUTHENTICATED');
    const api = installMockAuthApi();
    await api.signIn();
    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 9 * 60 * 60 * 1000);
    const expired = await session(new Request('http://localhost:3000/api/auth/session/', {
      headers: { Cookie: 'sessionid=' + api.jar.get('sessionid') },
    }));
    expect(expired.status).toBe(403);
  });

  it('invalidates a server session and supports repeated logout with 204', async () => {
    const api = installMockAuthApi();
    await api.signIn();
    const cookie = 'sessionid=' + api.jar.get('sessionid') + '; csrftoken=x';
    for (let count = 0; count < 2; count++) {
      const response = await logout(writeRequest('logout', undefined, cookie, 'x'));
      expect(response.status).toBe(204);
      expect(await response.text()).toBe('');
    }
    const after = await session(new Request('http://localhost:3000/api/auth/session/', { headers: { Cookie: cookie } }));
    expect(after.status).toBe(403);
  });
});

describe('Shared typed API client', () => {
  it('keeps the session on a server failure even if its code says NOT_AUTHENTICATED', async () => {
    const expired = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    try {
      const client = createApiClient({ baseUrl: 'http://localhost:3000', fetch: async () =>
        Response.json({ code: 'NOT_AUTHENTICATED', request_id: 'server-trace' }, { status: 503 }) });
      const { error, response } = await client.GET('/api/guidelines/rules/');
      expect(expired).not.toHaveBeenCalled();
      expect(new ApiRequestError(response.status, error, response.headers).message)
        .toBe(`${SERVER_ERROR_MESSAGE} Mã yêu cầu: server-trace`);
    } finally {
      window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
    }
  });

  it('sends CSRF and cookies on contract write paths', async () => {
    document.cookie = 'csrftoken=client-csrf; path=/';
    const transport = vi.fn(async (request: Request) => {
      expect(request.method).toBe('POST');
      return new Response(null, { status: 204 });
    });
    const client = createApiClient({ baseUrl: 'http://localhost:3000', fetch: transport });
    await client.POST('/api/auth/logout/');
    const request = transport.mock.calls[0][0];
    expect(request.url).toBe('http://localhost:3000/api/auth/logout/');
    expect(request.credentials).toBe('include');
    expect(request.headers.get('X-CSRFToken')).toBe('client-csrf');
  });

  it.each([401, 403])('signals expired authentication for status %s', async (status) => {
    const expired = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    try {
      const client = createApiClient({ baseUrl: 'http://localhost:3000', fetch: async () =>
        Response.json({ code: 'NOT_AUTHENTICATED', message: 'Chưa đăng nhập.', request_id: 'test-request' }, { status }) });
      await expect(client.GET('/api/auth/session/')).rejects.toBeInstanceOf(ApiRequestError);
      expect(expired).toHaveBeenCalledOnce();
    } finally { window.removeEventListener(AUTH_EXPIRED_EVENT, expired); }
  });

  it.each(['OUT_OF_SCOPE', 'SELF_REVIEW_FORBIDDEN', 'SAME_REQUESTER_APPROVER'] as const)
    ('returns operation-level 403 %s to the caller without an auth event', async (code) => {
    const expired = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    try {
      const client = createApiClient({ baseUrl: 'http://localhost:3000', fetch: async () =>
        Response.json({ code, message: 'Thao tác bị từ chối.', request_id: 'test-request' }, { status: 403 }) });
      const { response, error } = await client.GET('/api/runs/', {});
      expect(response.status).toBe(403);
      expect(error).toMatchObject({ code, request_id: 'test-request' });
      expect(expired).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
    }
  });

  it.each([
    { body: '<h1>Proxy traceback</h1>', contentType: 'text/html' },
    { body: '{', contentType: 'application/json' },
    { body: 'null', contentType: 'application/json' },
    { body: '["Server diagnostic"]', contentType: 'application/json' },
    { body: '', contentType: 'text/plain' },
  ])('preserves server status and trace when the error body is $body', async ({ body, contentType }) => {
    const expired = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    try {
      const client = createApiClient({ baseUrl: 'http://localhost:3000', fetch: async () => new Response(body, {
        status: 502, headers: { 'Content-Type': contentType, 'X-Request-ID': 'proxy-request' },
      }) });
      await expect(client.GET('/api/guidelines/rules/')).rejects.toMatchObject({
        name: 'ApiRequestError', status: 502, requestId: 'proxy-request',
        message: 'Máy chủ gặp lỗi. Vui lòng thử lại sau. Mã yêu cầu: proxy-request',
      });
      expect(expired).not.toHaveBeenCalled();
    } finally { window.removeEventListener(AUTH_EXPIRED_EVENT, expired); }
  });

  it('preserves the server trace when authentication expires', async () => {
    const client = createApiClient({ baseUrl: 'http://localhost:3000', fetch: async () =>
      Response.json({ code: 'NOT_AUTHENTICATED', message: 'Server diagnostic', request_id: 'expired-request' }, { status: 403 }) });
    await expect(client.GET('/api/auth/session/')).rejects.toMatchObject({
      name: 'ApiRequestError', status: 403, requestId: 'expired-request',
      message: 'Phiên đăng nhập đã hết hạn hoặc bạn chưa đăng nhập. Vui lòng đăng nhập lại.',
    });
  });
});
