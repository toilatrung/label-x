import { NextResponse } from 'next/server';
import { findMockUser, toMockSession } from '@/lib/auth/mock-users';
import { checkCsrf, endMockSession, issueMockSession, mockDisabled, mockError, sessionCookieOptions } from '@/lib/auth/mock-server';

export async function POST(request: Request) {
  const rejected = mockDisabled() ?? checkCsrf(request);
  if (rejected) return rejected;
  const body: unknown = await request.json().catch(() => null);
  if (!body || typeof body !== 'object' || !('username' in body) || !('password' in body) ||
    typeof body.username !== 'string' || !body.username.trim() || typeof body.password !== 'string' || !body.password) {
    return mockError('VALIDATION_ERROR', 'Tên đăng nhập và mật khẩu không được để trống.', 400,
      { fields: { username: ['Nhập tên đăng nhập.'], password: ['Nhập mật khẩu.'] } });
  }
  const user = findMockUser(body.username, body.password);
  if (!user) return mockError('INVALID_CREDENTIALS', 'Tên đăng nhập hoặc mật khẩu không chính xác', 400);
  const session = toMockSession(user);
  endMockSession(request);
  const response = NextResponse.json(session, { headers: { 'Cache-Control': 'no-store' } });
  response.cookies.set('sessionid', issueMockSession(session), sessionCookieOptions);
  return response;
}
