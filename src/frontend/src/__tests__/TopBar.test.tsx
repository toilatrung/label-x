import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TopBar } from '@/components/layout/TopBar';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

vi.mock('next/navigation', () => ({
  usePathname: () => '/', useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

describe('TopBar permissions', () => {
  it.each([
    ['admin', true, true, true], ['qalead', true, true, true],
    ['qcadmin', true, false, true], ['reviewer', false, true, false],
    ['annotator', false, false, false], ['productowner', false, false, false],
    ['modelowner', false, false, false],
  ] as const)('uses server grants for %s', async (username, analysis, review, configuration) => {
    const api = installMockAuthApi();
    await api.signIn(username);
    render(<AuthProvider><TopBar /></AuthProvider>);
    await waitFor(() => expect(screen.getByText(/mẫu/)).toBeDefined());
    expect(!!screen.queryByText('Phân tích chất lượng')).toBe(analysis);
    expect(!!screen.queryByText('Trung tâm kiểm tra')).toBe(review);
    expect(!!screen.queryByText('Cấu hình')).toBe(configuration);
  });

  it('opens the overview menu and logs out through the API', async () => {
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    render(<AuthProvider><TopBar /></AuthProvider>);
    await screen.findByText('Người kiểm tra mẫu');
    fireEvent.click(screen.getByText('Tổng quan'));
    expect(screen.getByText('Tóm tắt chất lượng')).toBeDefined();
    fireEvent.click(screen.getByText('Người kiểm tra mẫu'));
    expect(screen.queryByText('Thử nghiệm vai trò')).toBeNull();
    fireEvent.click(screen.getByText('Đăng xuất'));
    await waitFor(() => expect(screen.getByText('Khách')).toBeDefined());
    expect(api.jar.has('sessionid')).toBe(false);
  });
});
