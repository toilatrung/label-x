import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export async function GET(request: Request) {
  if (!isMockAuth && process.env.NODE_ENV === 'production') {
    return NextResponse.json(
      { code: 'NOT_FOUND', message: 'API mẫu chưa được bật.' },
      { status: 404 }
    );
  }

  const { searchParams } = new URL(request.url);
  const datasetId = Number(searchParams.get('dataset_id')) || 14;

  return NextResponse.json(
    {
      next: null,
      previous: null,
      results: [
        {
          id: 14,
          dataset_id: datasetId,
          status: 'locked',
          revision_hash: 'a91f3c8e9b0d',
          parent_snapshot_id: null,
          drift_jobs: [],
          created_by: 1,
          created_at: '2026-10-04T06:50:00Z',
          locked_at: '2026-10-04T06:50:00Z',
          taxonomy_version: 'v3',
          guideline_version: 'v1.2',
          jobs: [
            {
              cvat_job_id: 2270,
              cvat_task_id: 118,
              job_hash: null,
              assignee_user_id: 28,
              cvat_url: 'https://cvat.example/jobs/2270',
              frames: [
                { frame_index: 0, file_name: 'frame_0.jpg', width: 1920, height: 1080, cvat_url: 'https://cvat.example/frames/0' },
              ],
            },
          ],
        },
      ],
    },
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}
