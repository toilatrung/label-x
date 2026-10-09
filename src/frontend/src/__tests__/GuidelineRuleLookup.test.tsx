import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import { GuidelineRuleLookup } from '@/components/guidelines/GuidelineRuleLookup';
import { installMockAuthApi } from './helpers/mock-api';

const rule = (id: string, version = 'bdd-v1.2') => ({ rule_id: id, guideline_version: version, section: '3.1', content: `Hướng dẫn ${id}` });
async function setup(username: string, view: React.ReactNode = <GuidelineRuleLookup />) {
  const api = installMockAuthApi(); await api.signIn(username);
  const calls: URL[] = []; const passthrough = api.fetchSpy.getMockImplementation()!;
  api.fetchSpy.mockImplementation(async request => {
    const url = new URL(request.url);
    if (!url.pathname.startsWith('/api/guidelines/')) return passthrough(request);
    calls.push(url);
    if (url.pathname !== '/api/guidelines/rules/') {
      const id = decodeURIComponent(url.pathname.split('/').filter(Boolean).at(-1)!);
      return id === 'MISSING' ? Response.json({ code: 'NOT_FOUND', request_id: 'rule-404' }, { status: 404 })
        : Response.json(rule(id, url.searchParams.get('version') || 'bdd-v1.2'));
    }
    return Response.json({ next: null, previous: null, results: [rule('VEH-03')] });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={client}><AuthProvider>{children}</AuthProvider></QueryClientProvider>;
  return { ...render(view, { wrapper }), calls, client };
}

describe('GuidelineRuleLookup reusable API component', () => {
  it('retrieves an exact rule from the detail API with the requested version', async () => {
    const { calls } = await setup('reviewer');
    await screen.findByText('Hướng dẫn VEH-03');
    fireEvent.change(screen.getByLabelText('Rule ID'), { target: { value: ' VEH-02 ' } });
    fireEvent.change(screen.getByLabelText('Guideline version'), { target: { value: ' bdd-v1.1 ' } });
    expect((screen.getByLabelText('Nhóm lỗi') as HTMLSelectElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Lọc' }));
    await screen.findByText('Hướng dẫn VEH-02');
    expect(calls.at(-1)!.pathname).toBe('/api/guidelines/rules/VEH-02/');
    expect(calls.at(-1)!.searchParams.get('version')).toBe('bdd-v1.1');
    expect(calls.at(-1)!.searchParams.has('family')).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Xoá bộ lọc' }));
    await screen.findByText('Hướng dẫn VEH-03');
    expect((screen.getByLabelText('Rule ID') as HTMLInputElement).value).toBe('');
  });

  it('accepts Workspace context and resets when the Issue/version changes', async () => {
    const { rerender, calls } = await setup('reviewer', <GuidelineRuleLookup compact initialFilters={{ ruleId: 'VEH-02', version: 'bdd-v1.1' }} />);
    await screen.findByText('Hướng dẫn VEH-02');
    rerender(<GuidelineRuleLookup compact initialFilters={{ ruleId: 'PED-01', version: 'bdd-v1.2' }} />);
    await screen.findByText('Hướng dẫn PED-01');
    expect(screen.queryByText('Hướng dẫn VEH-02')).toBeNull();
    expect(calls.at(-1)!.pathname).toBe('/api/guidelines/rules/PED-01/');
    expect(calls.at(-1)!.searchParams.get('version')).toBe('bdd-v1.2');
  });

  it('sends family and class filters from a standalone Workspace panel', async () => {
    const { calls } = await setup('reviewer', <GuidelineRuleLookup initialFilters={{ family: 'E2', className: 'truck', version: 'bdd-v1.2' }} />);
    await screen.findByText('Hướng dẫn VEH-03');
    expect(calls[0].searchParams.get('family')).toBe('E2');
    expect(calls[0].searchParams.get('class_name')).toBe('truck');
    expect(calls[0].searchParams.get('version')).toBe('bdd-v1.2');
  });

  it('removes stale content when exact lookup fails', async () => {
    await setup('reviewer'); await screen.findByText('Hướng dẫn VEH-03');
    fireEvent.change(screen.getByLabelText('Rule ID'), { target: { value: 'MISSING' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lọc' }));
    expect(within(await screen.findByRole('alert')).getByText(/Không tìm thấy tài nguyên/)).toBeDefined();
    expect(screen.queryByText('Hướng dẫn VEH-03')).toBeNull();
  });

  it.each(['annotator', 'productowner', 'modelowner'])('does not call guideline API for forbidden %s even without a page guard', async username => {
    const { calls } = await setup(username);
    await screen.findByText('Bạn không có quyền tra cứu guideline.');
    expect(calls).toHaveLength(0);
  });

  it('uses unique input labels when multiple lookup panels share a Workspace', async () => {
    await setup('reviewer', <><GuidelineRuleLookup /><GuidelineRuleLookup compact /></>);
    await waitFor(() => expect(screen.getAllByRole('search')).toHaveLength(2));
    const fields = screen.getAllByLabelText('Rule ID');
    expect(fields[0].id).not.toBe(fields[1].id);
  });
});
