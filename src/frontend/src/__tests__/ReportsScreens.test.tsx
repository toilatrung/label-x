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

// Shape lấy từ GET /api/runs/107/report/ trên backend thật (MBE-03), thêm issue để kiểm thử biểu đồ.
const report107 = {
  run_id: 107, snapshot_id: 3, source_run_id: 107, source_reason: 'no_valid_final', score_version: 'score_v0',
  generated_at: '2026-10-11T18:55:45.658779+07:00',
  metrics: { run_id: 107, status: 'completed', frames_total: 588, frames_reviewed: 0, issues_total: 9,
    issues_by_family: { E2: 6, E1: 3 }, issues_by_state: { confirmed: 2, fix_pending: 1, rejected: 4, pending_review: 2 }, reviewed_ratio: 0 },
  gate: null,
  engine_coverage: [
    { engine: 'duplicate', status: 'checked', required: true, unit: 'frame', total: 588, eligible: 576, excluded: 12, applicability_version: '1.0.0',
      completed: 576, failed: 0, pending: 0, not_checked: 12, not_checked_reasons: { not_applicable: 12 }, coverage: 1 },
    { engine: 'geometry', status: 'checked', required: true, unit: 'frame', total: 588, eligible: 576, excluded: 12, applicability_version: '1.0.0',
      completed: 576, failed: 0, pending: 0, not_checked: 12, not_checked_reasons: { not_applicable: 12 }, coverage: 1 },
    { engine: 'schema', status: 'not_checked', required: true, unit: 'frame', total: 588, eligible: 588, excluded: 0, applicability_version: '1.0.0',
      completed: 0, failed: 0, pending: 0, not_checked: 588, not_checked_reasons: { no_reference: 588 }, coverage: 0 },
  ],
  release_id: null as number | null,
  exports: [] as unknown[],
};
const snapshot3 = { id: 3, dataset_id: 1, status: 'locked', failure_reason: null, revision_hash: 'x', parent_snapshot_id: 2, drift_jobs: [],
  created_by: 1, created_at: '2026-10-11T00:00:00Z',
  jobs: [1, 2, 3].map((j) => ({ cvat_job_id: j, cvat_task_id: j === 3 ? 2 : 1, job_hash: null, assignee_user_id: null, cvat_url: 'http://cvat/x', frames: [] })) };
const release5 = { id: 5, run_id: 107, snapshot_id: 3, config_version_id: 2, version_tag: 'urban-2026-10', status: 'pending', gate_status: 'failed',
  created_by: 3, created_at: '2026-10-12T00:00:00Z', approved_by: null, approved_at: null };
const manifest5 = { release_id: 5, generated_at: '2026-10-12T00:00:00Z', checksum: 'abc123checksum', snapshot_id: 3, run_id: 107, config_version_id: 2,
  guideline_version: 'v1.2', score_version: 'score_v0', gate: null, artifacts: [{ name: 'snapshot', sha256: 'f02a6d000000aaaa', size_bytes: 10 }] };

type Handler = (request: Request, path: string) => Promise<Response | undefined> | Response | undefined;

