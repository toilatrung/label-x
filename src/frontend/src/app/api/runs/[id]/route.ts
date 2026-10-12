import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export const MOCK_RUN_DETAIL = {
  id: 91,
  display_id: 'QC-091',
  snapshot_id: 14,
  config_version_id: 7,
  seed: 42,
  status: 'partial',
  is_final: true,
  origin_run_id: null,
  score_version: 'v1',
  model_artifact: null,
  engines: [
    { engine: 'schema', status: 'completed', reason: null, failed_units: 0 },
    { engine: 'geometry', status: 'completed', reason: null, failed_units: 0 },
    { engine: 'duplicate', status: 'partial', reason: '1 lỗi trùng lặp IoU > 0.85', failed_units: 1 },
    { engine: 'detector', status: 'completed', reason: null, failed_units: 0 },
    { engine: 'vlm', status: 'completed', reason: null, failed_units: 0 },
    { engine: 'metric', status: 'not_checked', reason: 'Chưa có Ground Truth', failed_units: 0 },
  ],
  created_by: 1,
  created_at: '2026-10-04T06:58:00Z',
  finished_at: '2026-10-04T09:38:00Z',
};

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
  const { id } = await params;
  return NextResponse.json(
    {
      ...MOCK_RUN_DETAIL,
      id: Number(id) || 91,
    },
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}
