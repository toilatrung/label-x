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
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AuthProvider><ReworkTrackingPage /></AuthProvider>
    </QueryClientProvider>,
  );
  return api;
}

describe('Rework Tracking (FE-06)', () => {
  it('renders metrics, tabs and sample rows with the not-connected notice, without extra API calls', async () => {
    const api = await setup('reviewer');
    expect(await screen.findByRole('heading', { name: 'Rework Tracking' })).toBeDefined();
    expect(screen.getByText('Tổng yêu cầu sửa')).toBeDefined();
    expect(screen.getByText('86.0%')).toBeDefined();
    expect(screen.getByText('74 / 86 yêu cầu đã đóng')).toBeDefined();
    expect(screen.getByText('Dữ liệu minh họa')).toBeDefined();
    expect(screen.getByRole('status').textContent).toContain('Chức năng vẫn chưa được kết nối với server');
    expect(screen.getByText('RW-0212')).toBeDefined();
    fireEvent.click(screen.getByRole('tab', { name: /Chờ xác minh/ }));
    expect(screen.getByText('RW-0198')).toBeDefined();
    fireEvent.click(screen.getByRole('tab', { name: /Đã đóng/ }));
    expect(screen.getByText('RW-0150')).toBeDefined();
    expect(api.fetchSpy.mock.calls.some(([r]) => new URL(r.url).pathname.startsWith('/api/rework'))).toBe(false);
  });

  it('blocks annotators before rendering the screen', async () => {
    await setup('annotator');
    expect(await screen.findByText('403 - Quyền truy cập bị từ chối')).toBeDefined();
  });
});
