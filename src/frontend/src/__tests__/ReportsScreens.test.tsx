import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import { QualityReportBody, QualityReportHeader } from '@/components/reports/QualityReportView';
import { QualityGateBody, QualityGateHeader } from '@/components/reports/QualityGateView';
import { ReleaseHistoryBody } from '@/components/reports/ReleaseHistoryView';
import { NOT_CONNECTED_MESSAGE } from '@/components/ui/NotConnectedNotice';
import { installMockAuthApi } from './helpers/mock-api';

const { replace, searchParamsState } = vi.hoisted(() => ({ replace: vi.fn(), searchParamsState: { current: 'run=107' } }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
  usePathname: () => '/reports/gate',
  useSearchParams: () => new URLSearchParams(searchParamsState.current),
}));

// Shape lấy từ GET /api/runs/107/gate/ trên backend thật (MBE-01).
const gate107 = {
  run_id: 107, source_run_id: 107, source_reason: 'no_valid_final', status: 'failed',
  conditions: [
    { name: 'coverage', status: 'failed', observed: 0.6620689655172414, threshold: 1.0, waiver_id: null, reason: 'no_valid_final' },
    { name: 'open_critical_issues', status: 'passed', observed: 0.0, threshold: 0.0, waiver_id: null, reason: null },
    { name: 'rework_verified', status: 'passed', observed: 1.0, threshold: 1.0, waiver_id: null, reason: null },
    { name: 'residual', status: 'not_checked', observed: null, threshold: 0.05, waiver_id: null, reason: null },
    { name: 'agreement', status: 'not_checked', observed: null, threshold: 0.9, waiver_id: null, reason: null },
  ],
};
const run107 = { id: 107, snapshot_id: 3, config_version_id: 2, seed: 1, status: 'completed', is_final: false, origin_run_id: null,
  score_version: 'score_v0', model_artifact: null, engines: [], created_by: 2, created_at: '2026-10-10T00:00:00Z', finished_at: '2026-10-10T00:10:00Z' };

