import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import GuidelinesPage from '@/app/configuration/guidelines/page';
import { AuthProvider } from '@/lib/auth/auth-context';
import { AUTH_EXPIRED_EVENT } from '@/lib/api/client';
import { installMockAuthApi } from './helpers/mock-api';

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace }), usePathname: () => '/configuration/guidelines',
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

  it('shows the common NOT_FOUND message for an unknown version', async () => {
    await setup('qcadmin', (url) => url.searchParams.get('version')
      ? json({ code: 'NOT_FOUND', message: "Guideline version 'v9' không tồn tại.", request_id: 'r1' }, 404)
      : json({ next: null, previous: null, results: [rule('VEH-03', 'Nội dung')] }));
    await screen.findByText('VEH-03');
    fireEvent.change(screen.getByLabelText('Guideline version'), { target: { value: 'v9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lọc' }));
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Không tải được guideline')).toBeDefined();
    expect(within(alert).getByText('Không tìm thấy tài nguyên yêu cầu. Vui lòng kiểm tra thông tin và thử lại.')).toBeDefined();
    expect(screen.queryByText("Guideline version 'v9' không tồn tại.")).toBeNull();
    expect(screen.queryByText('VEH-03')).toBeNull();
  });

  it.each([
    { status: 400, code: 'VALIDATION_ERROR', message: 'Dữ liệu không hợp lệ. Vui lòng kiểm tra và thử lại.' },
    { status: 403, code: 'OUT_OF_SCOPE', message: 'Dataset nằm ngoài phạm vi được cấp quyền của bạn.' },
    { status: 418, code: 'NEW_BACKEND_CODE', message: 'Không thể xử lý yêu cầu. Vui lòng thử lại.' },
  ])('maps guideline $status $code while keeping the authenticated page', async ({ status, code, message }) => {
    const expired = vi.fn();
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    try {
      await setup('reviewer', () => json({ code, message: 'Sensitive backend diagnostic', request_id: 'guideline-client-error' }, status));
      const alert = await screen.findByRole('alert');
      expect(within(alert).getByText(message)).toBeDefined();
      expect(screen.queryByText('Sensitive backend diagnostic')).toBeNull();
      expect(screen.getByRole('heading', { name: 'Models và Guidelines' })).toBeDefined();
      expect(replace).not.toHaveBeenCalled();
      expect(expired).not.toHaveBeenCalled();
    } finally { window.removeEventListener(AUTH_EXPIRED_EVENT, expired); }
  });

  it.each([
    { format: 'JSON', response: () => Response.json({ code: 'NOT_FOUND', message: 'Sensitive server traceback',
      request_id: 'guideline-body-request' }, { status: 500, headers: { 'X-Request-ID': 'guideline-header-request' } }),
      requestId: 'guideline-body-request' },
    { format: 'HTML', response: () => new Response('<h1>Sensitive proxy error</h1>', {
      status: 502, headers: { 'Content-Type': 'text/html', 'X-Request-ID': 'guideline-header-request' },
    }), requestId: 'guideline-header-request' },
  ])('shows a safe server message and trace for a $format guideline failure', async ({ response, requestId }) => {
    await setup('reviewer', response);
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText(`Máy chủ gặp lỗi. Vui lòng thử lại sau. Mã yêu cầu: ${requestId}`)).toBeDefined();
    expect(screen.queryByText(/Sensitive/)).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it('uses the status fallback for malformed guideline error JSON', async () => {
    await setup('reviewer', () => new Response('{', { status: 404, headers: { 'Content-Type': 'application/json' } }));
    expect(within(await screen.findByRole('alert'))
      .getByText('Không tìm thấy tài nguyên yêu cầu. Vui lòng kiểm tra thông tin và thử lại.')).toBeDefined();
    expect(replace).not.toHaveBeenCalled();
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
