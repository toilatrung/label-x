import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';
import frameFixture from '@/lib/demo/frames.fixture.json';

// DEMO-ONLY: lets the M-DEMO01 workspace run against the shared fixture in mock-auth mode.
export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!isMockAuth || id !== String(frameFixture.run_id)) {
    return NextResponse.json({ code: 'NOT_FOUND', message: 'QC run không tồn tại.' }, { status: 404 });
  }
  return NextResponse.json(frameFixture);
}