async function setup(username: string, ui: React.ReactElement, handler: Handler = () => undefined, password = 'password123') {
  searchParamsState.current = 'run=107';
  const api = installMockAuthApi(); await api.signIn(username, password);
  const original = api.fetchSpy.getMockImplementation()!;
  const calls: Request[] = [];
  api.fetchSpy.mockImplementation(async (request) => {
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/auth/')) return original(request);
    calls.push(request);
    const custom = await handler(request, path);
    if (custom) return custom;
    if (path === '/api/datasets/') return Response.json({ next: null, previous: null, results: [{ id: 1, name: 'Urban', cvat_project_id: 31 }] });
    if (path === '/api/runs/') return Response.json({ next: null, previous: null, results: [run107] });
    if (path === '/api/runs/107/gate/') return Response.json(gate107);
    if (path === '/api/runs/107/report/') return Response.json(report107);
    if (path === '/api/snapshots/3/') return Response.json(snapshot3);
    throw new Error(`Unexpected API path: ${path}`);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AuthProvider>{ui}</AuthProvider></QueryClientProvider>);
  return { calls };
}

function setupGate(username: string, options: { gateFailsOnce?: boolean; releaseId?: number | null } = {}) {
  let gateCalls = 0;
  return setup(username, <><QualityGateHeader /><QualityGateBody /></>, async (request, path) => {
    if (path === '/api/runs/107/gate/') {
      gateCalls += 1;
      if (options.gateFailsOnce && gateCalls === 1) return Response.json({ code: 'INTERNAL_ERROR', message: 'x', request_id: 'gate-500' }, { status: 500 });
      return undefined;
    }
    if (path === '/api/runs/107/report/') return Response.json({ ...report107, release_id: options.releaseId ?? null });
    if (path === '/api/waivers/' && request.method === 'POST') {
      const body = await request.clone().json();
      return Response.json({ id: 1, ...body, requested_by: 2, approved_by: null, status: 'pending' }, { status: 201 });
    }
    if (path === '/api/waivers/1/approve/') {
      return Response.json({ code: 'SAME_REQUESTER_APPROVER', message: 'Người duyệt phải khác người đề nghị.', details: {}, request_id: 'r1' }, { status: 403 });
    }
    if (path === '/api/releases/5/approve/' && request.method === 'POST') {
      return Response.json({ code: 'BUSINESS_RULE_UNMET', message: 'Gate chưa đạt.', details: {}, request_id: 'r2' }, { status: 422 });
    }
    return undefined;
  }, username === 'admin' ? '123456' : 'password123');
}

const reportUi = <><QualityReportHeader /><QualityReportBody /></>;

describe('Quality Report on GET /api/runs/{id}/report/', () => {
  it('renders real scope, KPI and issue families without design sample figures', async () => {
    const { calls } = await setup('qalead', reportUi);
    expect(await screen.findByText('588')).toBeTruthy();
    expect(await screen.findByText('2 task · 3 job')).toBeTruthy();
    const metric = (label: string) => screen.getByText(label).closest('.lx-metric')!.textContent;
    await waitFor(() => expect(metric('Coverage')).toContain('Ngưỡng yêu cầu 100%'));
    expect(metric('Coverage')).toContain('66.2%');
    expect(metric('Lỗi đã xác nhận chưa đóng')).toContain('3Trong đó 0 nghiêm trọng'); // confirmed 2 + fix_pending 1
    expect(metric('Rework hoàn thành')).toContain('100.0%');
    expect(screen.getByText('Sai nhãn').closest('.lx-bar')!.textContent).toContain('6');
    expect(screen.getByText('Thiếu object').closest('.lx-bar')!.textContent).toContain('3');
    expect(await screen.findByText(/Urban · Quality Control Run/)).toBeTruthy();
    expect(screen.getByText('Release blocked')).toBeTruthy();
    expect(screen.getByText(/Coverage đã loại khỏi mẫu số/).textContent).toContain('not_applicable 12');
    for (const fake of ['12,500', '92.4%', '#QC-091', 'car → truck', 'Dữ liệu minh họa']) expect(screen.queryByText(fake)).toBeNull();
    expect(calls.some((r) => new URL(r.url).pathname === '/api/runs/107/report/')).toBe(true);
    // Chỉ vùng cặp nhãn bị nhầm chưa có dữ liệu; không phủ cả trang.
    expect(screen.getAllByRole('status').filter((n) => n.textContent?.includes(NOT_CONNECTED_MESSAGE))).toHaveLength(1);
  });

  it('marks class and root-cause tabs as not connected without fake rows', async () => {
    await setup('qalead', reportUi);
    await screen.findByText('588');
    fireEvent.click(screen.getByRole('tab', { name: 'Theo lớp và loại hình' }));
    expect(screen.getByText('Chưa có dữ liệu theo lớp từ server.')).toBeTruthy();
    expect(screen.queryByText('lane marking')).toBeNull();
    fireEvent.click(screen.getByRole('tab', { name: 'Nguyên nhân gốc' }));
    expect(screen.getByText('Chưa có dữ liệu nguyên nhân gốc từ server.')).toBeTruthy();
    expect(screen.queryByText('Phê duyệt GAP-012')).toBeNull();
  });

  it('shows the report error with a retry button', async () => {
    let n = 0;
    await setup('qalead', reportUi, (_r, path) => {
      if (path === '/api/runs/107/report/' && ++n === 1) return Response.json({ code: 'INTERNAL_ERROR', message: 'x', request_id: 'r' }, { status: 500 });
      return undefined;
    });
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('Máy chủ gặp lỗi');
    fireEvent.click(within(alert).getByRole('button', { name: 'Thử lại' }));
    expect(await screen.findByText('588')).toBeTruthy();
  });

  it('requests a real export with an idempotency key and shows the queued status', async () => {
    const exported = { id: 1, run_id: 107, format: 'pdf', status: 'queued', download_url: null, error: null, created_at: '2026-10-14T00:00:00Z', finished_at: null };
    let posted = false;
    const { calls } = await setup('qalead', reportUi, (request, path) => {
      if (path === '/api/runs/107/report/export/' && request.method === 'POST') { posted = true; return Response.json(exported, { status: 202 }); }
      if (path === '/api/runs/107/report/' && posted) return Response.json({ ...report107, exports: [{ ...exported, status: 'completed', download_url: 'http://storage/r.pdf' }] });
      return undefined;
    });
    await screen.findByText('588');
    fireEvent.click(screen.getByRole('button', { name: /Xuất báo cáo/ }));
    expect(screen.getAllByRole('menuitem')).toHaveLength(3);
    fireEvent.click(screen.getByRole('menuitem', { name: /PDF/ }));
    expect(await screen.findByText(/Server đã nhận yêu cầu xuất PDF/)).toBeTruthy();
    const post = calls.find((r) => r.method === 'POST' && new URL(r.url).pathname === '/api/runs/107/report/export/')!;
    expect(post.headers.get('Idempotency-Key')).toBeTruthy();
    expect(await post.clone().json()).toEqual({ format: 'pdf' });
    expect((await screen.findByRole('link', { name: 'Tải xuống' })).getAttribute('href')).toBe('http://storage/r.pdf');
  });

  it('closes the export menu on Escape and on an outside click', async () => {
    await setup('qalead', <><QualityReportHeader /><p>Bên ngoài</p></>);
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
    expect(await screen.findByText(/Server chưa có release chờ duyệt cho run này/)).toBeTruthy();
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

  it('approves the run release through POST /api/releases/{id}/approve/ and surfaces the server rule', async () => {
    const { calls } = await setupGate('admin', { releaseId: 5 });
    await screen.findByText('66.2%');
    const approve = await screen.findByRole('button', { name: 'Phê duyệt phát hành' }) as HTMLButtonElement;
    await waitFor(() => expect(approve.disabled).toBe(false));
    fireEvent.change(screen.getByLabelText(/Ghi chú phê duyệt release/), { target: { value: 'ok' } });
    fireEvent.click(approve);
    expect((await screen.findByText(/Chưa đủ điều kiện thực hiện thao tác/))).toBeTruthy();
    const post = calls.find((r) => r.method === 'POST' && new URL(r.url).pathname === '/api/releases/5/approve/')!;
    expect(post.headers.get('Idempotency-Key')).toBeTruthy();
    expect(await post.clone().json()).toEqual({ note: 'ok' });
    expect(screen.queryByText(/Server đã ghi phê duyệt/)).toBeNull();
  });

  it('keeps approval disabled for a QA Lead even when a release exists', async () => {
    await setupGate('qalead', { releaseId: 5 });
    expect(await screen.findByText('Chỉ Product Owner hoặc Super Admin được phê duyệt phát hành.')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Phê duyệt phát hành' }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('Release History on GET /api/releases/', () => {
  it('shows the real empty state', async () => {
    await setup('qalead', <ReleaseHistoryBody />, (_r, path) => (path === '/api/releases/' ? Response.json({ next: null, previous: null, results: [] }) : undefined));
    expect(await screen.findByText('Chưa có release nào trên server.')).toBeTruthy();
    expect(screen.getByText('Chưa có release để xem manifest.')).toBeTruthy();
    expect(screen.queryByText('Dữ liệu minh họa')).toBeNull();
    expect(screen.queryByText(NOT_CONNECTED_MESSAGE, { exact: false })).toBeNull();
  });

  it('lists releases and loads the manifest of the selected release', async () => {
    const { calls } = await setup('qalead', <ReleaseHistoryBody />, (_r, path) => {
      if (path === '/api/releases/') return Response.json({ next: null, previous: null, results: [release5] });
      if (path === '/api/releases/5/manifest/') return Response.json(manifest5);
      return undefined;
    });
    const row = (await screen.findByText('urban-2026-10')).closest('tr')!;
    expect(row.textContent).toContain('#QC-107');
    expect(row.textContent).toContain('Blocked');
    expect(await screen.findByText('abc123checksum')).toBeTruthy();
    expect(screen.getByText('Manifest · urban-2026-10')).toBeTruthy();
    expect(calls.some((r) => new URL(r.url).pathname === '/api/releases/5/manifest/')).toBe(true);
  });

  it('shows the list error with a retry button', async () => {
    let n = 0;
    await setup('qalead', <ReleaseHistoryBody />, (_r, path) => {
      if (path !== '/api/releases/') return undefined;
      if (++n === 1) return Response.json({ code: 'INTERNAL_ERROR', message: 'x', request_id: 'r' }, { status: 500 });
      return Response.json({ next: null, previous: null, results: [] });
    });
    const alert = await screen.findByRole('alert');
    fireEvent.click(within(alert).getByRole('button', { name: 'Thử lại' }));
    expect(await screen.findByText('Chưa có release nào trên server.')).toBeTruthy();
  });
});
