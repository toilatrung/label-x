import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export const MOCK_ESCALATIONS = [
  {
    id: 902,
    issue_id: 902,
    frame_id: 3301,
    origin: 'engine',
    family: 'geometry',
    severity: 'major',
    status: 'escalated',
    description: 'Bounding box vượt biên ảnh 3 px - nghi vấn sai số camera góc siêu rộng.',
    review_decisions: [
      {
        id: 11,
        outcome: 'escalate',
        actor_user_id: 28,
        reason: 'Không thống nhất giữa reviewer và guideline GEO-001',
        created_at: '2026-10-10T14:20:00Z',
      },
    ],
    created_at: '2026-10-10T14:20:00Z',
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
      results: MOCK_ESCALATIONS,
    },
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}
