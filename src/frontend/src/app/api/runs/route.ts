import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export const MOCK_RUNS = [
  {
    id: 91,
    display_id: 'QC-091',
    snapshot_id: 14,
    config_version_id: 7,
    status: 'partial',
    is_final: true,
    created_at: '2026-10-04T06:58:00Z',
    seed: 42,
    dataset_id: 14,
  },
];

export async function GET(request: Request) {
  if (!isMockAuth && process.env.NODE_ENV === 'production') {
    return NextResponse.json(
      { code: 'NOT_FOUND', message: 'API mẫu chưa được bật.' },
      { status: 404 }
    );
  }

  void request;
  return NextResponse.json(
    {
      next: null,
      previous: null,
      results: MOCK_RUNS,
    },
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}

export async function POST(request: Request) {
  if (!isMockAuth && process.env.NODE_ENV === 'production') {
    return NextResponse.json(
      { code: 'NOT_FOUND', message: 'API mẫu chưa được bật.' },
      { status: 404 }
    );
  }

  const body = await request.json().catch(() => ({}));
  const newRun = {
    id: 92,
    display_id: 'QC-092',
    snapshot_id: body.snapshot_id ?? 14,
    config_version_id: body.config_version_id ?? 7,
    status: 'queued',
    is_final: false,
    created_at: new Date().toISOString(),
    seed: body.seed ?? 42,
  };

  return NextResponse.json(newRun, { status: 201 });
}
