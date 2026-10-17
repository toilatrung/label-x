import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import ExecutionHistoryPage from '@/app/analysis/history/page';
import AnalysisConfigPage from '@/app/analysis/config/page';
import { ModelsGuidelinesCard } from '@/components/configuration/ModelsGuidelinesCard';
import { installMockAuthApi } from './helpers/mock-api';
import type { Candidate } from '@/lib/execution/api';

const { push, replace, searchParamsState } = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), searchParamsState: { current: 'run=12' } }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push, replace }), usePathname: () => '/analysis/history', useSearchParams: () => new URLSearchParams(searchParamsState.current) }));

const run = { id: 12, snapshot_id: 4, config_version_id: 7, seed: 42, status: 'partial', is_final: false, origin_run_id: null,
  score_version: 'score_v0', model_artifact: null, engines: [{ engine: 'duplicate', status: 'partial', reason: null, failed_units: 1 },
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
    runStatus?: string;
    ledgerScript?: unknown[];
    publishFails?: boolean;
    configsOverride?: unknown;
    configsFails?: boolean;
    candidatesOverride?: unknown;
    candidatesFails?: boolean;
    artifactsOverride?: unknown;
    groundTruthOverride?: unknown;
  } = {}
) {
  const api = installMockAuthApi(); await api.signIn(username);
  const original = api.fetchSpy.getMockImplementation()!;
  const calls: Request[] = [];
  let createdConfig: Record<string, unknown> = {};
  let ledgerReads = 0;
  api.fetchSpy.mockImplementation(async (request) => {
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/auth/')) return original(request);
    if (path === '/api/ground-truth/') return Response.json(options.groundTruthOverride ?? null);
    if (path === '/api/configuration/vlm/') return Response.json({ revision: 0, model: 'qwen3-vl-plus', base_url: 'https://api.shopaikey.com/v1', confidence_threshold: 0.85, api_key_configured: false });
    if (path === '/api/model-artifacts/register/') { calls.push(request); return Response.json([{ id: 2, name: 'New Detector', version: 'v2', checksum: 'b'.repeat(64), class_mapping_version: 'bdd-10', class_mapping: { classes: ['car'] } }]); }
    if (path === '/api/model-artifacts/') return Response.json(options.artifactsOverride ?? [{ id: 1, name: 'Faster R-CNN', version: 'bdd-v1', checksum: 'a'.repeat(64), class_mapping_version: 'bdd-10', class_mapping: { classes: ['car'] } }]);
    if (path === '/api/config-versions/7/rules/') return Response.json({ config_version_id: 7, status: 'published', rules: [{ rule_id: 'duplicate-iou', name: 'Duplicate IoU', enabled: true, parameters: { iou_threshold: 0.85 } }], release_thresholds: { warning: 0.1 }, sampling_policy: { random_frames: 10 } });
    calls.push(request);
    if (path === '/api/datasets/') return Response.json({ next: null, previous: null, results: [{ id: 1, name: 'Urban', cvat_project_id: 31 }, { id: 2, name: 'Highway', cvat_project_id: 32 }] });
    if (path === '/api/runs/' && request.method === 'GET') return Response.json({ next: null, previous: null, results: [run, run13] });
    if (path === '/api/runs/12/') return Response.json({ ...run, status: options.runStatus ?? run.status });
    if (path === '/api/runs/13/') return Response.json(run13);
    if (path === '/api/runs/12/ledger/' || path === '/api/runs/13/ledger/') return Response.json(options.ledgerScript?.[Math.min(ledgerReads++, options.ledgerScript.length - 1)] ?? ledger);
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
    if (path === '/api/config-versions/' && request.method === 'POST') {
      createdConfig = await request.clone().json();
      return Response.json({ ...createdConfig, id: 8, status: 'draft', created_by: 2, created_at: '2026-10-10T00:00:00Z' }, { status: 201 });
    }
    if (path === '/api/config-versions/') {
      if (options.configsFails) return Response.json({ code: 'INTERNAL_ERROR', message: 'Lỗi nạp config' }, { status: 500 });
      if (options.configsOverride !== undefined) return Response.json(options.configsOverride);
      return Response.json({ next: null, previous: null, results: [{ id: 7, name: 'Published config', status: 'published', engines: { duplicate: { enabled: true, version: '1.0.0', params: { iou_threshold: 0.85 } } }, thresholds: { tau_loc: 0.55 }, models: { detector: 'detector-v2' }, created_by: 2, created_at: '2026-10-09T00:00:00Z' }] });
    }
    if (path === '/api/config-versions/8/publish/') return options.publishFails
      ? Response.json({ code: 'SERVICE_UNAVAILABLE', request_id: 'cfg-publish-503' }, { status: 503 })
      : Response.json({ ...createdConfig, id: 8, status: 'published', created_by: 2, created_at: '2026-10-10T00:00:00Z' });
    if (path === '/api/runs/' && request.method === 'POST') return Response.json(run, { status: 201 });
    throw new Error(`Unexpected API path: ${path}`);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AuthProvider>{page}</AuthProvider></QueryClientProvider>);
  return { calls };
}

describe('Execution screens on real API contract', () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function () { this.open = true; };
    HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new Event('close')); };
  });

  it('shows coverage exclusion reason/version, shard error, and truthful statuses', async () => {
    const { calls } = await setup('qalead', <ExecutionHistoryPage />);
    expect(await screen.findByText(/not_applicable: 1/)).toBeDefined();
    expect(screen.getByText(/Applicability version: 2026.10/)).toBeDefined();
    expect(screen.getByText('worker timeout')).toBeDefined();
    expect(screen.getByText(/disabled/)).toBeDefined();
    expect(screen.getByRole('columnheader', { name: 'Quality Control Run' })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: 'Snapshot' })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: 'Bắt đầu' })).toBeDefined();
    expect(screen.queryByRole('link', { name: 'Chạy phân tích mới' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Mở Review Queues →' })).toBeDefined();
    expect(screen.getByRole('button', { name: 'Chạy lại Duplicate / Overlap' })).toBeDefined();
    expect(screen.getAllByRole('cell').filter((cell) => cell.textContent === '—')).toHaveLength(2);
    expect(screen.queryByText(/Không cộng Coverage giữa các engine/)).toBeNull();
    expect(calls.some((request) => new URL(request.url).pathname === '/api/runs/12/ledger/')).toBe(true);
    expect(screen.getByRole('alert').textContent).toContain('gặp lỗi');
    expect(calls.some((request) => new URL(request.url).pathname === '/api/runs/12/retry-failed/' && request.method === 'POST')).toBe(false);
  });


  it('retries only the selected failed engine in the selected QC run', async () => {
    const { calls } = await setup('qalead', <ExecutionHistoryPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Chạy lại Duplicate / Overlap' }));
    await waitFor(() => expect(calls.filter(request => new URL(request.url).pathname === '/api/runs/12/retry-failed/' && request.method === 'POST')).toHaveLength(1));
    const request = calls.find(request => new URL(request.url).pathname === '/api/runs/12/retry-failed/' && request.method === 'POST')!;
    expect(await request.clone().json()).toEqual({ engine: 'duplicate' });
    expect(screen.queryByRole('button', { name: 'Chạy lại Geometry' })).toBeNull();
  });

  it('shows single-engine retry for a cancelled QC with failed engine units', async () => {
    const { calls } = await setup('qalead', <ExecutionHistoryPage />, { runStatus: 'cancelled' });
    fireEvent.click(await screen.findByRole('button', { name: 'Chạy lại Duplicate / Overlap' }));
    await waitFor(() => expect(calls.filter(request => new URL(request.url).pathname === '/api/runs/12/retry-failed/' && request.method === 'POST')).toHaveLength(1));
    const request = calls.find(request => new URL(request.url).pathname === '/api/runs/12/retry-failed/' && request.method === 'POST')!;
    expect(await request.clone().json()).toEqual({ engine: 'duplicate' });
    expect(screen.queryByRole('button', { name: 'Chạy lại Geometry' })).toBeNull();
  });

  it('refreshes a stale pending ledger even after the run detail is terminal', async () => {
    const pending = ledger.map(row => row.engine === 'duplicate' ? { ...row, completed: 1, failed: 0, pending: 1, status: 'running' } : row);
    const finished = ledger.map(row => row.engine === 'duplicate' ? { ...row, completed: 2, failed: 0, pending: 0, status: 'checked' } : row);
    const { calls } = await setup('qalead', <ExecutionHistoryPage />, { ledgerScript: [pending, finished] });
    await waitFor(() => expect(calls.filter(request => new URL(request.url).pathname === '/api/runs/12/ledger/').length).toBeGreaterThanOrEqual(2), { timeout: 6000 });
    expect(await screen.findByText('Đã kết thúc · Kết quả một phần')).toBeDefined();
    expect(screen.getByRole('progressbar', { name: 'Tổng tiến độ engine' }).getAttribute('aria-valuenow')).toBe('100');
  });

  it('keeps QC admin read-only on the config screen', async () => {
    const { calls } = await setup('qcadmin', <AnalysisConfigPage />);
    expect(await screen.findByRole('option', { name: /Published config/ })).toBeDefined();
    expect((screen.getByRole('button', { name: 'Chạy phân tích' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Lấy mẫu')).toBeDefined();
    expect(screen.getByText('Sẵn sàng chạy')).toBeDefined();
    expect(screen.queryByText(/kết nối với server/)).toBeNull();
    expect(screen.getByRole('link', { name: 'Xem chi tiết lấy mẫu' }).getAttribute('href')).toBe('/calibration/audit-sampling');
    expect(screen.getByText('Thời gian dự kiến')).toBeDefined();
    expect(calls.some((request) => request.method === 'POST' && new URL(request.url).pathname === '/api/runs/')).toBe(false);
  });

  it('keeps Review Queues navigation visible for QC admin while write actions stay hidden', async () => {
    searchParamsState.current = 'run=12';
    const { calls } = await setup('qcadmin', <ExecutionHistoryPage />);
    await screen.findByRole('option', { name: /Urban/ });
    fireEvent.change(await screen.findByLabelText('Dataset'), { target: { value: '1' } });

    expect(await screen.findByRole('link', { name: 'Mở Review Queues →' })).toBeDefined();
    expect(screen.queryByRole('button', { name: /Chạy lại/ })).toBeNull();
    expect(calls.some((request) => request.method === 'POST')).toBe(false);
  });

  it('uses the shared display formats and design labels on Execution History', async () => {
    await setup('qalead', <ExecutionHistoryPage />);
    const table = within(await screen.findByRole('region', { name: 'Các lần chạy' }));
    expect(table.queryByText('Dữ liệu thật từ LabelX API')).toBeNull();
    // Snapshot code is padded (SNP-004) and the start time is YYYY-MM-DD HH:mm.
    expect((await table.findAllByText('SNP-004')).length).toBeGreaterThan(0);
    const start = new Date('2026-10-09T00:00:00Z');
    const pad = (n: number) => String(n).padStart(2, '0');
    expect(table.getByText(`${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())} ${pad(start.getHours())}:${pad(start.getMinutes())}`)).toBeDefined();
    // The Dataset picker lives inside the runs card instead of floating above the layout.
    expect(table.getByLabelText('Dataset')).toBeDefined();
    expect(screen.queryByText(/Config v7|kết quả QC/)).toBeNull();
  });

  it('drops a URL-selected run when a global user changes Dataset context', async () => {
    searchParamsState.current = 'run=12';
    const { calls } = await setup('qcadmin', <ExecutionHistoryPage />);
    await screen.findByRole('option', { name: /Urban/ });
    const dataset = await screen.findByLabelText('Dataset');
    fireEvent.change(dataset, { target: { value: '1' } });
    expect(await screen.findByRole('link', { name: 'Mở Review Queues →' })).toBeDefined();
    const detailCallsBefore = calls.filter((request) => new URL(request.url).pathname === '/api/runs/12/').length;

    fireEvent.change(screen.getByLabelText('Dataset'), { target: { value: '2' } });

    await waitFor(() => expect(screen.queryByRole('link', { name: 'Mở Review Queues →' })).toBeNull());
    expect(calls.filter((request) => new URL(request.url).pathname === '/api/runs/12/').length).toBe(detailCallsBefore);
  });

  it('creates and publishes a version through the real config endpoints', async () => {
    const { calls } = await setup('qcadmin', <AnalysisConfigPage />);
    await screen.findByRole('option', { name: /Published config/ });
    fireEvent.change(screen.getByLabelText('Phiên bản cấu hình'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo phiên bản cấu hình' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Mô hình độc lập (Detector)' }));
    await screen.findByRole('option', { name: /Faster R-CNN/ });
    fireEvent.change(screen.getByLabelText('Model Detector'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText(/Tên cấu hình/), { target: { value: 'New config' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo và phát hành' }));
    await waitFor(() => expect(calls.some((request) => new URL(request.url).pathname === '/api/config-versions/8/publish/')).toBe(true));
    const create = calls.find((request) => request.method === 'POST' && new URL(request.url).pathname === '/api/config-versions/');
    expect(create?.headers.get('Idempotency-Key')).toBeTruthy();
    expect(create && (await create.clone().json()).engines.duplicate.enabled).toBe(true);
    const body = await create!.clone().json();
    expect(body.models).toMatchObject({ name: 'Faster R-CNN', version: 'bdd-v1' });
    expect(body.engines.detector).toEqual({ enabled: true, params: { score_threshold: 0.05 } });
    expect(body.engines.duplicate.params).toEqual({ iou_threshold: 0.85 });
    expect(body.thresholds).toEqual({ tau_loc: 0.55 });
    expect(body.rules[0].rule_id).toBe('duplicate-iou');
    expect(body.sampling_policy).toEqual({ random_frames: 10 });
    expect(body.release_thresholds).toEqual({ warning: 0.1 });
    expect(screen.queryByLabelText('Mô hình tham chiếu (JSON)')).toBeNull();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect((screen.getByLabelText('Phiên bản cấu hình') as HTMLSelectElement).value).toBe('8');
  });

  it('keeps a failed publish visible with its trace and retry action', async () => {
    const { calls } = await setup('qcadmin', <AnalysisConfigPage />, { publishFails: true });
    await screen.findByRole('option', { name: /Published config/ });
    fireEvent.change(screen.getByLabelText('Phiên bản cấu hình'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo phiên bản cấu hình' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Mô hình độc lập (Detector)' }));
    await screen.findByRole('option', { name: /Faster R-CNN/ });
    fireEvent.change(screen.getByLabelText('Model Detector'), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText(/Tên cấu hình/), { target: { value: 'New config' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo và phát hành' }));
    expect(await screen.findByText(/Mã yêu cầu: cfg-publish-503/)).toBeDefined();
    expect(screen.getByText(/Phiên bản v8 đã được tạo nhưng chưa xác nhận phát hành/)).toBeDefined();
    expect(screen.getByRole('button', { name: 'Thử phát hành lại' })).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Thử phát hành lại' }));
    await waitFor(() => expect(calls.filter(r => new URL(r.url).pathname === '/api/config-versions/8/publish/')).toHaveLength(2));
    const creates = calls.filter(r => r.method === 'POST' && new URL(r.url).pathname === '/api/config-versions/');
    expect(creates[0].headers.get('Idempotency-Key')).toBe(creates[1].headers.get('Idempotency-Key'));
  });

  it('displays prompt state in EngineThresholdsTable on AnalysisConfig when no config has been chosen yet (T-029 / F-1)', async () => {
    await setup('qalead', <AnalysisConfigPage />);
    expect(await screen.findByText('Chưa chọn phiên bản cấu hình')).toBeDefined();
    expect(screen.getByText(/Chọn một phiên bản cấu hình đã phát hành ở cột "Sẵn sàng chạy"/)).toBeDefined();
    expect(screen.queryByText('Duplicate / Overlap')).toBeNull();
  });

  it('displays read-only engine configuration in AnalysisConfig when published config is selected (T-029 / F-1)', async () => {
    const { calls } = await setup('qalead', <AnalysisConfigPage />);
    expect(await screen.findByText('Chưa chọn phiên bản cấu hình')).toBeDefined();
    fireEvent.change(screen.getByLabelText('Phiên bản cấu hình'), { target: { value: '7' } });
    expect(await screen.findByText('Duplicate / Overlap')).toBeDefined();
    expect(screen.getByText('Engine kiểm tra')).toBeDefined();
    expect(screen.getByText(/Intersection over Union ≥ 0.85/)).toBeDefined();
    expect((screen.getByRole('checkbox', { name: 'Duplicate / Overlap: bật' }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByLabelText('Ngưỡng và model tham chiếu').textContent).toContain('"tau_loc": 0.55');
    expect(screen.getByLabelText('Ngưỡng và model tham chiếu').textContent).toContain('detector-v2');
    const configCall = calls.find((r) => new URL(r.url).pathname === '/api/config-versions/' && r.method === 'GET');
    expect(configCall).toBeDefined();
    expect(new URL(configCall!.url).searchParams.get('status')).toBe('published');
  });

  it('lays out Analysis Configuration like the design: engine table and sampling on the left, readiness on the right', async () => {
    await setup('qcadmin', <AnalysisConfigPage />);
    expect(await screen.findByRole('heading', { name: 'Analysis Configuration' })).toBeDefined();
    // The design has no header action and no "real data" label; sample data is only on the sampling region.
    expect(screen.queryByRole('link', { name: 'Lịch sử thực thi' })).toBeNull();
    expect(screen.queryByText('Dữ liệu thật từ LabelX API')).toBeNull();
    expect(screen.queryByText('Dữ liệu minh họa')).toBeNull();
    const ready = within(screen.getByRole('complementary'));
    expect(ready.getByRole('heading', { name: 'Sẵn sàng chạy' })).toBeDefined();
    // Dataset is a select (also for a global role), not a bare number input.
    const dataset = await screen.findByLabelText('Dataset');
    expect(dataset.tagName).toBe('SELECT');
    expect(await ready.findByRole('option', { name: /Urban · project #31/ })).toBeDefined();
    // Empty state is neutral, not a red callout.
    fireEvent.change(await ready.findByLabelText('Phiên bản cấu hình'), { target: { value: '' } });
    const empty = await screen.findByText('Chưa chọn phiên bản cấu hình');
    expect(empty.closest('.lx-callout')?.className).toContain('lx-callout--neutral');
  });

  it('keeps engine settings and publishing out of the Detector model dialog', async () => {
    const { calls } = await setup('qcadmin', <ModelsGuidelinesCard />);
    await waitFor(() => expect((screen.getByRole('button', { name: 'Chỉnh Detector' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'Chỉnh Detector' }));
    await screen.findByRole('option', { name: /Faster R-CNN/ });
    expect(screen.queryByLabelText(/Tên cấu hình/)).toBeNull();
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(screen.queryByLabelText('Ngưỡng tin cậy Detector')).toBeNull();
    fireEvent.change(screen.getByLabelText('Model Detector'), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Chọn model' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(calls.filter(r => r.method === 'POST')).toHaveLength(0);
  });

  it('registers a worker model without creating or publishing any configuration', async () => {
    const { calls } = await setup('qcadmin', <ModelsGuidelinesCard />, { artifactsOverride: [] });
    await waitFor(() => expect((screen.getByRole('button', { name: 'Chỉnh Detector' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'Chỉnh Detector' }));
    await screen.findByText('Chưa có model Detector đã đăng ký.');
    fireEvent.click(screen.getByRole('button', { name: 'Đăng ký model từ worker' }));
    await screen.findByRole('option', { name: /New Detector/ });
    expect(calls.filter(r => r.method === 'POST').map(r => new URL(r.url).pathname)).toEqual(['/api/model-artifacts/register/']);
  });

  it('allows configurations without Detector when no detector models are registered', async () => {
    const { calls } = await setup('qcadmin', <AnalysisConfigPage />, { artifactsOverride: [] });
    fireEvent.click(await screen.findByRole('button', { name: 'Tạo phiên bản cấu hình' }));
    fireEvent.change(screen.getByLabelText(/Tên cấu hình/), { target: { value: 'Schema only' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo và phát hành' }));
    await waitFor(() => expect(calls.some(r => new URL(r.url).pathname === '/api/config-versions/8/publish/')).toBe(true));
    const create = calls.find(r => r.method === 'POST' && new URL(r.url).pathname === '/api/config-versions/');
    expect((await create!.clone().json()).engines.detector.enabled).toBe(false);
  });

  it('keeps Detector editing read-only for QA Lead', async () => {
    await setup('qalead', <ModelsGuidelinesCard />);
    await waitFor(() => expect(screen.queryByText('Đang tải…')).toBeNull());
    expect((screen.getByRole('button', { name: 'Chỉnh Detector' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('selecting Metric disables the other five engines and publishes a model-backed Metric-only config', async () => {
    const { calls } = await setup('qcadmin', <AnalysisConfigPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Tạo phiên bản cấu hình' }));
    const dialog = within(screen.getByRole('dialog'));
    fireEvent.click(dialog.getByRole('checkbox', { name: 'Mô hình độc lập (Detector)' }));
    fireEvent.click(dialog.getByRole('checkbox', { name: 'Mô hình thị giác – ngôn ngữ (VLM)' }));
    fireEvent.click(dialog.getByRole('checkbox', { name: 'Metric' }));
    expect(dialog.getAllByRole('checkbox').filter(input => (input as HTMLInputElement).checked)).toEqual([
      dialog.getByRole('checkbox', { name: 'Metric' }),
    ]);
    fireEvent.click(dialog.getByRole('checkbox', { name: 'Geometry' }));
    expect((dialog.getByRole('checkbox', { name: 'Metric' }) as HTMLInputElement).checked).toBe(false);
    fireEvent.click(dialog.getByRole('checkbox', { name: 'Metric' }));
    fireEvent.change(dialog.getByLabelText(/Tên cấu hình/), { target: { value: 'Metric exclusive' } });
    await dialog.findByRole('option', { name: /Faster R-CNN/ });
    fireEvent.change(dialog.getByLabelText('Model Detector'), { target: { value: '1' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Tạo và phát hành' }));
    await waitFor(() => expect(calls.some(r => new URL(r.url).pathname === '/api/config-versions/8/publish/')).toBe(true));
    const request = calls.find(r => r.method === 'POST' && new URL(r.url).pathname === '/api/config-versions/')!;
    const body = await request.clone().json();
    expect(Object.entries(body.engines).filter(([, value]) => (value as { enabled: boolean }).enabled).map(([key]) => key)).toEqual(['metric']);
    expect(body.models).toMatchObject({ name: 'Faster R-CNN', version: 'bdd-v1' });
  });

  it.each(['missing', 'draft', 'wrong-snapshot', 'deleted', 'ready'])('checks Metric Ground Truth readiness: %s', async state => {
    const { calls } = await setup('qalead', <AnalysisConfigPage />, {
      configsOverride: { results: [{ id: 7, name: 'Metric only', status: 'published', engines: { metric: { enabled: true } }, models: { name: 'Faster R-CNN', version: 'bdd-v1' }, thresholds: {} }], next: null, previous: null },
      groundTruthOverride: state === 'missing' ? null : { dataset_id: 1, filename: 'truth.json', frame_count: 1, box_count: 1,
        deleted_at: state === 'deleted' ? '2026-10-15T00:00:00Z' : null,
        reference: { id: 9, snapshot_id: state === 'wrong-snapshot' ? 99 : 4, status: state === 'draft' ? 'draft' : 'locked', created_by: 2 } },
    });
    await screen.findByRole('option', { name: /Metric only · v7/ });
    fireEvent.change(screen.getByLabelText('Dataset'), { target: { value: '1' } });
    await screen.findByRole('option', { name: /SNP-004/ });
    fireEvent.change(screen.getByLabelText('Snapshot đã khoá'), { target: { value: '4' } });
    fireEvent.change(screen.getByLabelText('Phiên bản cấu hình'), { target: { value: '7' } });
    await waitFor(() => expect((screen.getByRole('button', { name: 'Chạy phân tích' }) as HTMLButtonElement).disabled).toBe(!['ready', 'wrong-snapshot'].includes(state)));
    if (!['ready', 'wrong-snapshot'].includes(state)) {
      fireEvent.click(screen.getByRole('button', { name: 'Chạy phân tích' }));
      expect(calls.some(r => r.method === 'POST' && new URL(r.url).pathname === '/api/runs/')).toBe(false);
    } else {
      // Choosing a replacement must not silently run with the previous valid GT.
      fireEvent.change(screen.getByLabelText('Upload Ground Truth'), { target: { files: [new File(['{}'], 'invalid-replacement.json')] } });
      await waitFor(() => expect((screen.getByRole('button', { name: 'Chạy phân tích' }) as HTMLButtonElement).disabled).toBe(true));
    }
  });

  it('blocks analysis when an older published config enables Detector without a model', async () => {
    await setup('qcadmin', <AnalysisConfigPage />, { configsOverride: { next: null, previous: null, results: [{ id: 7, name: 'Missing model', status: 'published', engines: { detector: { enabled: true } }, models: {}, thresholds: {} }] } });
    await screen.findByRole('option', { name: /Missing model/ });
    fireEvent.change(screen.getByLabelText('Phiên bản cấu hình'), { target: { value: '7' } });
    expect(await screen.findByText(/Phiên bản này bật Detector nhưng chưa chọn model/)).toBeDefined();
    expect((screen.getByRole('button', { name: 'Chạy phân tích' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('preserves chosen config in EngineThresholdsTable and does not silently switch to results[0] when paginating away (T-029 / F-1)', async () => {
    const api = installMockAuthApi(); await api.signIn('qalead');
    const original = api.fetchSpy.getMockImplementation()!;
    api.fetchSpy.mockImplementation(async (request) => {
      const url = new URL(request.url);
      if (url.pathname.startsWith('/api/auth/')) return original(request);
      if (url.pathname === '/api/ground-truth/') return Response.json(null);
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
    fireEvent.click(screen.getByRole('button', { name: 'Trang phiên bản tiếp' }));

    // Page 2 loaded Different Config v9 as results[0]. UI must NOT silently switch to it.
    await screen.findByRole('option', { name: /Different Config v9/ });
    expect(screen.getByText('Selected Config v7')).toBeDefined();
    expect(screen.queryByText('Different Config v9')).toBeNull();
    expect(screen.getByText(/Intersection over Union ≥ 0.85/)).toBeDefined();
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
    expect(screen.getByText(/Chưa có phiên bản cấu hình engine đã phát hành/)).toBeDefined();
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
    await screen.findByText('#QC-12');
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
