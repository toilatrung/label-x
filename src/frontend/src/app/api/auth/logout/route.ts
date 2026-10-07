import { NextResponse } from 'next/server';
import { checkCsrf, endMockSession, mockDisabled, sessionCookieOptions } from '@/lib/auth/mock-server';

export async function POST(request: Request) {
  const disabled = mockDisabled();
  if (disabled) return disabled;
  const rejected = checkCsrf(request);
  if (rejected) return rejected;
  endMockSession(request);
  const response = new NextResponse(null, { status: 204, headers: { 'Cache-Control': 'no-store' } });
  response.cookies.set('sessionid', '', { ...sessionCookieOptions, maxAge: 0 });
  return response;
}
