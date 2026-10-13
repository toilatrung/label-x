import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export const MOCK_LEDGER = [
  {
    engine: 'schema',
    status: 'completed',
    required: true,
    unit: 'frame',
    total: 12500,
    eligible: 12500,
    excluded: 0,
    applicability_version: 'v3',
    completed: 12500,
    failed: 0,
    pending: 0,
    not_checked: 0,
    not_checked_reasons: {},
    coverage: 1.0,
  },
  {
    engine: 'geometry',
    status: 'completed',
    required: true,
    unit: 'frame',
    total: 12500,
    eligible: 12500,
    excluded: 0,
    applicability_version: '1.0.0',
    completed: 12500,
    failed: 0,
    pending: 0,
    not_checked: 0,
    not_checked_reasons: {},
    coverage: 1.0,
  },
  {
    engine: 'duplicate',
    status: 'partial',
    required: true,
    unit: 'frame',
    total: 12500,
    eligible: 12500,
    excluded: 0,
    applicability_version: '1.0.0',
    completed: 12499,
    failed: 1,
    pending: 0,
    not_checked: 0,
    not_checked_reasons: {},
    coverage: 0.9999,
  },
  {
    engine: 'detector',
    status: 'completed',
    required: false,
    unit: 'frame',
    total: 12500,
    eligible: 12500,
    excluded: 0,
    applicability_version: '2.3.0',
    completed: 12500,
    failed: 0,
    pending: 0,
    not_checked: 0,
    not_checked_reasons: {},
    coverage: 1.0,
  },
  {
    engine: 'vlm',
    status: 'completed',
    required: false,
    unit: 'candidate',
    total: 400,
    eligible: 400,
    excluded: 0,
    applicability_version: '1.0.0',
    completed: 400,
    failed: 0,
    pending: 0,
    not_checked: 0,
    not_checked_reasons: {},
    coverage: 1.0,
  },
  {
    engine: 'metric',
    status: 'not_checked',
    required: false,
    unit: 'frame',
    total: 0,
    eligible: 0,
    excluded: 0,
    applicability_version: '1.0.0',
    completed: 0,
    failed: 0,
    pending: 0,
    not_checked: 0,
    not_checked_reasons: { not_applicable: 1 },
    coverage: null,
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
  return NextResponse.json(MOCK_LEDGER, {
    headers: { 'Cache-Control': 'no-store' },
  });
}
