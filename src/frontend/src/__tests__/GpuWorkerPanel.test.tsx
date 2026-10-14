import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { GpuWorkerPanel } from '@/components/configuration/GpuWorkerPanel';
import { ModelsGuidelinesCard } from '@/components/configuration/ModelsGuidelinesCard';

const { get, put, post, auth } = vi.hoisted(() => ({
  get: vi.fn(), put: vi.fn(), post: vi.fn(),
  auth: { session: { roles: [{ role: 'super_admin', dataset_id: null as number | null }] }, hasPermission: () => true },
}));
vi.mock('@/lib/auth/auth-context', () => ({ useAuth: () => auth }));
vi.mock('@/lib/api/client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api/client')>();
  return { ...actual, apiClient: { GET: get, PUT: put, POST: post } };
});
const config = { revision: 1, name: 'Máy GPU', url: 'https://gpu.tailnet.ts.net',
  credential_ref: 'primary', enabled: true, timeout_seconds: 120 };
const envelope = { config, credential_refs: ['primary'], allowed_hosts: ['gpu.tailnet.ts.net'] };
function reply(data: unknown, status = 200) { return { data: status === 200 ? data : undefined,
  error: status === 200 ? undefined : data, response: new Response(null, { status }) }; }
beforeEach(() => {
  vi.clearAllMocks(); auth.session.roles = [{ role: 'super_admin', dataset_id: null }];
  get.mockResolvedValue(reply(envelope));
});
afterEach(cleanup);

it('loads real config, never shows token input and only ready means ready', async () => {
  post.mockResolvedValue(reply({ revision: 1, state: 'unavailable', message: 'Worker chưa sẵn sàng.',
    checked_at: '2026-10-14T00:00:00Z', device: null, model: null, latency_ms: 5 }));
  render(<GpuWorkerPanel />);
  await screen.findByDisplayValue('Máy GPU');
  expect(screen.queryByLabelText(/^token$/i)).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Kiểm tra kết nối' }));
  await screen.findByText('Không sẵn sàng');
  expect(screen.queryByText('Sẵn sàng', { exact: true })).toBeNull();
  expect(post).toHaveBeenCalledWith('/api/gpu-worker/probe/', { body: { revision: 1 } });
});

it('edits and saves a revision before enabling probe', async () => {
  put.mockResolvedValue(reply({ ...envelope, config: { ...config, revision: 2, name: 'Máy mới' } }));
  render(<GpuWorkerPanel />);
  await screen.findByDisplayValue('Máy GPU');
  fireEvent.change(screen.getByLabelText('Tên worker'), { target: { value: 'Máy mới' } });
  expect(screen.getByRole('button', { name: 'Kiểm tra kết nối' }).hasAttribute('disabled')).toBe(true);
  fireEvent.submit(screen.getByRole('form', { name: 'Cấu hình GPU Worker' }));
  await screen.findByText(/Đã lưu cấu hình/);
  expect(put).toHaveBeenCalledWith('/api/gpu-worker/config/', { body: { ...config, name: 'Máy mới' } });
  expect(screen.getByRole('button', { name: 'Kiểm tra kết nối' }).hasAttribute('disabled')).toBe(false);
  expect(post).not.toHaveBeenCalled();
});

it('load failure shows an error and retry, not sample data or fake ready', async () => {
  get.mockResolvedValue(reply({ code: 'INTERNAL_ERROR', message: 'secret upstream detail' }, 503));
  render(<GpuWorkerPanel />);
  await screen.findByRole('alert');
  expect(screen.getByRole('button', { name: 'Thử lại' })).toBeTruthy();
  expect(screen.queryByRole('form')).toBeNull();
  expect(screen.queryByText(/secret upstream detail/)).toBeNull();
});

it('a stale save does not report success', async () => {
  put.mockResolvedValue(reply({ code: 'INVALID_TRANSITION', message: 'reload' }, 409));
  render(<GpuWorkerPanel />);
  await screen.findByDisplayValue('Máy GPU');
  fireEvent.change(screen.getByLabelText('Tên worker'), { target: { value: 'Máy khác' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Cấu hình GPU Worker' }));
  await screen.findByRole('alert');
  expect(screen.queryByText(/Đã lưu cấu hình/)).toBeNull();
});

it('hides worker administration from dataset-scoped users', async () => {
  auth.session.roles = [{ role: 'qc_admin', dataset_id: 1 }];
  render(<ModelsGuidelinesCard />);
  expect(screen.queryByRole('tab', { name: 'GPU Worker' })).toBeNull();
  expect(get).not.toHaveBeenCalled();
});

it('global admin opens the worker tab', async () => {
  render(<ModelsGuidelinesCard />);
  fireEvent.click(screen.getByRole('tab', { name: 'GPU Worker' }));
  await waitFor(() => expect(get).toHaveBeenCalled());
  await screen.findByDisplayValue('Máy GPU');
});
