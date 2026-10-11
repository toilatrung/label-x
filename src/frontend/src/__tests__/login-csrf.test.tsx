import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { AuthProvider, useAuth } from '@/lib/auth/auth-context';
import { ApiRequestError, CSRF_ERROR_MESSAGE, isCsrfError } from '@/lib/api/errors';
import { toMockSession, MOCK_USERS } from '@/lib/auth/mock-users';

const csrfBody = { code: 'FORBIDDEN', message: 'Yêu cầu thiếu hoặc sai mã bảo vệ.', request_id: 'r1', details: { reason: 'csrf' } };

function stubApi(loginReplies: Response[]) {
  const calls: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: Request) => {
    const { pathname } = new URL(input.url);
    calls.push(input.method + ' ' + pathname);
    if (pathname === '/api/auth/session/') return Response.json({ code: 'NOT_AUTHENTICATED', message: 'x', request_id: 'r0' }, { status: 403 });
    if (pathname === '/api/auth/csrf/') return new Response(null, { status: 204 });
    if (pathname === '/api/auth/login/') return loginReplies.shift()!;
    throw new Error('Unexpected ' + pathname);
  }));
  return calls;
}

const wrapper = ({ children }: { children: React.ReactNode }) => <AuthProvider>{children}</AuthProvider>;
afterEach(() => vi.unstubAllGlobals());

describe('login CSRF handling', () => {
  it('names a CSRF failure instead of reporting missing permission', () => {
    const error = new ApiRequestError(403, csrfBody);
    expect(isCsrfError(error)).toBe(true);
    expect(error.message).toBe(CSRF_ERROR_MESSAGE);
    expect(new ApiRequestError(403, { code: 'FORBIDDEN', message: 'x', request_id: 'r' }).message)
      .toBe('Bạn không có quyền thực hiện thao tác này.');
  });

  it('fetches a fresh csrf token and retries the login once', async () => {
    const calls = stubApi([Response.json(csrfBody, { status: 403 }), Response.json(toMockSession(MOCK_USERS[0]))]);
    const { result } = renderHook(() => useAuth(), { wrapper });
    let outcome: { success: boolean } | undefined;
    await act(async () => { outcome = await result.current.login({ username: 'admin', password: 'password123' }); });
    expect(outcome?.success).toBe(true);
    expect(calls.filter((c) => c === 'GET /api/auth/csrf/')).toHaveLength(2);
    expect(calls.filter((c) => c === 'POST /api/auth/login/')).toHaveLength(2);
  });

  it('reports the CSRF cause when the retry also fails, without a third attempt', async () => {
    const calls = stubApi([Response.json(csrfBody, { status: 403 }), Response.json(csrfBody, { status: 403 })]);
    const { result } = renderHook(() => useAuth(), { wrapper });
    let outcome: { success: boolean; error?: string } | undefined;
    await act(async () => { outcome = await result.current.login({ username: 'admin', password: 'password123' }); });
    expect(outcome).toEqual({ success: false, error: CSRF_ERROR_MESSAGE });
    expect(calls.filter((c) => c === 'POST /api/auth/login/')).toHaveLength(2);
  });

  it('does not retry wrong credentials', async () => {
    const calls = stubApi([Response.json({ code: 'INVALID_CREDENTIALS', message: 'x', request_id: 'r' }, { status: 400 })]);
    const { result } = renderHook(() => useAuth(), { wrapper });
    await act(async () => { await result.current.login({ username: 'a', password: 'b' }); });
    expect(calls.filter((c) => c === 'POST /api/auth/login/')).toHaveLength(1);
  });
});
