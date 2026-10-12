import React from 'react';
import { it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { FlowNav } from '@/components/layout/FlowNav';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

vi.mock('next/navigation', () => ({ usePathname: () => '/', useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));

it('shows review steps without revealing analysis navigation to a reviewer', async () => {
  const api = installMockAuthApi();
  await api.signIn('reviewer');
  render(<AuthProvider><FlowNav flow="review" /><FlowNav flow="analysis" /></AuthProvider>);
  expect(await screen.findByText('Hàng đợi')).toBeDefined();
  expect(screen.getByText('Kiểm tra ảnh')).toBeDefined();
  expect(screen.queryByText('Snapshot')).toBeNull();
  expect(screen.queryByRole('link', { name: /Snapshot|Analysis Configuration/ })).toBeNull();
});

it('uses analysis steps for an authorized QA Lead', async () => {
  const api = installMockAuthApi();
  await api.signIn('qalead');
  render(<AuthProvider><FlowNav flow="analysis" /></AuthProvider>);
  expect(await screen.findByText('Snapshot')).toBeDefined();
  expect(screen.getByText('Analysis Configuration')).toBeDefined();
  expect(screen.queryByText('Hàng đợi')).toBeNull();
});

it('links every step and offers previous/next arrows with tooltips naming the neighbouring step', async () => {
  const api = installMockAuthApi();
  await api.signIn('qalead');
  render(<AuthProvider><FlowNav flow="analysis" currentStep={2} /></AuthProvider>);
  const nav = await screen.findByRole('navigation', { name: 'Quy trình phân tích' });
  expect(within(nav).getByRole('link', { name: /^3.*Execution History/ }).getAttribute('href')).toBe('/analysis/history');
  expect(within(nav).getByRole('link', { name: /^2.*Analysis Configuration/ }).getAttribute('aria-current')).toBe('step');
  expect(within(nav).getByRole('link', { name: 'Bước trước: Snapshot' }).getAttribute('href')).toBe('/analysis');
  expect(within(nav).getByRole('link', { name: 'Bước sau: Execution History' }).getAttribute('href')).toBe('/analysis/history');
  expect(within(nav).getByText('Bước 2 / 3')).toBeDefined();
});

it('disables the previous arrow on the first step and the next arrow on the last step', async () => {
  const api = installMockAuthApi();
  await api.signIn('qalead');
  const { rerender } = render(<AuthProvider><FlowNav flow="reports" currentStep={1} /></AuthProvider>);
  expect((await screen.findByRole('img', { name: 'Đây là bước đầu tiên' })).className).toContain('is-off');
  rerender(<AuthProvider><FlowNav flow="reports" currentStep={3} /></AuthProvider>);
  expect(screen.getByRole('img', { name: 'Đây là bước cuối cùng' }).className).toContain('is-off');
  expect(screen.getByRole('link', { name: 'Bước trước: Quality Gate' }).getAttribute('href')).toBe('/reports/gate');
});
