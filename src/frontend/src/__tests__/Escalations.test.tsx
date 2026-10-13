import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import EscalationsPage from '@/app/escalations/page';
import { installMockAuthApi } from './helpers/mock-api';
import type { EscalationIssue } from '@/lib/escalations/api';

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
  usePathname: () => '/escalations',
}));

const issue: EscalationIssue = {
  id: 42,
  family: 'E2',
  origin: 'reviewer',
  state: 'escalated',
  anchor: {
    kind: 'annotation',
    objects: [],
    rule_id: 'VEH-03',
    bbox: null,
    policy_version: 'anchor-v1',
  },
  n_i: 1,
  q_i: 0.8,
  severity: 'medium',
  rule_ids: ['VEH-03'],
  evidence: [
    {
      engine: 'detector',
      rule_id: 'VEH-03',
      expected: 'car',
      actual: 'truck',
      prediction_bbox: { x1: 10, y1: 20, x2: 30, y2: 40 },
      prediction_class: 'truck',
      confidence: 0.92,
      iou: 0.7,
    },
  ],
  links: [],
  review_decisions: [
    {
      id: 8,
      issue_id: 42,
      actor_user_id: 4,
      actor_role: 'reviewer',
      decision: 'escalate',
      revision: 'sha-review-1',
      reason: 'Không chắc nhãn xe.',
      rule_ids: ['VEH-03'],
      reference_version: 'ref-v1',
      reference_match_status: 'not_matched',
      reference_error_ids: [],
      recorded_at: '2026-10-11T01:00:00Z',
    },
  ],
};

const issuePage2: EscalationIssue = { ...issue, id: 84, review_decisions: [] };

function testQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

