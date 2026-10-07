import { NextResponse } from 'next/server';
import { mockDisabled } from '@/lib/auth/mock-server';
import { MOCK_USERS } from '@/lib/auth/mock-users';

// Dev-only quick-pick list for the login screen. Server-side only, so demo credentials
// never reach the client bundle; returns 404 NOT_FOUND whenever mock auth is off.
export async function GET() {
  const disabled = mockDisabled();
  if (disabled) return disabled;
  return NextResponse.json(MOCK_USERS, { headers: { 'Cache-Control': 'no-store' } });
}
