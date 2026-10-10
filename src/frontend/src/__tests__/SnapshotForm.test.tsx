import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SnapshotForm } from '@/components/snapshots/SnapshotForm';
import type { CvatTask } from '@/lib/snapshots/api';

const { post, push } = vi.hoisted(() => ({ post: vi.fn(), push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('@/lib/snapshots/api', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/snapshots/api')>()), postSnapshot: post,
}));

const tasks: CvatTask[] = [
  { cvat_task_id: 9, name: 'Day', jobs: [
    { cvat_job_id: 17, assignee_cvat_user_id: 3, frame_count: 12, updated_date: '2026-10-09T07:00:00Z' },
    { cvat_job_id: 18, assignee_cvat_user_id: null, updated_date: '2026-10-09T07:00:00Z' },
  ] },
  { cvat_task_id: 10, name: 'Night', jobs: [
    { cvat_job_id: 22, assignee_cvat_user_id: 4, updated_date: '2026-10-09T07:00:00Z' },
  ] },
];

function show(canCreate = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><SnapshotForm datasetId={42} tasks={tasks}
    canCreate={canCreate} /></QueryClientProvider>);
}

describe('Snapshot create form', () => {
  it('sends selected Task and Job to the real snapshot contract', async () => {
    post.mockResolvedValue({ id: 101, status: 'locked' });
    show();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Chọn Task 9' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Chọn Job 22' }));
    fireEvent.change(screen.getByLabelText('Ghi chú'), { target: { value: '  QA pass  ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo Snapshot' }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post.mock.calls[0][0]).toEqual({ dataset_id: 42,
      scope: { cvat_task_ids: [9], cvat_job_ids: [22] }, note: 'QA pass' });
    expect(typeof post.mock.calls[0][1]).toBe('string');
    await waitFor(() => expect(push).toHaveBeenCalledWith('/analysis?snapshotId=101'));
  });

  it('blocks creation for a read-only QC Admin', () => {
    show(false);
    expect((screen.getByRole('button', { name: 'Tạo Snapshot' }) as HTMLButtonElement).disabled).toBe(true);
    expect(post).not.toHaveBeenCalled();
  });

  it('retries an unknown result with the same body and idempotency key', async () => {
    post.mockRejectedValueOnce(new TypeError('network')).mockResolvedValueOnce({ id: 102, status: 'locked' });
    show();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Chọn Job 17' }));
    fireEvent.click(screen.getByRole('button', { name: 'Tạo Snapshot' }));
    expect(await screen.findByRole('button', { name: 'Gửi lại cùng yêu cầu' })).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Gửi lại cùng yêu cầu' }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(post.mock.calls[1]).toEqual(post.mock.calls[0]);
  });
});
