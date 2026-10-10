import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import ExecutionHistoryPage from '@/app/analysis/history/page';
import AnalysisConfigPage from '@/app/analysis/config/page';
import { installMockAuthApi } from './helpers/mock-api';
import type { Candidate } from '@/lib/execution/api';

const { push, replace, searchParamsState } = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), searchParamsState: { current: 'run=12' } }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push, replace }), usePathname: () => '/analysis/history', useSearchParams: () => new URLSearchParams(searchParamsState.current) }));

const run = { id: 12, snapshot_id: 4, config_version_id: 7, seed: 42, status: 'partial', is_final: false, origin_run_id: null,
  score_version: 'v1', model_artifact: null, engines: [{ engine: 'duplicate', status: 'partial', reason: null, failed_units: 1 },
    { engine: 'geometry', status: 'not_checked', reason: 'disabled', failed_units: 0 }], created_by: 2, created_at: '2026-10-09T00:00:00Z', finished_at: null };
const run13 = { id: 13, snapshot_id: 4, config_version_id: 7, seed: 99, status: 'completed', is_final: true, origin_run_id: null,
  score_version: 'v1', model_artifact: null, engines: [{ engine: 'duplicate', status: 'completed', reason: null, failed_units: 0 }],
  created_by: 2, created_at: '2026-10-10T00:00:00Z', finished_at: '2026-10-10T00:10:00Z' };
const ledger = [{ engine: 'duplicate', status: 'partial', required: true, unit: 'shape', total: 3, eligible: 2, excluded: 1,
  applicability_version: '2026.10', completed: 1, failed: 1, pending: 0, not_checked: 1, not_checked_reasons: { not_applicable: 1 }, coverage: 0.5 },
  { engine: 'geometry', status: 'not_checked', required: true, unit: 'frame', total: 0, eligible: 0, excluded: 0,
    applicability_version: '1.0.0', completed: 0, failed: 0, pending: 0, not_checked: 0, not_checked_reasons: {}, coverage: null }];

