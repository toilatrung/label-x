import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GroundTruthUpload } from '@/components/execution/GroundTruthUpload';

const metadata = { dataset_id: 1, filename: 'truth.json', frame_count: 3, box_count: 34,
  deleted_at: null, is_current: true, reference: { id: 9, snapshot_id: 4,
    gt_checksum: 'a'.repeat(64), mapping_version: 'bdd100k-det-10-v1', matching_threshold: 0.5,
    minimum_area: 0, algorithm_version: '1.0.0', status: 'draft', created_by: 2, locked_by: null, locked_at: null } };

function setup(current: unknown = null, userId = 2, failUpload = false) {
  let value = current;
  const calls: Request[] = [];
  const fetchMock = vi.fn(async (request: Request) => {
    calls.push(request);
    const path = new URL(request.url).pathname;
    if (path === '/api/auth/csrf/') return Response.json({});
    if (path === '/api/ground-truth/' && request.method === 'GET') return Response.json(value);
    if (path === '/api/ground-truth/' && request.method === 'POST') {
      if (failUpload) return Response.json({ code: 'VALIDATION_ERROR', message: 'Frame không thuộc Snapshot.' }, { status: 400 });
      value = metadata;
      return Response.json(metadata, { status: 201 });
    }
    if (path === '/api/ground-truth/9/preview/') return Response.json({ reference_id: 9, frames: [{ cvat_task_id: 9, frame_number: 0, boxes: [] }] });
    if (path === '/api/references/9/lock/') {
      value = { ...metadata, reference: { ...metadata.reference, status: 'locked', locked_by: userId } };
      return Response.json((value as typeof metadata).reference);
    }
    throw new Error(`Unexpected ${request.method} ${path}`);
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={queryClient}><GroundTruthUpload datasetId={1} snapshotId={4}
    userId={userId} enabled busy={false} /></QueryClientProvider>);
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe('temporary Ground Truth upload', () => {
  it('uploads a real multipart file and preserves its snapshot and idempotency key', async () => {
    const set = vi.spyOn(FormData.prototype, 'set');
    const calls = setup();
    await screen.findByText('Chưa upload Ground Truth cho Dataset này.');
    fireEvent.change(screen.getByLabelText('Upload Ground Truth'), { target: { files: [new File(['{"frames":[]}'], 'truth.json', { type: 'application/json' })] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload Ground Truth' }));
    await screen.findByText('Chờ QA Lead khác người upload duyệt Ground Truth.');
    const post = calls.find((r) => r.method === 'POST' && r.url.endsWith('/api/ground-truth/'))!;
    const form = await post.clone().formData();
    expect(form.get('snapshot_id')).toBe('4');
    expect(form.get('mapping_version')).toBe('bdd100k-det-10-v1');
    // jsdom File crosses into Node's Request parser; assert the browser FormData input.
    expect(set).toHaveBeenCalledWith('file', expect.any(File), 'truth.json');
    expect(form.get('file')).toBeTruthy();
    expect(post.headers.get('Idempotency-Key')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Duyệt Ground Truth' })).toBeNull();
  });

  it('requires preview before another QA Lead approves', async () => {
    const calls = setup(metadata, 3);
    const approve = await screen.findByRole('button', { name: 'Duyệt Ground Truth' });
    expect((approve as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Xem Ground Truth' }));
    await waitFor(() => expect((approve as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(approve);
    await screen.findByText('Ground Truth đã duyệt, sẵn sàng chạy.');
    expect(calls.some((r) => r.method === 'POST' && r.url.endsWith('/api/references/9/lock/'))).toBe(true);
  });

  it('shows reupload guidance after cleanup and hides preview and approval', async () => {
    setup({ ...metadata, deleted_at: '2026-10-14T00:00:00Z' }, 3);
    await screen.findByText('File đã xóa sau khi chạy thành công. Chạy lại cần upload lại.');
    expect(screen.queryByRole('button', { name: 'Xem Ground Truth' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Duyệt Ground Truth' })).toBeNull();
  });

  it('keeps a validation failure visible without claiming success', async () => {
    setup(null, 2, true);
    await screen.findByText('Chưa upload Ground Truth cho Dataset này.');
    fireEvent.change(screen.getByLabelText('Upload Ground Truth'), { target: { files: [new File(['{}'], 'bad.json')] } });
    fireEvent.click(screen.getByRole('button', { name: 'Upload Ground Truth' }));
    await screen.findByRole('alert');
    expect(screen.queryByText('Ground Truth đã duyệt, sẵn sàng chạy.')).toBeNull();
  });
});
