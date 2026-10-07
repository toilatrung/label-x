import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import type { ApiError, AuthSession } from '@/types/auth';
import { isMockAuth } from './config';

type StoredSession = { session: AuthSession; expiresAt: number };
const mockGlobal = globalThis as typeof globalThis & { labelxMockSessions?: Map<string, StoredSession> };
const sessions = mockGlobal.labelxMockSessions ??= new Map<string, StoredSession>();
const SESSION_SECONDS = 8 * 60 * 60;

export function mockError(code: ApiError['code'], message: string, status: number, details?: ApiError['details']) {
  const request_id = randomUUID();
  return NextResponse.json({ code, message, request_id, ...(details ? { details } : {}) } satisfies ApiError,
    { status, headers: { 'X-Request-ID': request_id, 'Cache-Control': 'no-store' } });
}

export function mockDisabled() {
  return isMockAuth ? null : mockError('NOT_FOUND', 'API mẫu chưa được bật.', 404);
}

export function readCookie(request: Request, name: string): string | undefined {
  return request.headers.get('cookie')?.split(/;\s*/).find((part) => part.startsWith(`${name}=`))?.slice(name.length + 1);
}

export function checkCsrf(request: Request) {
  const token = readCookie(request, 'csrftoken');
  const origin = request.headers.get('origin');
  // Next may normalize the internal URL to localhost while the browser uses 127.0.0.1.
  const url = new URL(request.url);
  const expectedOrigin = `${url.protocol}//${request.headers.get('host') ?? url.host}`;
  if (!token || request.headers.get('X-CSRFToken') !== token ||
    (origin !== null && origin !== expectedOrigin)) {
    return mockError('FORBIDDEN', 'Yêu cầu thiếu hoặc sai mã bảo vệ. Vui lòng thử lại.', 403);
  }
  return null;
}

export function issueMockSession(session: AuthSession): string {
  for (const [key, value] of sessions) if (value.expiresAt <= Date.now()) sessions.delete(key);
  const token = randomUUID();
  sessions.set(token, { session, expiresAt: Date.now() + SESSION_SECONDS * 1000 });
  return token;
}

export function readMockSession(request: Request): AuthSession | null {
  const token = readCookie(request, 'sessionid');
  const record = token ? sessions.get(token) : undefined;
  if (!record || record.expiresAt <= Date.now()) {
    if (token) sessions.delete(token);
    return null;
  }
  return record.session;
}

export function endMockSession(request: Request) {
  const token = readCookie(request, 'sessionid');
  if (token) sessions.delete(token);
}

export const sessionCookieOptions = {
  httpOnly: true, path: '/', sameSite: 'lax' as const, maxAge: SESSION_SECONDS,
  secure: process.env.NODE_ENV === 'production',
};
