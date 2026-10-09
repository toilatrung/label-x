import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ConfigurationPage from '@/app/configuration/page';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/configuration',
}));

const PATH = '/api/auth/workflow-permissions/';
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

const roles = (value: string) => ({
  annotator: value, reviewer: value, qa_lead: value, qc_admin: value,
  super_admin: value, product_owner: value, data_model_owner: value,
});

async function setup(username: string, handler: () => Response) {
  const api = installMockAuthApi();
  await api.signIn(username);
  const passthrough = api.fetchSpy.getMockImplementation()!;
  api.fetchSpy.mockImplementation(async (request: Request) =>
    new URL(request.url).pathname === PATH ? handler() : passthrough(request));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AuthProvider><ConfigurationPage /></AuthProvider></QueryClientProvider>);
  return api;
}

describe('WorkflowPermissions (T-016)', () => {
  it('renders the matrix, rules and own roles returned by the API', async () => {
    const api = await setup('qalead', () => json({
      matrix: [{ function: 'Rework', roles: roles('execute') }],
      rules: [
        { rule: 'anti_self_review', name: 'Không tự review', description: 'Backend từ chối khi trùng người', enforced: false },
        { rule: 'audit_logging', name: 'Ghi nhật ký', description: 'Mọi thao tác', enforced: true },
      ],
      user_roles: [{ role: 'qa_lead', dataset_id: 1 }],
    }));
    expect(await screen.findByText('Rework')).toBeDefined();
    expect(screen.getByText('Không tự review')).toBeDefined();
    expect(screen.getByText('Chờ triển khai')).toBeDefined();
    expect(screen.getByText('Đã áp dụng')).toBeDefined();
    expect(screen.getByText('Dataset #1')).toBeDefined();
    expect(api.fetchSpy.mock.calls.some(([r]) => new URL(r.url).pathname === PATH)).toBe(true);
    expect(screen.queryByRole('button', { name: /sửa|xoá|xóa|edit|delete/i })).toBeNull();
  });

  it('shows the shared error message when the API denies access', async () => {
    await setup('qalead', () => json({ code: 'FORBIDDEN', message: 'x', details: {}, request_id: 'r' }, 403));
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(screen.getByText('Bạn không có quyền thực hiện thao tác này.')).toBeDefined();
  });

  it('does not call the API for a role without access', async () => {
    const api = await setup('reviewer', () => json({}));
    await screen.findAllByText(/quyền/i);
    expect(api.fetchSpy.mock.calls.some(([r]) => new URL(r.url).pathname === PATH)).toBe(false);
  });
});
