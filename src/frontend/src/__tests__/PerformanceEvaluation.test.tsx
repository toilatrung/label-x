import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import { PerformanceBody, PerformanceHeader } from '@/components/calibration/PerformanceView';
import { NOT_CONNECTED_MESSAGE } from '@/components/ui/NotConnectedNotice';
import { installMockAuthApi } from './helpers/mock-api';

const { replace, searchParamsState } = vi.hoisted(() => ({ replace: vi.fn(), searchParamsState: { current: 'evaluation=5' } }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
  usePathname: () => '/calibration/performance',
  useSearchParams: () => new URLSearchParams(searchParamsState.current),
}));

const metric = (value: number | null, sample: number, method: string, status = value === null ? 'not_checked' : 'computed') =>
  ({ status, value, sample_size: sample, denominator: sample, method, confidence_interval: null });
// Shape theo backend runs/kpi_views.py (_evaluation_read, ReportView) và contract Evaluation/EffectivenessReport.
const metrics = {
  'KPI-1': metric(null, 40, 'gt_payload_not_stored'), 'KPI-2': metric(null, 40, 'gt_payload_not_stored'),
  'KPI-2b': metric(null, 40, 'gt_payload_not_stored'), 'G-1': metric(null, 40, 'gt_payload_not_stored'),
  'G-2': metric(0, 40, 'open_critical_count'), 'G-3': metric(0.925, 40, 'reviewer_vs_adjudicator'), 'G-4': metric(0.06, 50, 'random_audit_residual'),
};
const evaluation = { id: 5, status: 'completed', snapshot_id: 3, run_id: 107, reference_id: 2, score_version: 'score_v0', experiment_id: null,
  parameters: { e_min: 30 }, metrics, leakage_check: 'not_checked', created_by: 2, created_at: '2026-10-12T00:00:00Z' };
const report = { id: 5, input_snapshot_id: 3, reference_id: 2, source_run_id: 107, source_reason: 'no_valid_final', score_version: 'score_v0', metrics,
  risk_queue: { frames_ranked: 100, frames_reviewed: 80, open_issues: 20 }, random_queue: { frames_ranked: 50, frames_reviewed: 50, open_issues: 3 },
  engine_coverage: [] };
const run107 = { id: 107, snapshot_id: 3, config_version_id: 2, seed: 1, status: 'completed', is_final: false, origin_run_id: null,
  score_version: 'score_v0', model_artifact: null, engines: [], created_by: 2, created_at: '2026-10-10T00:00:00Z', finished_at: '2026-10-10T00:10:00Z' };

