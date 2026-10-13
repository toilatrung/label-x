import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';
import { MOCK_CONFIG_VERSIONS } from '../route';

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
  const config = MOCK_CONFIG_VERSIONS.find((c) => c.id === Number(id));

  if (!config) {
    return NextResponse.json(
      { code: 'NOT_FOUND', message: 'Không tìm thấy phiên bản cấu hình.' },
      { status: 404 }
    );
  }

  return NextResponse.json(config, {
    headers: { 'Cache-Control': 'no-store' },
  });
}
