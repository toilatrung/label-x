import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import ExecutionHistoryPage from '@/app/analysis/history/page';
import AnalysisConfigPage from '@/app/analysis/config/page';
import { installMockAuthApi } from './helpers/mock-api';

const { push, replace } = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push, replace }), usePathname: () => '/analysis/history', useSearchParams: () => new URLSearchParams('run=12') }));

const run = { id: 12, snapshot_id: 4, config_version_id: 7, seed: 42, status: 'partial', is_final: false, origin_run_id: null,
  score_version: 'v1', model_artifact: null, engines: [{ engine: 'duplicate', status: 'partial', reason: null, failed_units: 1 },
    { engine: 'geometry', status: 'not_checked', reason: 'disabled', failed_units: 0 }], created_by: 2, created_at: '2026-10-09T00:00:00Z', finished_at: null };
const ledger = [{ engine: 'duplicate', status: 'partial', required: true, unit: 'shape', total: 3, eligible: 2, excluded: 1,
  applicability_version: '2026.10', completed: 1, failed: 1, pending: 0, not_checked: 1, not_checked_reasons: { not_applicable: 1 }, coverage: 0.5 },
  { engine: 'geometry', status: 'not_checked', required: true, unit: 'frame', total: 0, eligible: 0, excluded: 0,
    applicability_version: '1.0.0', completed: 0, failed: 0, pending: 0, not_checked: 0, not_checked_reasons: {}, coverage: null }];

async function setup(username: string, page: React.ReactNode, options: { publishFails?: boolean } = {}) {
  const api = installMockAuthApi(); await api.signIn(username);
  const original = api.fetchSpy.getMockImplementation()!;
  const calls: Request[] = [];
  api.fetchSpy.mockImplementation(async (request) => {
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/auth/')) return original(request);
    calls.push(request);
    if (path === '/api/runs/' && request.method === 'GET') return Response.json({ next: null, previous: null, results: [run] });
    if (path === '/api/runs/12/') return Response.json(run);
    if (path === '/api/runs/12/ledger/') return Response.json(ledger);
    if (path === '/api/runs/12/shards/') return Response.json({ next: null, previous: null, results: [{ id: 5, engine: 'duplicate', shard_key: 'job:1', shard_index: 0, status: 'failed', attempt: 2, last_error: 'worker timeout' }] });
    if (path === '/api/runs/12/retry-failed/') return Response.json({ ...run, status: 'running' }, { status: 202 });
    if (path === '/api/snapshots/') return Response.json({ next: null, previous: null, results: [{ id: 4, dataset_id: 1, status: 'locked', revision_hash: 'abc123' }] });
    if (path === '/api/config-versions/' && request.method === 'POST') return Response.json({ id: 8, name: 'New config', status: 'draft', engines: {}, thresholds: {}, models: {}, created_by: 2, created_at: '2026-10-10T00:00:00Z' }, { status: 201 });
    if (path === '/api/config-versions/') return Response.json({ next: null, previous: null, results: [{ id: 7, name: 'Published config', status: 'published', engines: { duplicate: { enabled: true } }, thresholds: {}, models: {}, created_by: 2, created_at: '2026-10-09T00:00:00Z' }] });
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
    expect(await screen.findByText(/Published config/)).toBeDefined();
    expect((screen.getByRole('button', { name: 'Tạo QC run' }) as HTMLButtonElement).disabled).toBe(true);
    expect(calls.some((request) => request.method === 'POST' && new URL(request.url).pathname === '/api/runs/')).toBe(false);
  });

  it('creates and publishes a version through the real config endpoints', async () => {
    const { calls } = await setup('qcadmin', <AnalysisConfigPage />);
    await screen.findByText(/Published config/);
    fireEvent.change(screen.getByLabelText('Tên cấu hình'), { target: { value: 'New config' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo và publish config' }));
    await waitFor(() => expect(calls.some((request) => new URL(request.url).pathname === '/api/config-versions/8/publish/')).toBe(true));
    const create = calls.find((request) => request.method === 'POST' && new URL(request.url).pathname === '/api/config-versions/');
    expect(create?.headers.get('Idempotency-Key')).toBeTruthy();
    expect(create && (await create.clone().json()).engines.duplicate.enabled).toBe(true);
  });

  it('keeps a failed publish visible with its trace and retry action', async () => {
    await setup('qcadmin', <AnalysisConfigPage />, { publishFails: true });
    await screen.findByText(/Published config/);
    fireEvent.change(screen.getByLabelText('Tên cấu hình'), { target: { value: 'New config' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo và publish config' }));
    expect(await screen.findByText(/Mã yêu cầu: cfg-publish-503/)).toBeDefined();
    expect(screen.getByText(/Config v8 đã được tạo nhưng chưa xác nhận publish/)).toBeDefined();
    expect(screen.getByRole('button', { name: 'Thử publish lại' })).toBeDefined();
  });
});
