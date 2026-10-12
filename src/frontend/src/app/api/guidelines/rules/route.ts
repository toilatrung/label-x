import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export const MOCK_GUIDELINE_RULES = [
  {
    rule_id: 'GEO-001',
    version: 'v1.2',
    section: 'Geometry',
    content: 'Bounding box phải nằm trọn trong biên ảnh (sai số cho phép tối đa 2 px).',
  },
  {
    rule_id: 'TAX-003',
    version: 'v1.2',
    section: 'Taxonomy',
    content: 'Vật thể loại car phải có nhãn thuộc tính trạng thái di chuyển (moving / parked).',
  },
  {
    rule_id: 'DUP-001',
    version: 'v1.2',
    section: 'Duplicate',
    content: 'Hai bounding box cùng lớp có IoU >= 0.85 được coi là trùng lặp.',
  },
  {
    rule_id: 'VEH-02',
    version: 'v1.2',
    section: 'Vehicle',
    content: 'Phân loại xe tải (truck) và xe buýt (bus) dựa trên kích thước cabin và số trục bánh.',
  },
  {
    rule_id: 'PED-01',
    version: 'v1.2',
    section: 'Pedestrian',
    content: 'Người đi bộ đang dắt xe đạp được tính vào nhóm người đi bộ (pedestrian).',
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
      results: MOCK_GUIDELINE_RULES,
    },
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}