async function setup(
  username: string,
  page: React.ReactNode,
  options: {
    publishFails?: boolean;
    configsOverride?: unknown;
    configsFails?: boolean;
    candidatesOverride?: unknown;
    candidatesFails?: boolean;
  } = {}
) {
  const api = installMockAuthApi(); await api.signIn(username);
  const original = api.fetchSpy.getMockImplementation()!;
  const calls: Request[] = [];
  api.fetchSpy.mockImplementation(async (request) => {
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/auth/')) return original(request);
    calls.push(request);
    if (path === '/api/runs/' && request.method === 'GET') return Response.json({ next: null, previous: null, results: [run, run13] });
    if (path === '/api/runs/12/') return Response.json(run);
    if (path === '/api/runs/13/') return Response.json(run13);
    if (path === '/api/runs/12/ledger/' || path === '/api/runs/13/ledger/') return Response.json(ledger);
    if (path === '/api/runs/12/shards/' || path === '/api/runs/13/shards/') return Response.json({ next: null, previous: null, results: [{ id: 5, engine: 'duplicate', shard_key: 'job:1', shard_index: 0, status: 'failed', attempt: 2, last_error: 'worker timeout' }] });
    if (path === '/api/runs/12/candidates/') {
      if (options.candidatesFails) return Response.json({ code: 'INTERNAL_ERROR', message: 'Lỗi nạp candidate' }, { status: 500 });
      if (options.candidatesOverride !== undefined) return Response.json(options.candidatesOverride);
      return Response.json({
        next: null,
        previous: null,
        raw_count: null,
        dedup_count: 1,
        results: [
          {
            engine: 'detector',
            engine_version: '2.0.0',
            family: 'E2',
            severity: 'medium',
            frame: { cvat_task_id: 9, frame_number: 1 },
            anchor: { kind: 'prediction_region', objects: [{ namespace: 'detector', id: 'd-1' }], policy_version: 'v1' },
            evidence: { engine: 'detector', prediction_class: 'truck', prediction_bbox: { x1: 10, y1: 20, x2: 30, y2: 40 }, confidence: 0.88 },
          } satisfies Candidate,
        ],
      });
    }
    if (path === '/api/runs/13/candidates/') {
      return Response.json({
        next: null,
        previous: null,
        raw_count: null,
        dedup_count: 2,
        results: [
          {
            engine: 'duplicate',
            engine_version: '1.0.0',
            family: 'E3',
            severity: 'minor',
            frame: { cvat_task_id: 9, frame_number: 2 },
            anchor: { kind: 'annotation', objects: [{ namespace: 'cvat_shape', id: 's-2' }], policy_version: 'v1' },
            evidence: { engine: 'duplicate', iou: 0.94 },
          } satisfies Candidate,
        ],
      });
    }
    if (path === '/api/runs/12/retry-failed/') return Response.json({ ...run, status: 'running' }, { status: 202 });
    if (path === '/api/snapshots/') return Response.json({ next: null, previous: null, results: [{ id: 4, dataset_id: 1, status: 'locked', revision_hash: 'abc123' }] });
    if (path === '/api/config-versions/' && request.method === 'POST') return Response.json({ id: 8, name: 'New config', status: 'draft', engines: {}, thresholds: {}, models: {}, created_by: 2, created_at: '2026-10-10T00:00:00Z' }, { status: 201 });
    if (path === '/api/config-versions/') {
      if (options.configsFails) return Response.json({ code: 'INTERNAL_ERROR', message: 'Lỗi nạp config' }, { status: 500 });
      if (options.configsOverride !== undefined) return Response.json(options.configsOverride);
      return Response.json({ next: null, previous: null, results: [{ id: 7, name: 'Published config', status: 'published', engines: { duplicate: { enabled: true, version: '1.0.0', params: { iou_threshold: 0.85 } } }, thresholds: { tau_loc: 0.55 }, models: { detector: 'detector-v2' }, created_by: 2, created_at: '2026-10-09T00:00:00Z' }] });
    }
    if (path === '/api/config-versions/8/publish/') return options.publishFails
      ? Response.json({ code: 'SERVICE_UNAVAILABLE', request_id: 'cfg-publish-503' }, { status: 503 })
      : Response.json({ id: 8, name: 'New config', status: 'published', engines: {}, thresholds: {}, models: {}, created_by: 2, created_at: '2026-10-10T00:00:00Z' });
    if (path === '/api/runs/' && request.method === 'POST') return Response.json(run, { status: 201 });
    throw new Error(`Unexpected API path: ${path}`);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AuthProvider>{page}</AuthProvider></QueryClientProvider>);
  return { calls };
}

describe('Execution screens on real API contract', () => {
  it('shows coverage exclusion reason/version, shard error, and truthful statuses', async () => {
    const { calls } = await setup('qalead', <ExecutionHistoryPage />);
    expect(await screen.findByText(/not_applicable: 1/)).toBeDefined();
    expect(screen.getByText(/Applicability version: 2026.10/)).toBeDefined();
    expect(screen.getByText('worker timeout')).toBeDefined();
    expect(screen.getByText(/disabled/)).toBeDefined();
    expect(screen.getByRole('button', { name: 'Chạy lại shard lỗi' })).toBeDefined();
    expect(calls.some((request) => new URL(request.url).pathname === '/api/runs/12/ledger/')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Chạy lại shard lỗi' }));
    await waitFor(() => expect(calls.some((request) => new URL(request.url).pathname === '/api/runs/12/retry-failed/' && request.method === 'POST')).toBe(true));
  });

  it('keeps QC admin read-only on the config screen', async () => {
    const { calls } = await setup('qcadmin', <AnalysisConfigPage />);
    expect(await screen.findByRole('option', { name: /Published config/ })).toBeDefined();
    expect((screen.getByRole('button', { name: 'Tạo QC run' }) as HTMLButtonElement).disabled).toBe(true);
    expect(calls.some((request) => request.method === 'POST' && new URL(request.url).pathname === '/api/runs/')).toBe(false);
  });

  it('creates and publishes a version through the real config endpoints', async () => {
    const { calls } = await setup('qcadmin', <AnalysisConfigPage />);
    await screen.findByRole('option', { name: /Published config/ });
    fireEvent.change(screen.getByLabelText('Tên cấu hình'), { target: { value: 'New config' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo và publish config' }));
    await waitFor(() => expect(calls.some((request) => new URL(request.url).pathname === '/api/config-versions/8/publish/')).toBe(true));
    const create = calls.find((request) => request.method === 'POST' && new URL(request.url).pathname === '/api/config-versions/');
    expect(create?.headers.get('Idempotency-Key')).toBeTruthy();
    expect(create && (await create.clone().json()).engines.duplicate.enabled).toBe(true);
  });

  it('keeps a failed publish visible with its trace and retry action', async () => {
    await setup('qcadmin', <AnalysisConfigPage />, { publishFails: true });
    await screen.findByRole('option', { name: /Published config/ });
    fireEvent.change(screen.getByLabelText('Tên cấu hình'), { target: { value: 'New config' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo và publish config' }));
    expect(await screen.findByText(/Mã yêu cầu: cfg-publish-503/)).toBeDefined();
    expect(screen.getByText(/Config v8 đã được tạo nhưng chưa xác nhận publish/)).toBeDefined();
    expect(screen.getByRole('button', { name: 'Thử publish lại' })).toBeDefined();
  });

  it('displays prompt state in EngineThresholdsTable on AnalysisConfig when no config has been chosen yet (T-029 / F-1)', async () => {
    await setup('qalead', <AnalysisConfigPage />);
    expect(await screen.findByText('Chưa chọn phiên bản cấu hình')).toBeDefined();
    expect(screen.getByText(/Vui lòng chọn một phiên bản cấu hình đã phát hành từ danh sách phía trên/)).toBeDefined();
    expect(screen.queryByText('Duplicate / Overlap')).toBeNull();
  });

  it('displays read-only engine configuration in AnalysisConfig when published config is selected (T-029 / F-1)', async () => {
    const { calls } = await setup('qalead', <AnalysisConfigPage />);
    expect(await screen.findByText('Chưa chọn phiên bản cấu hình')).toBeDefined();
    fireEvent.change(screen.getByLabelText('Phiên bản cấu hình'), { target: { value: '7' } });
    expect(await screen.findByText('Duplicate / Overlap')).toBeDefined();
    expect(screen.getByText('Ngưỡng kiểm tra engine')).toBeDefined();
    expect(screen.getByText(/Intersection over Union \(IoU\) ≥ 0.85/)).toBeDefined();
    expect(screen.getByText('Bật trong config')).toBeDefined();
    expect(screen.getByLabelText('Ngưỡng và model tham chiếu').textContent).toContain('"tau_loc": 0.55');
    expect(screen.getByLabelText('Ngưỡng và model tham chiếu').textContent).toContain('detector-v2');
    const configCall = calls.find((r) => new URL(r.url).pathname === '/api/config-versions/' && r.method === 'GET');
    expect(configCall).toBeDefined();
    expect(new URL(configCall!.url).searchParams.get('status')).toBe('published');
  });

  it('preserves chosen config in EngineThresholdsTable and does not silently switch to results[0] when paginating away (T-029 / F-1)', async () => {
    const api = installMockAuthApi(); await api.signIn('qalead');
    const original = api.fetchSpy.getMockImplementation()!;
    api.fetchSpy.mockImplementation(async (request) => {
      const url = new URL(request.url);
      if (url.pathname.startsWith('/api/auth/')) return original(request);
      if (url.pathname === '/api/snapshots/') return Response.json({ next: null, previous: null, results: [{ id: 4, dataset_id: 1, status: 'locked', revision_hash: 'abc123' }] });
      if (url.pathname === '/api/config-versions/') {
        const cursor = url.searchParams.get('cursor');
        if (cursor === 'page2') {
          return Response.json({
            next: null, previous: null,
            results: [{ id: 9, name: 'Different Config v9', status: 'published', engines: { detector: { enabled: true, version: '2.0.0', params: { confidence_threshold: 0.9 } } }, thresholds: {}, models: {}, created_by: 2, created_at: '2026-10-10T00:00:00Z' }],
          });
        }
        return Response.json({
          next: 'http://localhost/api/config-versions/?cursor=page2', previous: null,
          results: [{ id: 7, name: 'Selected Config v7', status: 'published', engines: { duplicate: { enabled: true, version: '1.0.0', params: { iou_threshold: 0.85 } } }, thresholds: {}, models: {}, created_by: 2, created_at: '2026-10-09T00:00:00Z' }],
        });
      }
      return Response.json({});
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><AuthProvider><AnalysisConfigPage /></AuthProvider></QueryClientProvider>);

    // Select config 7 on page 1
    await screen.findByRole('option', { name: /Selected Config v7/ });
    fireEvent.change(screen.getByLabelText('Phiên bản cấu hình'), { target: { value: '7' } });
    expect(await screen.findByText('Duplicate / Overlap')).toBeDefined();

    // Click next page button
    fireEvent.click(screen.getByRole('button', { name: 'Trang config tiếp' }));

    // Page 2 loaded Different Config v9 as results[0]. UI must NOT silently switch to it.
    await screen.findByRole('option', { name: /Different Config v9/ });
    expect(screen.getByText('Selected Config v7')).toBeDefined();
    expect(screen.queryByText('Different Config v9')).toBeNull();
    expect(screen.getByText(/Intersection over Union \(IoU\) ≥ 0.85/)).toBeDefined();
    expect(screen.queryByText(/Ngưỡng tin cậy ≥ 0.9/)).toBeNull();
    // Dropdown preserves option for the selected config
    expect(screen.getByRole('option', { name: /Selected Config v7 · v7 \(đang chọn\)/ })).toBeDefined();
  });

  it('displays loading state in EngineThresholdsTable on AnalysisConfig while configs query is pending (T-029 / F-1)', async () => {
    let resolveConfigs!: (value: Response) => void;
    const configsPromise = new Promise<Response>((resolve) => { resolveConfigs = resolve; });
    const api = installMockAuthApi(); await api.signIn('qalead');
    const original = api.fetchSpy.getMockImplementation()!;
    api.fetchSpy.mockImplementation(async (request) => {
      const path = new URL(request.url).pathname;
      if (path.startsWith('/api/auth/')) return original(request);
      if (path === '/api/snapshots/') return Response.json({ next: null, previous: null, results: [] });
      if (path === '/api/config-versions/') return configsPromise;
      return Response.json({});
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><AuthProvider><AnalysisConfigPage /></AuthProvider></QueryClientProvider>);
    expect(await screen.findByText('Đang tải cấu hình ngưỡng engine…')).toBeDefined();
    resolveConfigs(Response.json({ next: null, previous: null, results: [] }));
  });

  it('displays empty state in EngineThresholdsTable on AnalysisConfig when no published config exists (T-029 / F-1)', async () => {
    await setup('qalead', <AnalysisConfigPage />, {
      configsOverride: { next: null, previous: null, results: [] },
    });
    expect(await screen.findByText('Chưa có cấu hình đã phát hành')).toBeDefined();
    expect(screen.getByText(/API chưa trả về phiên bản cấu hình engine đã phát hành/)).toBeDefined();
  });

  it('displays error state in EngineThresholdsTable on AnalysisConfig when config-versions API fails (T-029 / F-1)', async () => {
    await setup('qalead', <AnalysisConfigPage />, { configsFails: true });
    expect(await screen.findByText('Không tải được cấu hình engine')).toBeDefined();
    expect((await screen.findAllByText('Máy chủ gặp lỗi. Vui lòng thử lại sau.')).length).toBeGreaterThan(0);
  });

  it('fetches and displays CandidateEvidenceList in ExecutionHistory with dedup_count when raw_count is null and displays detector evidence (CR-108)', async () => {
    searchParamsState.current = 'run=12';
    const { calls } = await setup('qalead', <ExecutionHistoryPage />);
    expect(await screen.findByText('Candidate: 1 sau khi gộp trùng.')).toBeDefined();
    expect(screen.queryByText(/0 bản ghi thô/)).toBeNull();
    expect(screen.getByText('truck')).toBeDefined();
    expect(screen.getByText('[10, 20, 30, 40]')).toBeDefined();
    expect(screen.getByText('0.88')).toBeDefined();
    expect(calls.some((r) => new URL(r.url).pathname === '/api/runs/12/candidates/')).toBe(true);
  });

  it('does not fetch candidates when no run is selected, and fetches only after run is selected', async () => {
    searchParamsState.current = '';
    const { calls } = await setup('qalead', <ExecutionHistoryPage />);
    await screen.findByText('QC-12');
    expect(calls.some((r) => new URL(r.url).pathname.includes('/candidates/'))).toBe(false);
    expect(screen.queryByText('Candidate nghi vấn & Evidence')).toBeNull();

    const detailButtons = screen.getAllByRole('button', { name: 'Chi tiết' });
    fireEvent.click(detailButtons[0]);

    expect(await screen.findByText('Candidate: 1 sau khi gộp trùng.')).toBeDefined();
    expect(calls.some((r) => new URL(r.url).pathname === '/api/runs/12/candidates/')).toBe(true);
  });

  it('updates CandidateEvidenceList when switching between runs in ExecutionHistory', async () => {
    searchParamsState.current = 'run=12';
    const { calls } = await setup('qalead', <ExecutionHistoryPage />);
    expect(await screen.findByText('Candidate: 1 sau khi gộp trùng.')).toBeDefined();
    expect(screen.getByText('truck')).toBeDefined();

    const detailButtons = screen.getAllByRole('button', { name: 'Chi tiết' });
    fireEvent.click(detailButtons[1]);

    expect(await screen.findByText('Candidate: 2 sau khi gộp trùng.')).toBeDefined();
    expect(screen.getByText('0.9400')).toBeDefined();
    expect(screen.queryByText('truck')).toBeNull();
    expect(calls.some((r) => new URL(r.url).pathname === '/api/runs/13/candidates/')).toBe(true);
  });

  it('displays loading state in CandidateEvidenceList while candidates query is pending', async () => {
    searchParamsState.current = 'run=12';
    let resolveCandidates!: (value: Response) => void;
    const candidatesPromise = new Promise<Response>((resolve) => { resolveCandidates = resolve; });
    const api = installMockAuthApi(); await api.signIn('qalead');
    const original = api.fetchSpy.getMockImplementation()!;
    api.fetchSpy.mockImplementation(async (request) => {
      const path = new URL(request.url).pathname;
      if (path.startsWith('/api/auth/')) return original(request);
      if (path === '/api/runs/' && request.method === 'GET') return Response.json({ next: null, previous: null, results: [run] });
      if (path === '/api/runs/12/') return Response.json(run);
      if (path === '/api/runs/12/ledger/') return Response.json(ledger);
      if (path === '/api/runs/12/shards/') return Response.json({ next: null, previous: null, results: [] });
      if (path === '/api/runs/12/candidates/') return candidatesPromise;
      return Response.json({});
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><AuthProvider><ExecutionHistoryPage /></AuthProvider></QueryClientProvider>);
    expect(await screen.findByText('Đang tải candidate và evidence…')).toBeDefined();
    resolveCandidates(Response.json({ next: null, previous: null, raw_count: null, dedup_count: 0, results: [] }));
  });

  it('displays empty state in CandidateEvidenceList when run has no candidates', async () => {
    searchParamsState.current = 'run=12';
    await setup('qalead', <ExecutionHistoryPage />, {
      candidatesOverride: { next: null, previous: null, raw_count: null, dedup_count: 0, results: [] },
    });
    expect(await screen.findByText('Chưa có candidate nghi vấn')).toBeDefined();
    expect(screen.getByText(/Chưa có candidate nghi vấn nào cho lần chạy này \(không tự động xem là đạt kết quả\)\./)).toBeDefined();
  });

  it('displays error state in CandidateEvidenceList when candidates API fails', async () => {
    searchParamsState.current = 'run=12';
    await setup('qalead', <ExecutionHistoryPage />, { candidatesFails: true });
    expect(await screen.findByText('Không tải được danh sách candidate')).toBeDefined();
    expect((await screen.findAllByText('Máy chủ gặp lỗi. Vui lòng thử lại sau.')).length).toBeGreaterThan(0);
  });
});
