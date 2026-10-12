import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export const MOCK_SHARDS = [
  {
    id: 1,
    run_id: 91,
    engine: 'schema',
    shard_key: 'task:118',
    shard_index: 0,
    status: 'succeeded',
    attempt: 1,
    last_error: null,
  },
  {
    id: 2,
    run_id: 91,
    engine: 'geometry',
    shard_key: 'task:118',
    shard_index: 1,
    status: 'succeeded',
    attempt: 1,
    last_error: null,
  },
  {
    id: 3,
    run_id: 91,
    engine: 'duplicate',
    shard_key: 'task:118',
    shard_index: 2,
    status: 'failed',
    attempt: 1,
    last_error: '1 candidate IoU > 0.85',
  },
  {
    id: 4,
    run_id: 91,
    engine: 'detector',
    shard_key: 'task:119',
    shard_index: 0,
    status: 'succeeded',
    attempt: 1,
    last_error: null,
  },
  {
    id: 5,
    run_id: 91,
    engine: 'vlm',
    shard_key: 'task:120',
    shard_index: 0,
    status: 'succeeded',
    attempt: 1,
    last_error: null,
  },
];

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  if (!isMockAuth && process.env.NODE_ENV === 'production') {
    return NextResponse.json(
      { code: 'NOT_FOUND', message: 'API mẫu chưa được bật.' },
      { status: 404 }
    );
  }

  void request;
  void params;
  return NextResponse.json(
    {
      next: null,
      previous: null,
      results: MOCK_SHARDS,
    },
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}
