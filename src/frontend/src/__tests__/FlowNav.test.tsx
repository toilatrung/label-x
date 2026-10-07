import React from 'react';
import { it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FlowNav } from '@/components/layout/FlowNav';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

vi.mock('next/navigation', () => ({ usePathname: () => '/', useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));

it('shows review steps without revealing analysis navigation to a reviewer', async () => {
  const api = installMockAuthApi();
  await api.signIn('reviewer');
  render(<AuthProvider><FlowNav flow="review" /><FlowNav flow="analysis" /></AuthProvider>);
  expect(await screen.findByText('Hàng đợi kiểm tra')).toBeDefined();
  expect(screen.getByText('Không gian kiểm tra')).toBeDefined();
  expect(screen.queryByText('Snapshot')).toBeNull();
  expect(screen.queryByRole('link')).toBeNull();
});

it('uses analysis steps for an authorized QA Lead', async () => {
  const api = installMockAuthApi();
  await api.signIn('qalead');
  render(<AuthProvider><FlowNav flow="analysis" /></AuthProvider>);
  expect(await screen.findByText('Snapshot')).toBeDefined();
  expect(screen.getByText('Cấu hình phân tích')).toBeDefined();
  expect(screen.queryByText('Hàng đợi kiểm tra')).toBeNull();
});
