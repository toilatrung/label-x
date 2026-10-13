import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';
import { MOCK_GUIDELINE_RULES } from '../route';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ rule_id: string }> }
) {
  if (!isMockAuth && process.env.NODE_ENV === 'production') {
    return NextResponse.json(
      { code: 'NOT_FOUND', message: 'API mẫu chưa được bật.' },
      { status: 404 }
    );
  }

  void request;
  const { rule_id } = await params;
  const rule = MOCK_GUIDELINE_RULES.find((r) => r.rule_id.toLowerCase() === rule_id.toLowerCase());

  if (!rule) {
    return NextResponse.json(
      {
        rule_id,
        version: 'v1.2',
        section: 'General',
        content: `Quy tắc chuẩn hướng dẫn kiểm định ${rule_id}.`,
      },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  }

  return NextResponse.json(rule, {
    headers: { 'Cache-Control': 'no-store' },
  });
}
