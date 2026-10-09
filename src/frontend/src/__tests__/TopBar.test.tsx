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
    ['admin', true, true, true, true], ['qalead', true, true, true, true],
    ['qcadmin', true, false, true, true], ['reviewer', false, true, true, true],
    ['annotator', false, false, false, false], ['productowner', false, false, false, false],
    ['modelowner', false, false, false, false],
  ] as const)('uses server grants for %s', async (username, analysis, review, configuration, guidelines) => {
    const api = installMockAuthApi();
    await api.signIn(username);
    render(<AuthProvider><TopBar /></AuthProvider>);
    await waitFor(() => expect(screen.getByText(/mẫu/)).toBeDefined());
    expect(!!screen.queryByText('Quality Analysis')).toBe(analysis);
    expect(!!screen.queryByText('Review Center')).toBe(review);
    expect(!!screen.queryByText('Configuration')).toBe(configuration);
    if (guidelines) fireEvent.click(screen.getByRole('button', { name: 'Configuration' }));
    const guidelineLink = screen.queryByRole('menuitem', { name: 'Models & Guidelines' });
    expect(!!guidelineLink).toBe(guidelines);
    if (guidelineLink) expect(guidelineLink.getAttribute('href')).toBe('/configuration/guidelines');
  });

  it('opens the overview menu and logs out through the API', async () => {
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    render(<AuthProvider><TopBar /></AuthProvider>);
    await screen.findByText('Người kiểm tra mẫu');
    fireEvent.click(screen.getByText('Overview'));
    expect(screen.getByText('Quality Summary')).toBeDefined();
    fireEvent.click(screen.getByText('Người kiểm tra mẫu'));
    expect(screen.queryByText('Thử nghiệm vai trò')).toBeNull();
    fireEvent.click(screen.getByText('Đăng xuất'));
    await waitFor(() => expect(screen.getByText('Khách')).toBeDefined());
    expect(api.jar.has('sessionid')).toBe(false);
  });
  it('keeps reviewer guideline access in Configuration without exposing workflow permissions', async () => {
    const api = installMockAuthApi(); await api.signIn('reviewer');
    render(<AuthProvider><TopBar /></AuthProvider>);
    await screen.findByText('Người kiểm tra mẫu');
    const trigger = screen.getByRole('button', { name: 'Configuration' });
    fireEvent.click(trigger);
    expect(screen.getByRole('menuitem', { name: 'Models & Guidelines' })).toBeDefined();
    expect(screen.queryByRole('menuitem', { name: 'Workflow & Permissions' })).toBeNull();
    const item = screen.getByRole('menuitem', { name: 'Rules & Thresholds' });
    item.focus();
    fireEvent.keyDown(item, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: 'Models & Guidelines' }));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it('closes a menu on an outside pointer interaction', async () => {
    const api = installMockAuthApi(); await api.signIn('reviewer');
    render(<AuthProvider><TopBar /></AuthProvider>);
    await screen.findByText('Người kiểm tra mẫu');
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }));
    expect(screen.getByRole('menu')).toBeDefined();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole('menu')).toBeNull();
  });

});
