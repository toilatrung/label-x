import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

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
    [
      {
        cvat_task_id: 118,
        name: 'T-118 · Urban day',
        jobs: [
          {
            cvat_job_id: 2270,
            assignee_cvat_user_id: 28,
            frame_count: 200,
            updated_date: '2026-10-04T06:40:00Z',
          },
          {
            cvat_job_id: 2271,
            assignee_cvat_user_id: 29,
            frame_count: 200,
            updated_date: '2026-10-04T06:40:00Z',
          },
          {
            cvat_job_id: 2272,
            assignee_cvat_user_id: 30,
            frame_count: 200,
            updated_date: '2026-10-04T06:40:00Z',
          },
        ],
      },
      {
        cvat_task_id: 119,
        name: 'T-119 · Urban night',
        jobs: [
          {
            cvat_job_id: 2273,
            assignee_cvat_user_id: 28,
            frame_count: 3000,
            updated_date: '2026-10-04T06:40:00Z',
          },
          {
            cvat_job_id: 2274,
            assignee_cvat_user_id: 29,
            frame_count: 3000,
            updated_date: '2026-10-04T06:40:00Z',
          },
        ],
      },
      {
        cvat_task_id: 120,
        name: 'T-120 · Urban rain',
        jobs: [
          {
            cvat_job_id: 2275,
            assignee_cvat_user_id: 30,
            frame_count: 2950,
            updated_date: '2026-10-04T06:40:00Z',
          },
          {
            cvat_job_id: 2276,
            assignee_cvat_user_id: 31,
            frame_count: 2950,
            updated_date: '2026-10-04T06:40:00Z',
          },
        ],
      },
    ],
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}
