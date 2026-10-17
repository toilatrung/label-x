import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ReworkTrackingPage from '@/app/review/rework/page';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/review/rework',
}));

async function setup(username: string) {
  const api = installMockAuthApi();
  await api.signIn(username);
  const original = api.fetchSpy.getMockImplementation()!;
  api.fetchSpy.mockImplementation(async request => {
    const url = new URL(request.url);
    const detail = (id: number, status: 'fix_pending' | 'recheck_pending' | 'resolved') => ({
      id, dataset_id: 1, issue_id: id === 212 ? 61 : 44, frame_id: id === 212 ? 104 : 71,
      annotator_user_id: 5, created_by_user_id: 4, status,
      instruction: 'Sửa annotation trên CVAT', severity: 'critical' as const,
      original_revision: 'rev-1', submitted_revision: status === 'fix_pending' ? null : 'rev-2',
      recheck_run_id: status === 'fix_pending' ? null : 8, due_at: '2026-10-06T00:00:00Z',
      cvat_deep_link: 'https://cvat.example/tasks/1', submitted_at: status === 'fix_pending' ? null : '2026-10-04T00:00:00Z',
      resolved_at: status === 'resolved' ? '2026-10-05T00:00:00Z' : null,
      created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-04T00:00:00Z', round_count: status === 'fix_pending' ? 0 : 1,
      review_state: 'awaiting_followup' as const, timeline: [],
    });
    if (url.pathname === '/api/rework/212/' && request.method === 'GET') return Response.json(detail(212, 'fix_pending'));
    if (url.pathname === '/api/rework/198/' && request.method === 'GET') return Response.json(detail(198, 'recheck_pending'));
    if (url.pathname === '/api/rework/300/' && request.method === 'GET') return Response.json(detail(300, 'fix_pending'));
    if (url.pathname === '/api/rework/212/current-revision/') return Response.json({
      rework_id: 212, cvat_job_id: 77, revision_sha256: 'a'.repeat(64), original_revision: 'rev-1',
      unchanged: false, rework_status: 'fix_pending', read_at: '2026-10-05T00:00:00Z',
    });
    if (url.pathname === '/api/rework/212/submitted/' && request.method === 'POST') return Response.json({
      id: 212, issue_id: 61, annotator_user_id: 5, status: 'recheck_pending', original_revision: 'rev-1',
      submitted_revision: 'a'.repeat(64), recheck_run_id: 9, due_at: '2026-10-06T00:00:00Z', cvat_deep_link: 'https://cvat.example/tasks/1',
    }, { status: 202 });
    if (url.pathname === '/api/rework/198/verify/' && request.method === 'POST') return Response.json({
      id: 198, issue_id: 44, annotator_user_id: 5, status: 'resolved', original_revision: 'rev-1',
      submitted_revision: 'rev-2', recheck_run_id: 8, due_at: '2026-10-05T00:00:00Z', cvat_deep_link: 'https://cvat.example/tasks/1',
    });
    if (url.pathname === '/api/rework/' && request.method === 'POST') return Response.json({
      id: 300, issue_id: 99, annotator_user_id: 5, status: 'fix_pending', original_revision: 'rev-1',
      submitted_revision: null, recheck_run_id: null, due_at: '2026-10-20T00:00:00Z', cvat_deep_link: 'https://cvat.example/tasks/99',
    }, { status: 201 });
    if (url.pathname !== '/api/rework/') return original(request);
    const status = url.searchParams.get('status');
    const rows = status === 'fix_pending' ? [{
      id: 212, dataset_id: 1, issue_id: 61, frame_id: 104, annotator_user_id: 5,
      created_by_user_id: 4, status: 'fix_pending', instruction: 'Đổi nhãn car → truck',
      severity: 'critical', original_revision: 'rev-1', submitted_revision: null,
      recheck_run_id: null, due_at: '2026-10-06T00:00:00Z', cvat_deep_link: 'https://cvat.example/tasks/1',
      submitted_at: null, resolved_at: null, created_at: '2026-10-01T00:00:00Z',
      updated_at: '2026-10-01T00:00:00Z', round_count: 0,
    }] : status === 'recheck_pending' ? [{
      id: 198, dataset_id: 1, issue_id: 44, frame_id: 71, annotator_user_id: 5,
      created_by_user_id: 4, status: 'recheck_pending', instruction: 'Đã đổi nhãn bus → truck',
      severity: 'critical', original_revision: 'rev-1', submitted_revision: 'rev-2',
      recheck_run_id: 8, due_at: '2026-10-05T00:00:00Z', cvat_deep_link: 'https://cvat.example/tasks/1',
      submitted_at: '2026-10-04T00:00:00Z', resolved_at: null, created_at: '2026-10-01T00:00:00Z',
      updated_at: '2026-10-04T00:00:00Z', round_count: 1,
    }] : status === 'resolved' ? [{
      id: 150, dataset_id: 1, issue_id: 12, frame_id: 20, annotator_user_id: 5,
      created_by_user_id: 4, status: 'resolved', instruction: 'Đã đổi nhãn van → car',
      severity: 'medium', original_revision: 'rev-1', submitted_revision: 'rev-2',
      recheck_run_id: 8, due_at: '2026-10-02T00:00:00Z', cvat_deep_link: 'https://cvat.example/tasks/1',
      submitted_at: '2026-10-02T00:00:00Z', resolved_at: '2026-10-03T00:00:00Z',
      created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-03T00:00:00Z', round_count: 1,
    }] : [];
    return Response.json({
      next: null, previous: null, counts: { fix_pending: 5, reopened: 0, recheck_pending: 7, resolved: 74 }, results: rows,
    });
  });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AuthProvider><ReworkTrackingPage /></AuthProvider>
    </QueryClientProvider>,
  );
  return api;
}

