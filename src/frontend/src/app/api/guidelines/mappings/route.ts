import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export const MOCK_GUIDELINE_MAPPINGS = [
  { family: 'geometry', label: 'car', rule_ids: ['GEO-001'] },
  { family: 'taxonomy', label: 'car', rule_ids: ['TAX-003'] },
  { family: 'duplicate', label: 'car', rule_ids: ['DUP-001'] },
  { family: 'vehicle_confusion', label: 'truck', rule_ids: ['VEH-02'] },
  { family: 'pedestrian_confusion', label: 'pedestrian', rule_ids: ['PED-01'] },
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
      results: MOCK_GUIDELINE_MAPPINGS,
    },
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}
