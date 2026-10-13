import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';
import { MOCK_DATASETS } from '@/lib/mock/datasets';

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
      results: MOCK_DATASETS,
    },
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}
