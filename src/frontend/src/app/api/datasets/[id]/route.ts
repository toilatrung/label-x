import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';
import { MOCK_DATASETS } from '@/lib/mock/datasets';

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
  const numId = Number(id);
  const found = MOCK_DATASETS.find((d) => d.id === numId);

  if (!found) {
    return NextResponse.json(
      {
        id: numId,
        name: `Dataset #${numId}`,
        cvat_project_id: numId,
        guideline_version: 'v1.2',
        taxonomy_version: 'v3',
      },
      { headers: { 'Cache-Control': 'no-store' } }
    );
  }

  return NextResponse.json(found, { headers: { 'Cache-Control': 'no-store' } });
}
