import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import RulesThresholdsPage from '@/app/configuration/rules-thresholds/page';
import GuidelinesPage from '@/app/configuration/guidelines/page';
import { AdjudicationEmptyDetail } from '@/components/escalations/AdjudicationEmptyDetail';
import { installMockAuthApi } from './helpers/mock-api';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => '/configuration',
}));

const NOTICE = 'Chức năng vẫn chưa được kết nối với server';

async function renderPage(Page: React.ComponentType) {
  const api = installMockAuthApi();
  await api.signIn('qalead');
  const passthrough = api.fetchSpy.getMockImplementation()!;
  api.fetchSpy.mockImplementation(async (request: Request) => {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/api/auth/')) return passthrough(request);
    if (url.pathname === '/api/model-artifacts/') return Response.json([]);
    return Response.json({ next: null, previous: null, results: [] });
  });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><AuthProvider><Page /></AuthProvider></QueryClientProvider>);
}

describe('Rules và Thresholds: API blocks belong to the rules tab', () => {
  it('shows engine thresholds and guideline mapping only on Quy tắc kiểm tra', async () => {
    await renderPage(RulesThresholdsPage);
    expect(await screen.findByRole('region', { name: 'Mapping rule guideline' })).toBeDefined();
    expect(screen.getByRole('region', { name: 'Cấu hình ngưỡng engine' })).toBeDefined();
    fireEvent.click(screen.getByRole('tab', { name: 'Ngưỡng phát hành' }));
    expect(screen.queryByRole('region', { name: 'Mapping rule guideline' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'Cấu hình ngưỡng engine' })).toBeNull();
    fireEvent.click(screen.getByRole('tab', { name: 'Chính sách lấy mẫu' }));
    expect(screen.queryByRole('region', { name: 'Mapping rule guideline' })).toBeNull();
    fireEvent.click(screen.getByRole('tab', { name: 'Quy tắc kiểm tra' }));
    expect(screen.getByRole('region', { name: 'Mapping rule guideline' })).toBeDefined();
  });
});

describe('Models và Guidelines: rule lookup belongs to the guideline tab', () => {
  it('shows the rule list only on Phiên bản guideline', async () => {
    await renderPage(GuidelinesPage);
    await screen.findByRole('tab', { name: 'Mô hình' });
    expect(screen.queryByRole('region', { name: 'Danh sách rule guideline' })).toBeNull();
    fireEvent.click(screen.getByRole('tab', { name: 'Phiên bản guideline' }));
    expect(await screen.findByRole('region', { name: 'Danh sách rule guideline' })).toBeDefined();
    fireEvent.click(screen.getByRole('tab', { name: 'Mô hình' }));
    expect(screen.queryByRole('region', { name: 'Danh sách rule guideline' })).toBeNull();
  });
});

describe('Adjudication empty detail', () => {
  it('shows the design layout without fake data, with locked controls and no notice', () => {
    render(<AdjudicationEmptyDetail />);
    expect(screen.getByText('Quyết định của reviewer')).toBeDefined();
    expect(screen.getByText('Hướng dẫn liên quan')).toBeDefined();
    expect(screen.getByText('Kết luận phân xử')).toBeDefined();
    expect(screen.queryByText('QC-00098')).toBeNull();
    expect(screen.queryByText('Dữ liệu minh họa')).toBeNull();
    expect(screen.queryByText(NOTICE)).toBeNull();
    for (const name of ['Lưu phân xử', 'Tạo Guideline Gap']) expect((screen.getByRole('button', { name }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('radio', { name: 'Xác nhận lỗi' }) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText('Sau khi phân xử') as HTMLSelectElement).disabled).toBe(true);
  });
});
