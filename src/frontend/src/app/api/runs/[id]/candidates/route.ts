import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export const MOCK_CANDIDATES = [
  {
    id: 501,
    frame_id: 3301,
    engine: 'duplicate',
    engine_version: '1.0.0',
    family: 'overlap',
    severity: 'major',
    frame: { cvat_task_id: 118, frame_number: 1 },
    anchor: { kind: 'annotation', objects: [{ namespace: 'cvat_shape', id: 's-117' }], policy_version: 'v1' },
    evidence: { engine: 'duplicate', iou: 0.94, description: 'Hai bounding box trùng lặp IoU 0.94 trên cùng một vật thể ô tô' },
  },
  {
    id: 502,
    frame_id: 3302,
    engine: 'detector',
    engine_version: '2.3.0',
    family: 'missing_annotation',
    severity: 'medium',
    frame: { cvat_task_id: 118, frame_number: 2 },
    anchor: { kind: 'prediction_region', objects: [{ namespace: 'detector', id: 'd-22' }], policy_version: 'v1' },
    evidence: { engine: 'detector', prediction_class: 'truck', confidence: 0.88, bbox: [120, 180, 240, 160] },
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
      raw_count: 512,
      dedup_count: 384,
      results: MOCK_CANDIDATES,
    },
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}
