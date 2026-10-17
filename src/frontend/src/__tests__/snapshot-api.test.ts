import { describe, expect, it, vi } from 'vitest';
import { getDatasetRevisions, getSnapshotRuns, getSnapshots, postSnapshot, safeCvatUrl } from '@/lib/snapshots/api';
import { ApiRequestError } from '@/lib/api/errors';

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

  it('sends the POST when the CSRF endpoint answers 204 with no body (real backend)', async () => {
    const fetch = vi.fn(async (request: Request) => {
      if (new URL(request.url).pathname === '/api/auth/csrf/') return new Response(null, { status: 204 });
      return Response.json({ id: 102, status: 'locked', drift_jobs: [] }, { status: 202 });
    });
    vi.stubGlobal('fetch', fetch);
    expect((await postSnapshot({ dataset_id: 42, scope: { cvat_job_ids: [17] } }, 'request-2')).id).toBe(102);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('reads one snapshot run page by path id and forwards the cursor', async () => {
    const fetch = vi.fn(async (request: Request) => {
      const url = new URL(request.url);
      expect(url.pathname).toBe('/api/snapshots/7/runs/');
      expect(url.searchParams.get('cursor')).toBe('c2');
      return Response.json({ next: null, previous: null, results: [{ id: 9 }] });
    });
    vi.stubGlobal('fetch', fetch);
    expect((await getSnapshotRuns(7, 'c2')).results[0].id).toBe(9);
  });

  it('reads dataset revisions and surfaces the CVAT 502 as an API error', async () => {
    const fetch = vi.fn(async (request: Request) => {
      expect(new URL(request.url).pathname).toBe('/api/datasets/42/revisions/');
      return Response.json({ code: 'BUSINESS_RULE_UNMET', message: 'CVAT', request_id: 'r1' }, { status: 502 });
    });
    vi.stubGlobal('fetch', fetch);
    const error = await getDatasetRevisions(42).catch(e => e);
    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error.status).toBe(502);
  });

  it('rejects unsafe CVAT URLs from a server response', () => {
    expect(safeCvatUrl('javascript:alert(1)')).toBeNull();
    expect(safeCvatUrl('https://cvat.example.test/tasks/1/jobs/2')).toContain('cvat.example.test');
    expect(safeCvatUrl('')).toBeNull();
    expect(safeCvatUrl(null)).toBeNull();
    expect(safeCvatUrl(undefined)).toBeNull();
  });
});
