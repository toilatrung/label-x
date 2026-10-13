import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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

  it('blocks annotators before rendering the screen', async () => {
    await setup('annotator');
    expect(await screen.findByText('403 - Quyền truy cập bị từ chối')).toBeDefined();
  });
});