async function setup(username: string, search: string, options: { reportFailsOnce?: boolean } = {}) {
  searchParamsState.current = search;
  replace.mockClear();
  const api = installMockAuthApi(); await api.signIn(username);
  const original = api.fetchSpy.getMockImplementation()!;
  const calls: Request[] = [];
  let reportCalls = 0;
  api.fetchSpy.mockImplementation(async (request) => {
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/auth/')) return original(request);
    calls.push(request);
    if (path === '/api/evaluations/5/') return Response.json(evaluation);
    if (path === '/api/reports/5/') {
      reportCalls += 1;
      if (options.reportFailsOnce && reportCalls === 1) return Response.json({ code: 'NOT_FOUND', message: 'x' }, { status: 404 });
      return Response.json(report);
    }
    if (path === '/api/runs/107/') return Response.json(run107);
    if (path === '/api/evaluations/' && request.method === 'POST') return Response.json({ ...evaluation, id: 9 }, { status: 202 });
    // B-6: danh sách KPI evaluation và reference đã khoá của Dataset đang chọn.
    if (path === '/api/evaluations/') return Response.json({ next: null, previous: null, results: [
      { ...evaluation, id: 8, run_id: 108, reference_id: 4, created_at: '2026-10-13T00:00:00Z' }, evaluation] });
    if (path === '/api/references/') return Response.json({ next: null, previous: null, results: [
      { id: 4, snapshot_id: 3, gt_checksum: 'b'.repeat(64), mapping_version: 'map-v2', status: 'locked', created_by: 2 },
      { id: 2, snapshot_id: 3, gt_checksum: 'a'.repeat(64), mapping_version: 'map-v1', status: 'locked', created_by: 2 }] });
    throw new Error(`Unexpected API path: ${path}`);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AuthProvider><PerformanceHeader /><PerformanceBody /></AuthProvider></QueryClientProvider>);
  return { calls };
}

describe('Performance Evaluation on KPI evaluation + effectiveness report', () => {
  it('shows G-3 and G-4 from the server and the random/risk streams separately', async () => {
    const { calls } = await setup('qalead', 'evaluation=5');
    expect(await screen.findByText('92.5%')).toBeTruthy();
    expect(screen.getByText('6.0%')).toBeTruthy();
    expect(screen.getByText(/So với adjudicator trên 40 case/)).toBeTruthy();
    expect(screen.getByText(/Từ 50 frame kiểm tra ngẫu nhiên/)).toBeTruthy();
    const random = (await screen.findByText('Kiểm tra ngẫu nhiên')).closest('tr')!;
    expect(within(random).getByText('3')).toBeTruthy();
    const risk = screen.getByText('Lấy mẫu theo rủi ro').closest('tr')!;
    expect(within(risk).getByText('25.0%')).toBeTruthy();
    expect((screen.getByLabelText('Phạm vi đánh giá') as HTMLSelectElement).textContent).toContain('#QC-107');
    expect(screen.getByText('Completed')).toBeTruthy();
    expect(calls.some((r) => new URL(r.url).pathname === '/api/reports/5/' && new URL(r.url).searchParams.get('format') === 'json')).toBe(true);
  });

  it('keeps regions without API as labelled sample data with the notice', async () => {
    await setup('qalead', 'evaluation=5');
    await screen.findByText('92.5%');
    expect(screen.getByText('87.5%')).toBeTruthy();
    expect(screen.getAllByText('Dữ liệu minh họa').length).toBe(4);
    expect(screen.getAllByRole('status').filter((n) => n.textContent?.includes(NOT_CONNECTED_MESSAGE))).toHaveLength(3);
  });

  it('shows an empty state without an evaluation and creates one through POST /api/evaluations/', async () => {
    const { calls } = await setup('qalead', '');
    expect(screen.getByText('Chọn evaluation để xem kết quả theo luồng lấy mẫu.')).toBeTruthy();
    expect(screen.queryByText('92.5%')).toBeNull();
    fireEvent.change(await screen.findByLabelText('Quality Control Run'), { target: { value: '107' } });
    await waitFor(() => expect((screen.getByLabelText('Reference đã khoá') as HTMLSelectElement).options).toHaveLength(3));
    fireEvent.change(screen.getByLabelText('Reference đã khoá'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('Score version'), { target: { value: 'score_v0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Chạy đánh giá' }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/calibration/performance?evaluation=9'));
    const post = calls.find((r) => r.method === 'POST' && new URL(r.url).pathname === '/api/evaluations/')!;
    expect(post.headers.get('Idempotency-Key')).toBeTruthy();
    expect(await post.clone().json()).toEqual({ snapshot_id: 3, run_id: 107, reference_id: 2, score_version: 'score_v0', parameters: {} });
  });

  it('lists the dataset evaluations and locked references in the scope selects (B-6)', async () => {
    const { calls } = await setup('qalead', 'evaluation=5');
    const scope = await screen.findByLabelText('Phạm vi đánh giá') as HTMLSelectElement;
    await waitFor(() => expect(scope.disabled).toBe(false));
    const list = calls.find((r) => new URL(r.url).pathname === '/api/evaluations/' && r.method === 'GET')!;
    expect(new URL(list.url).searchParams.get('dataset_id')).toBeTruthy();
    const references = calls.find((r) => new URL(r.url).pathname === '/api/references/')!;
    expect(new URL(references.url).searchParams.get('status')).toBe('locked');
    // Reference của evaluation đang xem lọc danh sách phạm vi.
    const benchmark = screen.getByLabelText('Benchmark') as HTMLSelectElement;
    await waitFor(() => expect(benchmark.value).toBe('2'));
    expect([...scope.options].map((o) => o.value)).toEqual(['', '5']);
    fireEvent.change(benchmark, { target: { value: '4' } });
    expect(replace).toHaveBeenCalledWith('/calibration/performance?evaluation=8');
    fireEvent.change(benchmark, { target: { value: '' } });
    await waitFor(() => expect([...scope.options].map((o) => o.value)).toEqual(['', '8', '5']));
    fireEvent.change(scope, { target: { value: '8' } });
    expect(replace).toHaveBeenLastCalledWith('/calibration/performance?evaluation=8');
  });

  it('picks the reference for a new evaluation from the locked list', async () => {
    await setup('qalead', '');
    const select = await screen.findByLabelText('Reference đã khoá') as HTMLSelectElement;
    await waitFor(() => expect(select.options).toHaveLength(3));
    expect(select.options[1].textContent).toBe('Reference #4 · Snapshot #3 · map-v2');
  });

  it('hides evaluation creation from reviewers', async () => {
    await setup('reviewer', '');
    expect(screen.queryByRole('button', { name: 'Chạy đánh giá' })).toBeNull();
  });

  it('shows report errors with a retry button', async () => {
    await setup('qalead', 'evaluation=5', { reportFailsOnce: true });
    const alert = await screen.findByRole('alert');
    fireEvent.click(within(alert).getByRole('button', { name: 'Thử lại' }));
    expect(await screen.findByText('25.0%')).toBeTruthy();
  });
});
