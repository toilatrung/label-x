import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RulesThresholdsPage from '@/app/configuration/rules-thresholds/page';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
  usePathname: () => '/configuration/rules-thresholds',
}));

const MAPPINGS_PATH = '/api/guidelines/mappings/';
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const mapping = (
  error_group: string,
  class_name: string,
  paired_class: string,
  rule_id: string,
  guideline_version = 'v1.0'
) => ({
  error_group,
  class_name,
  paired_class,
  rule_id,
  guideline_version,
});

async function setup(username: string, handler: (url: URL) => Response) {
  const api = installMockAuthApi();
  await api.signIn(username);
  const passthrough = api.fetchSpy.getMockImplementation()!;
  api.fetchSpy.mockImplementation(async (request: Request) => {
    const url = new URL(request.url);
    return url.pathname === MAPPINGS_PATH ? handler(url) : passthrough(request);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <RulesThresholdsPage />
      </AuthProvider>
    </QueryClientProvider>
  );
  const mappingCalls = () =>
    api.fetchSpy.mock.calls
      .map(([request]) => new URL(request.url))
      .filter((url) => url.pathname === MAPPINGS_PATH);
  return { api, mappingCalls };
}

describe('Rules & Thresholds page (T-017)', () => {
  it('renders mapping table returned by API and displays all fields', async () => {
    await setup('reviewer', () =>
      json({
        next: null,
        previous: null,
        results: [
          mapping('E2', 'car', 'truck', 'RULE-01', 'bdd-v1'),
          mapping('E1', 'pedestrian', '', 'RULE-02', 'bdd-v1'),
        ],
      })
    );

    expect(await screen.findByText('RULE-01')).toBeDefined();
    expect(screen.getByText('Rules và Thresholds')).toBeDefined();
    expect(screen.getByText('RULE-02')).toBeDefined();
    expect(screen.getByText('car')).toBeDefined();
    expect(screen.getByText('truck')).toBeDefined();
    expect(screen.getByText('pedestrian')).toBeDefined();
    expect(screen.getByText(/2 mapping trên trang/)).toBeDefined();

    // Xác nhận không có bất kỳ nút hoặc điều khiển sửa/xóa nào
    expect(screen.queryByRole('button', { name: /sửa|chỉnh sửa|edit|xoá|xóa|delete/i })).toBeNull();
    expect(screen.getByText('Chỉ đọc')).toBeDefined();
  });

  it('shows empty state when no mapping is available', async () => {
    await setup('qcadmin', () => json({ next: null, previous: null, results: [] }));
    expect(await screen.findByText('Chưa có mapping guideline.')).toBeDefined();
    expect(screen.getByText(/0 mapping trên trang/)).toBeDefined();
  });

  it('handles pagination: next button fetches next page with cursor and previous button returns', async () => {
    const { mappingCalls } = await setup('reviewer', (url) => {
      const cursor = url.searchParams.get('cursor');
      if (cursor === 'page-2-token') {
        return json({
          next: null,
          previous: 'http://localhost/api/guidelines/mappings/?cursor=page-1-token',
          results: [mapping('structural', 'bus', '', 'RULE-51', 'bdd-v1')],
        });
      }
      return json({
        next: 'http://localhost/api/guidelines/mappings/?cursor=page-2-token',
        previous: null,
        results: [mapping('E1', 'car', '', 'RULE-01', 'bdd-v1')],
      });
    });

    // Trang 1
    expect(await screen.findByText('RULE-01')).toBeDefined();
    expect(screen.getByText(/Trang 1/)).toBeDefined();
    const nextBtn = screen.getByRole('button', { name: 'Trang sau' }) as HTMLButtonElement;
    const prevBtn = screen.getByRole('button', { name: 'Trang trước' }) as HTMLButtonElement;
    expect(nextBtn.disabled).toBe(false);
    expect(prevBtn.disabled).toBe(true);

    // Bấm Trang sau
    fireEvent.click(nextBtn);
    expect(await screen.findByText('RULE-51')).toBeDefined();
    expect(screen.getByText(/Trang 2/)).toBeDefined();
    expect(nextBtn.disabled).toBe(true);
    expect(prevBtn.disabled).toBe(false);

    // Bấm Trang trước
    fireEvent.click(prevBtn);
    expect(await screen.findByText('RULE-01')).toBeDefined();
    expect(screen.getByText(/Trang 1/)).toBeDefined();

    expect(mappingCalls().length).toBeGreaterThanOrEqual(2);
  });

  it('shows error alert when mapping API fails', async () => {
    await setup('reviewer', () =>
      json({ code: 'SERVER_ERROR', message: 'Internal Server Error' }, 500)
    );
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Không tải được mapping')).toBeDefined();
  });

  it('blocks unauthorized roles (annotator) via AuthGuard before calling API', async () => {
    const { mappingCalls } = await setup('annotator', () =>
      json({ next: null, previous: null, results: [] })
    );
    expect(await screen.findByText('403 - Quyền truy cập bị từ chối')).toBeDefined();
    expect(mappingCalls()).toHaveLength(0);
  });
});