async function setupGate(username: string, options: { gateFailsOnce?: boolean } = {}) {
  searchParamsState.current = 'run=107';
  const api = installMockAuthApi(); await api.signIn(username);
  const original = api.fetchSpy.getMockImplementation()!;
  const calls: Request[] = [];
  let gateCalls = 0;
  api.fetchSpy.mockImplementation(async (request) => {
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/auth/')) return original(request);
    calls.push(request);
    if (path === '/api/datasets/') return Response.json({ next: null, previous: null, results: [{ id: 1, name: 'Urban', cvat_project_id: 31 }] });
    if (path === '/api/runs/') return Response.json({ next: null, previous: null, results: [run107] });
    if (path === '/api/runs/107/gate/') {
      gateCalls += 1;
      if (options.gateFailsOnce && gateCalls === 1) return Response.json({ code: 'INTERNAL_ERROR', message: 'x', request_id: 'gate-500' }, { status: 500 });
      return Response.json(gate107);
    }
    if (path === '/api/waivers/' && request.method === 'POST') {
      const body = await request.clone().json();
      return Response.json({ id: 1, ...body, requested_by: 2, approved_by: null, status: 'pending' }, { status: 201 });
    }
    if (path === '/api/waivers/1/approve/') {
      return Response.json({ code: 'SAME_REQUESTER_APPROVER', message: 'Người duyệt phải khác người đề nghị.', details: {}, request_id: 'r1' }, { status: 403 });
    }
    throw new Error(`Unexpected API path: ${path}`);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AuthProvider><QualityGateHeader /><QualityGateBody /></AuthProvider></QueryClientProvider>);
  return { calls };
}

describe('Quality Report', () => {
  it('labels the design figures as sample data and shows the not-connected notice', () => {
    render(<><QualityReportHeader /><QualityReportBody /></>);
    expect(screen.getByText('12,500')).toBeTruthy();
    expect(screen.getByText('92.4%')).toBeTruthy();
    expect(screen.getAllByText('Dữ liệu minh họa').length).toBeGreaterThan(0);
    expect(screen.getByRole('status').textContent).toContain(NOT_CONNECTED_MESSAGE);
  });
  it('switches tabs and keeps Polyline as not evaluated', () => {
    render(<QualityReportBody />);
    fireEvent.click(screen.getByRole('tab', { name: 'Theo lớp và loại hình' }));
    const row = screen.getByText('lane marking').closest('tr')!;
    expect(within(row).getAllByText('—').length).toBe(3);
    fireEvent.click(screen.getByRole('tab', { name: 'Nguyên nhân gốc' }));
    expect(screen.getByText('Phê duyệt GAP-012')).toBeTruthy();
  });
  it('blocks export with the not-connected notice instead of reporting success', () => {
    render(<QualityReportHeader />);
    fireEvent.click(screen.getByRole('button', { name: /Xuất báo cáo/ }));
    expect(screen.getAllByRole('menuitem')).toHaveLength(3);
    fireEvent.click(screen.getByRole('menuitem', { name: /PDF/ }));
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.getByRole('status').textContent).toContain(NOT_CONNECTED_MESSAGE);
    expect(screen.queryByText(/thành công/i)).toBeNull();
  });
  it('closes the export menu on Escape and on an outside click', () => {
    render(<><QualityReportHeader /><p>Bên ngoài</p></>);
    const trigger = screen.getByRole('button', { name: /Xuất báo cáo/ });
    fireEvent.click(trigger);
    expect(screen.getByRole('menu')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    fireEvent.click(trigger);
    fireEvent.mouseDown(screen.getByText('Bên ngoài'));
    expect(screen.queryByRole('menu')).toBeNull();
  });
});

describe('Quality Gate on GET /api/runs/{id}/gate/', () => {
  it('renders the server conditions, overall badge and source run reason', async () => {
    const { calls } = await setupGate('qalead');
    expect(await screen.findByText('66.2%')).toBeTruthy();
    expect(screen.getAllByRole('row')).toHaveLength(6);
    expect(screen.getByText('2 đạt · 1 chưa đạt · 2 chưa kiểm tra')).toBeTruthy();
    expect(screen.getByText('Blocked')).toBeTruthy();
    expect(screen.getByText(/Gate tính theo run/).textContent).toContain('Chưa có run cuối đủ điều kiện');
    expect(screen.getAllByText('Not checked')).toHaveLength(2);
    expect(screen.queryByText('Toàn vẹn phiên bản')).toBeNull();
    expect((screen.getByRole('button', { name: 'Phê duyệt phát hành' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByRole('status').some((n) => n.textContent?.includes(NOT_CONNECTED_MESSAGE))).toBe(true);
    expect(calls.some((r) => new URL(r.url).pathname === '/api/runs/107/gate/')).toBe(true);
  });

  it('sends a real waiver request with idempotency key and only offers waivable conditions', async () => {
    const { calls } = await setupGate('qalead');
    await screen.findByText('66.2%');
    const select = screen.getByLabelText('Điều kiện') as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(['coverage', 'agreement']);
    const send = screen.getByRole('button', { name: 'Gửi xin waiver' }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Lý do (bắt buộc)'), { target: { value: 'Coverage thiếu do job lỗi' } });
    fireEvent.change(screen.getByLabelText('Bằng chứng (bắt buộc)'), { target: { value: 'link log' } });
    fireEvent.click(send);
    expect(await screen.findByText(/Server đã ghi waiver/)).toBeTruthy();
    const post = calls.find((r) => r.method === 'POST' && new URL(r.url).pathname === '/api/waivers/')!;
    expect(post.headers.get('Idempotency-Key')).toBeTruthy();
    const body = await post.clone().json();
    expect(body).toMatchObject({ run_id: 107, condition: 'coverage', reason: 'Coverage thiếu do job lỗi', evidence: 'link log' });
    expect(typeof body.expires_at).toBe('string');
  });

  it('surfaces the server rule when the approver is the requester', async () => {
    await setupGate('qalead');
    await screen.findByText('66.2%');
    fireEvent.change(screen.getByLabelText('Mã waiver'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText('Lý do quyết định (bắt buộc)'), { target: { value: 'ok' } });
    fireEvent.click(screen.getByRole('button', { name: 'Duyệt waiver' }));
    expect((await screen.findByRole('alert')).textContent).toContain('Người duyệt phải khác người yêu cầu');
    expect(screen.queryByText(/Server đã ghi quyết định/)).toBeNull();
  });

  it('hides waiver approval for reviewers (contract: qa_lead only)', async () => {
    await setupGate('reviewer');
    await screen.findByText('66.2%');
    expect(screen.queryByRole('button', { name: 'Duyệt waiver' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Gửi xin waiver' })).toBeTruthy();
  });

  it('shows the error with a retry button', async () => {
    await setupGate('qalead', { gateFailsOnce: true });
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Máy chủ gặp lỗi');
    fireEvent.click(within(alert).getByRole('button', { name: 'Thử lại' }));
    await waitFor(() => expect(screen.getByText('66.2%')).toBeTruthy());
  });
});

describe('Release History', () => {
  it('keeps the sample releases labelled and blocked behind the not-connected notice', () => {
    render(<ReleaseHistoryBody />);
    expect(screen.getByText('Road Vision Urban v1.4').closest('tr')!.textContent).toContain('Blocked');
    expect(screen.getByText('Manifest · v1.3')).toBeTruthy();
    expect(screen.getAllByText('Dữ liệu minh họa')).toHaveLength(2);
    expect(screen.getAllByRole('status')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Tải manifest (JSON)' }));
    expect(screen.getAllByRole('status')[1].textContent).toContain('Tải manifest');
    expect(screen.queryByText(/thành công/i)).toBeNull();
  });
});
