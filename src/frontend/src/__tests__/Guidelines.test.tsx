import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import GuidelinesPage from '@/app/configuration/guidelines/page';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => '/configuration/guidelines',
}));

const RULES_PATH = '/api/guidelines/rules/';
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});
const rule = (rule_id: string, content: string) => ({ rule_id, section: '3.1', content, guideline_version: 'bdd-v1.2' });

// Sign in through the mock auth routes, then answer guideline calls with `handler`.
async function setup(username: string, handler: (url: URL) => Response) {
  const api = installMockAuthApi();
  await api.signIn(username);
  const passthrough = api.fetchSpy.getMockImplementation()!;
  api.fetchSpy.mockImplementation(async (request: Request) => {
    const url = new URL(request.url);
    return url.pathname === RULES_PATH ? handler(url) : passthrough(request);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AuthProvider><GuidelinesPage /></AuthProvider></QueryClientProvider>);
  const ruleCalls = () => api.fetchSpy.mock.calls.map(([request]) => new URL(request.url))
    .filter((url) => url.pathname === RULES_PATH);
  return { api, ruleCalls };
}

describe('Guidelines page', () => {
  it('renders rules and the guideline version returned by the API', async () => {
    await setup('reviewer', () => json({ next: null, previous: null,
      results: [rule('VEH-03', 'Xe bị che khuất vẫn phải gán box.'), rule('PED-01', 'Người đi bộ nhỏ hơn 10px bỏ qua.')] }));
    expect(await screen.findByText('VEH-03')).toBeDefined();
    expect(screen.getByText('Người đi bộ nhỏ hơn 10px bỏ qua.')).toBeDefined();
    expect(screen.getByTestId('guideline-version').textContent).toBe('bdd-v1.2');
    expect(screen.queryByText('Mới nhất')).toBeNull();
    expect(screen.getByText(/2 rule trên trang/)).toBeDefined();
    expect((screen.getByRole('button', { name: 'Trang sau' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows an empty state when no guideline is loaded', async () => {
    await setup('qalead', () => json({ next: null, previous: null, results: [] }));
    expect(await screen.findByText('Chưa có guideline nào được nạp.')).toBeDefined();
    expect(screen.getByTestId('guideline-version').textContent).toBe('—');
  });

  it('shows the API message for a 404 on an unknown version', async () => {
    await setup('qcadmin', (url) => url.searchParams.get('version')
      ? json({ code: 'NOT_FOUND', message: "Guideline version 'v9' không tồn tại.", request_id: 'r1' }, 404)
      : json({ next: null, previous: null, results: [rule('VEH-03', 'Nội dung')] }));
    await screen.findByText('VEH-03');
    fireEvent.change(screen.getByLabelText('Guideline version'), { target: { value: 'v9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lọc' }));
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Không tìm thấy guideline')).toBeDefined();
    expect(within(alert).getByText("Guideline version 'v9' không tồn tại.")).toBeDefined();
    expect(screen.queryByText('VEH-03')).toBeNull();
  });

  it('sends family and class_name filters and resets to the first page', async () => {
    const { ruleCalls } = await setup('admin', (url) => {
      if (url.searchParams.get('family') === 'E2') {
        return json({ next: null, previous: null, results: [rule('CLS-07', 'Xe tải và xe buýt.')] });
      }
      return url.searchParams.get('cursor') === 'p2'
        ? json({ next: null, previous: 'http://x/api/guidelines/rules/?cursor=p1', results: [rule('PED-01', 'Trang hai')] })
        : json({ next: 'http://x/api/guidelines/rules/?cursor=p2', previous: null, results: [rule('VEH-03', 'Trang một')] });
    });
    await screen.findByText('VEH-03');
    fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }));
    expect(await screen.findByText('PED-01')).toBeDefined();
    expect(screen.getByText(/Trang 2/)).toBeDefined();

    fireEvent.change(screen.getByLabelText('Nhóm lỗi'), { target: { value: 'E2' } });
    fireEvent.change(screen.getByLabelText('Tên lớp'), { target: { value: ' truck ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lọc' }));
    expect(await screen.findByText('CLS-07')).toBeDefined();
    const last = ruleCalls().at(-1)!;
    expect(last.searchParams.get('family')).toBe('E2');
    expect(last.searchParams.get('class_name')).toBe('truck');
    expect(last.searchParams.has('cursor')).toBe(false);
    expect(screen.getByText(/Trang 1/)).toBeDefined();
  });

  it('blocks roles that cannot read guidelines before calling the API', async () => {
    const { ruleCalls } = await setup('annotator', () => json({ next: null, previous: null, results: [] }));
    expect(await screen.findByText('403 - Quyền truy cập bị từ chối')).toBeDefined();
    expect(ruleCalls()).toHaveLength(0);
  });
});