describe('Rework Tracking (FE-06)', () => {
  it('renders the design layout with live rework API data', async () => {
    const api = await setup('reviewer');
    expect(await screen.findByRole('heading', { name: 'Rework Tracking' })).toBeDefined();
    expect(screen.getByText('Tổng yêu cầu sửa')).toBeDefined();
    expect(await screen.findByText('86.0%')).toBeDefined();
    expect(screen.getByText('74 / 86 yêu cầu đã đóng')).toBeDefined();
    expect(await screen.findByText('RW-0212')).toBeDefined();
    fireEvent.click(screen.getByRole('tab', { name: /Chờ xác minh/ }));
    expect(await screen.findByText('RW-0198')).toBeDefined();
    fireEvent.click(screen.getByRole('tab', { name: /Đã đóng/ }));
    expect(await screen.findByText('RW-0150')).toBeDefined();
    expect(api.fetchSpy.mock.calls.some(([r]) => new URL(r.url).pathname.startsWith('/api/rework'))).toBe(true);
  });

  it('allows annotators to see their assigned rework without create permission', async () => {
    const api = await setup('annotator');
    expect(await screen.findByRole('heading', { name: 'Rework Tracking' })).toBeDefined();
    expect(await screen.findByText('RW-0212')).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Tạo rework' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Chi tiết' }));
    expect(await screen.findByRole('heading', { name: 'Chi tiết RW-0212' })).toBeDefined();
    fireEvent.click(await screen.findByRole('button', { name: 'Đọc revision hiện tại' }));
    expect(await screen.findByText('a'.repeat(64))).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận đã sửa' }));
    await waitFor(() => expect(api.fetchSpy.mock.calls.some(([request]) =>
      new URL(request.url).pathname === '/api/rework/212/submitted/' && request.method === 'POST')).toBe(true));
  });

  it('creates and verifies rework with idempotency headers', async () => {
    const api = await setup('reviewer');
    await screen.findByText('RW-0212');
    fireEvent.click(screen.getByRole('button', { name: 'Tạo rework' }));
    fireEvent.change(screen.getByLabelText('Issue ID *'), { target: { value: '99' } });
    fireEvent.change(screen.getByLabelText('Annotator User ID *'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Việc cần sửa *'), { target: { value: 'Sửa nhãn đối tượng' } });
    fireEvent.change(screen.getByLabelText('Hạn xử lý *'), { target: { value: '2026-10-20T08:00' } });
    fireEvent.change(screen.getByLabelText('Liên kết CVAT *'), { target: { value: 'https://cvat.example/tasks/99' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo yêu cầu sửa' }));
    await waitFor(() => expect(api.fetchSpy.mock.calls.some(([request]) =>
      new URL(request.url).pathname === '/api/rework/' && request.method === 'POST')).toBe(true));
    const createRequest = api.fetchSpy.mock.calls.map(([request]) => request).find(request =>
      new URL(request.url).pathname === '/api/rework/' && request.method === 'POST');
    expect(createRequest?.headers.get('Idempotency-Key')).toBeTruthy();

    fireEvent.click(screen.getByRole('tab', { name: /Chờ xác minh/ }));
    await screen.findByText('RW-0198');
    fireEvent.click(screen.getByRole('button', { name: 'Chi tiết' }));
    expect(await screen.findByRole('heading', { name: 'Chi tiết RW-0198' })).toBeDefined();
    fireEvent.click(await screen.findByRole('button', { name: 'Lưu xác minh' }));
    await waitFor(() => expect(api.fetchSpy.mock.calls.some(([request]) =>
      new URL(request.url).pathname === '/api/rework/198/verify/' && request.method === 'POST')).toBe(true));
    const verifyRequest = api.fetchSpy.mock.calls.map(([request]) => request).find(request =>
      new URL(request.url).pathname === '/api/rework/198/verify/' && request.method === 'POST');
    expect(verifyRequest?.headers.get('Idempotency-Key')).toBeTruthy();
    await expect(verifyRequest?.clone().json()).resolves.toEqual({ passed: true, revision: 'rev-2' });
  });
});
