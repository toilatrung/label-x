import { randomUUID } from 'node:crypto';
import { NextResponse } from 'next/server';
import { mockDisabled } from '@/lib/auth/mock-server';

export async function GET() {
  const disabled = mockDisabled();
  if (disabled) return disabled;
  const response = new NextResponse(null, { status: 204, headers: { 'Cache-Control': 'no-store' } });
  response.cookies.set('csrftoken', randomUUID(), { path: '/', sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production', maxAge: 86400 });
  return response;
}
