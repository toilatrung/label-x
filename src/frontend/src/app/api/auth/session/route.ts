import { NextResponse } from 'next/server';
import { mockDisabled, mockError, readMockSession } from '@/lib/auth/mock-server';

export async function GET(request: Request) {
  const disabled = mockDisabled();
  if (disabled) return disabled;
  const session = readMockSession(request);
  return session ? NextResponse.json(session, { headers: { 'Cache-Control': 'no-store' } }) :
    mockError('NOT_AUTHENTICATED', 'Chưa đăng nhập hoặc phiên làm việc đã hết hạn.', 403);
}
