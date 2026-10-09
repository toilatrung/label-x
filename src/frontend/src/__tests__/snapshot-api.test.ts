import { describe, expect, it, vi } from 'vitest';
import { getSnapshots, postSnapshot, safeCvatUrl } from '@/lib/snapshots/api';

describe('Snapshot API wiring', () => {
  it('always passes dataset_id to the dataset-scoped history endpoint', async () => {
    const fetch = vi.fn(async (request: Request) => {
      expect(new URL(request.url).searchParams.get('dataset_id')).toBe('42');
      return Response.json({ next: null, previous: null, results: [] });
    });
    vi.stubGlobal('fetch', fetch);
    expect((await getSnapshots(42)).results).toEqual([]);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('prepares CSRF and sends the idempotency key for create', async () => {
    const fetch = vi.fn(async (request: Request) => {
      if (new URL(request.url).pathname === '/api/auth/csrf/') return Response.json({ csrf_token: 'token' });
      expect(request.headers.get('Idempotency-Key')).toBe('request-1');
      expect(await request.json()).toEqual({ dataset_id: 42, scope: { cvat_job_ids: [17] } });
      return Response.json({ id: 101, status: 'locked', drift_jobs: [] }, { status: 202 });
    });
    vi.stubGlobal('fetch', fetch);
    expect((await postSnapshot({ dataset_id: 42, scope: { cvat_job_ids: [17] } }, 'request-1')).id).toBe(101);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('rejects unsafe CVAT URLs from a server response', () => {
    expect(safeCvatUrl('javascript:alert(1)')).toBeNull();
    expect(safeCvatUrl('https://cvat.example.test/tasks/1/jobs/2')).toContain('cvat.example.test');
    expect(safeCvatUrl('')).toBeNull();
    expect(safeCvatUrl(null)).toBeNull();
    expect(safeCvatUrl(undefined)).toBeNull();
  });
});
