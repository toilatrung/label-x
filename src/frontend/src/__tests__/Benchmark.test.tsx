import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BenchmarkHeader, BenchmarkBody } from '@/components/calibration/BenchmarkView';

const auth = vi.hoisted(() => ({ role: 'qc_admin', datasetId: 42 as number | null }));
vi.mock('@/lib/auth/auth-context', () => ({ useAuth: () => ({
  session: { user: { id: 7 }, roles: [{ role: auth.role, dataset_id: 42 }] }, datasetId: auth.datasetId,
}) }));
const frames = [
  { id: 101, frame_index: 0, file_name: 'a.jpg', cvat_url: 'http://cvat/tasks/9/jobs/11?frame=0' },
  { id: 105, frame_index: 1, file_name: 'b.jpg', cvat_url: 'http://cvat/tasks/9/jobs/11?frame=1' },
];
const snapshot = { id: 3, dataset_id: 42, status: 'locked', created_at: '2026-10-14T00:00:00Z',
  jobs: [{ cvat_job_id: 11, cvat_task_id: 9, frames }] };
const benchmark = { id: 8, name: 'Chuẩn giao thông', dataset_id: 42, snapshot_id: 3, frame_count: 1,
  status: 'ready', source: 'manual', created_by: 7, created_at: '2026-10-14T00:00:00Z' };

function setup(failFirst = false) {
  let created = false;
  let attempts = 0;
  const posts: { body: unknown; key: string | null }[] = [];
  const fetch = vi.fn(async (request: Request) => {
    const url = new URL(request.url);
    if (url.pathname === '/api/auth/csrf/') return new Response(null, { status: 204 });
    if (url.pathname === '/api/snapshots/') return Response.json({ results: [snapshot], next: null });
    if (url.pathname === '/api/snapshots/3/') return Response.json(snapshot);
    if (url.pathname === '/api/benchmarks/' && request.method === 'GET') {
      expect(url.searchParams.get('dataset_id')).toBe('42');
      return Response.json({ results: created ? [benchmark] : [], next: null });
    }
    if (url.pathname === '/api/benchmarks/' && request.method === 'POST') {
      posts.push({ body: await request.json(), key: request.headers.get('Idempotency-Key') });
      attempts++;
      if (failFirst && attempts === 1) return Response.json({ code: 'VALIDATION_ERROR' }, { status: 500 });
      created = true;
      return Response.json(benchmark, { status: 201 });
    }
    throw new Error(`Unexpected request: ${request.method} ${url.pathname}`);
  });
  vi.stubGlobal('fetch', fetch);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}><BenchmarkHeader /><BenchmarkBody /></QueryClientProvider>);
  return { posts, fetch };
}

beforeEach(() => {
  auth.role = 'qc_admin'; auth.datasetId = 42;
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
});

async function chooseFrame() {
  fireEvent.click(screen.getByRole('button', { name: 'Tạo benchmark' }));
  await screen.findByRole('option', { name: /Snapshot #3/ });
  fireEvent.change(screen.getByLabelText('Tên benchmark'), { target: { value: benchmark.name } });
  fireEvent.change(screen.getByLabelText('Snapshot đã khóa'), { target: { value: '3' } });
  fireEvent.click(await screen.findByRole('checkbox', { name: /Frame 0/ }));
}

describe('Benchmark API integration', () => {
  it('creates selected SnapshotFrame IDs and refreshes the real benchmark list', async () => {
    const { posts } = setup();
    await screen.findByText('Chưa có benchmark trong Dataset này.');
    await chooseFrame();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu benchmark' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(await screen.findByRole('button', { name: `Xem ${benchmark.name}` })).toBeTruthy();
    expect(posts[0].body).toEqual({ name: benchmark.name, dataset_id: 42, snapshot_id: 3, frame_ids: [101] });
    expect(posts[0].key).toBeTruthy();
    expect(screen.queryByText('Benchmark v1.2')).toBeNull();
    expect(screen.getAllByText('Sẵn sàng').length).toBeGreaterThan(0);
  });

  it('keeps the form and reuses the idempotency key when retrying a failed request', async () => {
    const { posts } = setup(true);
    await chooseFrame();
    fireEvent.click(screen.getByRole('button', { name: 'Lưu benchmark' }));
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Máy chủ gặp lỗi. Vui lòng thử lại sau.');
    fireEvent.click(screen.getByRole('button', { name: 'Lưu benchmark' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(posts).toHaveLength(2);
    expect(posts[0]).toEqual(posts[1]);
  });

  it('requires a Dataset and does not call the API without one', () => {
    auth.datasetId = null;
    const { fetch } = setup();
    expect(screen.getByRole('button', { name: 'Tạo benchmark' })).toHaveProperty('disabled', true);
    expect(screen.getByText(/Chọn Dataset trên thanh/)).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('lets QA lead read but not create benchmarks', async () => {
    auth.role = 'qa_lead';
    setup();
    await screen.findByText('Chưa có benchmark trong Dataset này.');
    expect(screen.getByRole('button', { name: 'Tạo benchmark' })).toHaveProperty('disabled', true);
  });
});