describe('Escalations UI (T-039)', () => {
  beforeEach(() => {
    replace.mockClear();
    HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new Event('close')); };
  });

  async function renderPage(
    username = 'qalead',
    customHandler?: (request: Request) => Promise<Response | null>,
  ) {
    const api = installMockAuthApi();
    await api.signIn(username);
    const authFetch = api.fetchSpy.getMockImplementation()!;
    const calls: Request[] = [];

    api.fetchSpy.mockImplementation(async (request: Request) => {
      const url = new URL(request.url);
      if (url.pathname.startsWith('/api/auth/')) return authFetch(request);
      calls.push(request);
      const custom = await customHandler?.(request);
      if (custom) return custom;
      if (url.pathname === '/api/escalations/') {
        if (url.searchParams.get('cursor') === '42') {
          return Response.json({ next: null, previous: null, results: [issuePage2] });
        }
        return Response.json({
          next: 'http://localhost:8000/api/escalations/?cursor=42',
          previous: null,
          results: [issue],
        });
      }
      if (/^\/api\/decision-cases\/\d+\/$/.test(url.pathname)) return Response.json({
        id: Number(url.pathname.split('/')[3]), issue_id: 42, outcome: 'confirm', actor_user_id: 2,
        rule_id: 'VEH-03', correct_label: 'truck', reason: 'Chi tiết từ API', case_version: 'v2',
        created_at: '2026-10-11T03:00:00Z', history: [],
      });
      if (url.pathname === '/api/decision-cases/') return Response.json({ next: null, previous: null, results: [] });
      if (url.pathname === '/api/issues/42/adjudications/') {
        return Response.json({
          id: 91,
          issue_id: 42,
          outcome: 'confirm',
          actor_user_id: 2,
          rule_id: 'VEH-03',
          correct_label: 'car',
          reason: 'Evidence và guideline thống nhất.',
          case_version: 'v2',
          created_at: '2026-10-11T02:00:00Z',
        }, { status: 201 });
      }
      return Response.json({ code: 'NOT_FOUND', message: 'Not found' }, { status: 404 });
    });

    render(
      <QueryClientProvider client={testQueryClient()}>
        <AuthProvider><EscalationsPage /></AuthProvider>
      </QueryClientProvider>,
    );
    const adjudication = await screen.findByRole('tab', { name: /Adjudication/ }).catch(() => null);
    if (adjudication) fireEvent.click(adjudication);
    return { api, calls };
  }

  it('renders API evidence and reviewer decisions, then loads beyond the first page', async () => {
    const { calls } = await renderPage();
    expect(await screen.findByRole('heading', { name: 'Escalations' })).toBeDefined();
    expect(await screen.findByText('QC-00042')).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Mở phân xử' }));
    expect(screen.getByText('detector')).toBeDefined();
    expect(screen.getByText(/Vị trí neo:/)).toBeDefined();
    expect(screen.getByText(/Chính sách neo:/)).toBeDefined();
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toEqual([
      'Engine / Quy tắc', 'Kỳ vọng / Thực tế', 'Dự đoán', 'Độ tin cậy / Intersection over Union']);
    expect(screen.queryByText(/Anchor|Policy|Evidence/)).toBeNull();
    expect(screen.getByText('Thực tế: truck')).toBeDefined();
    expect(screen.getByText('Không chắc nhãn xe.')).toBeDefined();
    expect(screen.getByText(/sha-review-1/)).toBeDefined();

    fireEvent.click(screen.getByRole('button', { name: 'Trang sau' }));
    expect(await screen.findByText('QC-00084')).toBeDefined();
    expect(calls.some((call) => new URL(call.url).searchParams.get('cursor') === '42')).toBe(true);
  });

  it('validates and posts the adjudication contract with an idempotency key', async () => {
    const { calls } = await renderPage();
    await screen.findByText('QC-00042');
    fireEvent.click(screen.getByRole('button', { name: 'Mở phân xử' }));

    fireEvent.change(screen.getByLabelText('Nhãn đúng'), { target: { value: 'car' } });
    fireEvent.change(screen.getByLabelText('Lý do phân xử *'), {
      target: { value: 'Evidence và guideline thống nhất.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu phân xử' }));

    expect(await screen.findByText(/Đã lưu Decision Case #91/)).toBeDefined();
    const request = calls.find((call) => new URL(call.url).pathname === '/api/issues/42/adjudications/');
    expect(request).toBeDefined();
    expect(request?.headers.get('Idempotency-Key')).toBeTruthy();
    await expect(request?.clone().json()).resolves.toEqual({
      outcome: 'confirm',
      rule_id: 'VEH-03',
      correct_label: 'car',
      reason: 'Evidence và guideline thống nhất.',
    });
  });

  it('blocks the same account that escalated before sending adjudication', async () => {
    const ownIssue: EscalationIssue = {
      ...issue,
      review_decisions: [{ ...issue.review_decisions[0], actor_user_id: 2 }],
    };
    const { calls } = await renderPage('qalead', async (request) => {
      if (new URL(request.url).pathname === '/api/escalations/') {
        return Response.json({ next: null, previous: null, results: [ownIssue] });
      }
      return null;
    });

    await screen.findByText('QC-00042');
    fireEvent.click(screen.getByRole('button', { name: 'Mở phân xử' }));
    expect(screen.getByText(/không được tự phân xử/i)).toBeDefined();
    expect((screen.getByRole('button', { name: 'Lưu phân xử' }) as HTMLButtonElement).disabled).toBe(true);
    expect(calls.some((call) => call.method === 'POST')).toBe(false);
  });

  it('surfaces backend RBAC/separation errors with the contract code', async () => {
    await renderPage('qalead', async (request) => {
      if (new URL(request.url).pathname === '/api/issues/42/adjudications/') {
        return Response.json({
          code: 'SAME_REQUESTER_APPROVER',
          message: 'Người phân xử không được là người đã chuyển cấp.',
          request_id: 'req-t039-403',
        }, { status: 403 });
      }
      return null;
    });

    await screen.findByText('QC-00042');
    fireEvent.click(screen.getByRole('button', { name: 'Mở phân xử' }));
    fireEvent.change(screen.getByLabelText('Lý do phân xử *'), { target: { value: 'Đủ bằng chứng.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu phân xử' }));
    expect(await screen.findByText(/SAME_REQUESTER_APPROVER/)).toBeDefined();
    expect(screen.getByText(/Người duyệt phải khác người yêu cầu/)).toBeDefined();
  });

  it('maps the approved guideline_gap outcome to the current T-038 wire value', async () => {
    const { calls } = await renderPage('qalead', async (request) => {
      if (new URL(request.url).pathname === '/api/issues/42/adjudications/') {
        return Response.json({
          id: 92,
          issue_id: 42,
          outcome: 'guideline_gap',
          actor_user_id: 2,
          rule_id: 'VEH-03',
          correct_label: null,
          reason: 'Guideline chưa bao phủ tình huống này.',
          case_version: 'v3',
          created_at: '2026-10-11T02:30:00Z',
        }, { status: 201 });
      }
      return null;
    });

    await screen.findByText('QC-00042');
    fireEvent.click(screen.getByRole('button', { name: 'Mở phân xử' }));
    fireEvent.click(screen.getByLabelText('Guideline còn thiếu'));
    fireEvent.change(screen.getByLabelText('Lý do phân xử *'), {
      target: { value: 'Guideline chưa bao phủ tình huống này.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu phân xử' }));
    expect(await screen.findByText(/Đã lưu Decision Case #92/)).toBeDefined();

    const request = calls.find((call) => new URL(call.url).pathname === '/api/issues/42/adjudications/');
    expect((await request?.clone().json()).outcome).toBe('guideline_gap');
  });

  it('enforces the page role matrix without issuing data requests', async () => {
    const { calls } = await renderPage('reviewer');
    expect(await screen.findByText('403 - Quyền truy cập bị từ chối')).toBeDefined();
    expect(screen.queryByRole('heading', { name: 'Escalations' })).toBeNull();
    expect(calls).toHaveLength(0);
  });

  it('queries Decision Cases by the requested case version', async () => {
    const { calls } = await renderPage();
    await screen.findByText('QC-00042');
    fireEvent.click(screen.getByRole('button', { name: 'Mở phân xử' }));
    await waitFor(() => expect(calls.some((call) => new URL(call.url).pathname === '/api/decision-cases/')).toBe(true));

    fireEvent.change(screen.getByLabelText('Case version'), { target: { value: 'v2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tra cứu' }));
    await waitFor(() => expect(calls.some((call) => {
      const url = new URL(call.url);
      return url.pathname === '/api/decision-cases/' && url.searchParams.get('version') === 'v2';
    })).toBe(true));
  });

  it('loads Decision Case detail from the dedicated endpoint', async () => {
    const { calls } = await renderPage('qalead', async (request) => {
      if (new URL(request.url).pathname === '/api/decision-cases/') return Response.json({ next: null, previous: null, results: [{
        id: 12, issue_id: 42, outcome: 'confirm', actor_user_id: 2, rule_id: 'VEH-03',
        correct_label: 'truck', reason: 'Kết quả danh sách', case_version: 'v2', created_at: '2026-10-11T03:00:00Z',
      }] });
      return null;
    });
    await screen.findByText('QC-00042');
    fireEvent.click(screen.getByRole('button', { name: 'Mở phân xử' }));
    expect(await screen.findByText('#12')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Chi tiết' }));
    expect(await screen.findByText('Chi tiết từ API')).toBeDefined();
    expect(calls.some(request => new URL(request.url).pathname === '/api/decision-cases/12/')).toBe(true);
  });

  it('requires an override reason for a global Super Admin', async () => {
    await renderPage('admin');
    await screen.findByText('QC-00042');
    fireEvent.click(screen.getByRole('button', { name: 'Mở phân xử' }));
    expect(screen.getByLabelText('Lý do ghi đè *')).toBeDefined();
  });

  it('renders the three-column summary and the locked Sau khi phân xử field (FE-12)', async () => {
    const { calls } = await renderPage();
    await screen.findByText('QC-00042');
    fireEvent.click(screen.getByRole('button', { name: 'Mở phân xử' }));
    expect(screen.getByText('Quyết định của reviewer')).toBeDefined();
    expect(screen.getByText('Hướng dẫn liên quan')).toBeDefined();
    expect(screen.getAllByText('Bằng chứng').length).toBeGreaterThan(0);
    const after = screen.getByLabelText('Sau khi phân xử') as HTMLSelectElement;
    expect(after.disabled).toBe(true);
    expect(calls.some((call) => new URL(call.url).pathname.startsWith('/api/rework'))).toBe(false);
    expect(screen.queryByText(/IoU/)).toBeNull();
  });

  it('uses the real adjudication outcome when creating a Guideline Gap (FE-12)', async () => {
    const { calls } = await renderPage();
    await screen.findByText('QC-00042');
    expect(screen.queryByText('QC-00098')).toBeNull();
    expect(screen.queryByText('Dữ liệu minh họa')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Mở phân xử' }));
    const before = calls.length;
    fireEvent.click(screen.getByRole('button', { name: 'Tạo Guideline Gap' }));
    expect((screen.getByRole('radio', { name: 'Guideline còn thiếu' }) as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByRole('dialog', { name: 'Tạo Guideline Gap' })).toBeNull();
    expect(calls.length).toBe(before);
  });

  it('uses sketchup data for Guideline Gaps and API data for Decision Cases (FE-06)', async () => {
    await renderPage('qalead', async (request) => {
      const url = new URL(request.url);
      if (url.pathname !== '/api/decision-cases/') return null;
      return Response.json({ next: null, previous: null, results: [
        {
          id: 12,
          issue_id: 42,
          outcome: 'guideline_gap',
          actor_user_id: 2,
          rule_id: 'VEH-03',
          correct_label: null,
          reason: 'Xe buýt mini chở hàng thuộc nhãn nào',
          case_version: 'v2',
          created_at: '2026-10-11T02:00:00Z',
        },
        {
          id: 40,
          issue_id: 84,
          outcome: 'confirm',
          actor_user_id: 2,
          rule_id: 'VEH-03',
          correct_label: 'truck',
          reason: 'Xe bán tải có nắp thùng',
          case_version: 'v2',
          created_at: '2026-10-11T03:00:00Z',
        },
      ] });
    });
    fireEvent.click(screen.getByRole('tab', { name: /Guideline Gaps/ }));
    expect(await screen.findByText('GAP-012')).toBeDefined();
    expect(screen.getByRole('button', { name: 'Tạo Guideline Gap' })).toBeDefined();
    expect(screen.queryByText(/chưa được kết nối với server/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Tạo Guideline Gap' }));
    const dialog = screen.getByRole('dialog', { name: 'Tạo Guideline Gap' });
    fireEvent.change(within(dialog).getByLabelText('Quy tắc liên quan *'), { target: { value: 'VEH-03' } });
    fireEvent.change(within(dialog).getByLabelText('Nội dung hướng dẫn còn thiếu *'), { target: { value: 'Tình huống mới từ sketchup' } });
    fireEvent.change(within(dialog).getByLabelText('Lý do / bằng chứng *'), { target: { value: 'Ba case chưa thống nhất' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Tạo Guideline Gap' }));
    expect(await screen.findByText('GAP-013')).toBeDefined();
    expect(screen.getByText('Tình huống mới từ sketchup')).toBeDefined();
    fireEvent.click(screen.getByRole('tab', { name: /Decision Cases/ }));
    expect(await screen.findByText('CASE-040')).toBeDefined();
    expect(screen.getByRole('tab', { name: /Guideline Gaps/ })).toBeDefined();
    expect(screen.getByRole('tab', { name: /Decision Cases/ })).toBeDefined();
    expect(screen.getByRole('tab', { name: /Adjudication/ })).toBeDefined();
  });
});
