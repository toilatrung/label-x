import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { ForbiddenView } from '@/components/auth/ForbiddenView';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';
import { canAccessReview } from '@/lib/auth/roles';
import { MOCK_USERS, toMockSession } from '@/lib/auth/mock-users';
import { AUTH_EXPIRED_EVENT } from '@/lib/api/client';
import { fireEvent } from '@testing-library/react';

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace }), usePathname: () => '/',
}));

describe('AuthGuard and ForbiddenView', () => {
  it('renders a clear permission error', async () => {
    installMockAuthApi();
    render(<AuthProvider><ForbiddenView reason="Bạn không có quyền thực hiện hành động này." /></AuthProvider>);
    expect(screen.getByText('403 - Quyền truy cập bị từ chối')).toBeDefined();
    expect(screen.getByText('FORBIDDEN')).toBeDefined();
    await waitFor(() => expect(screen.getByText('Chưa có quyền trong phạm vi này')).toBeDefined());
  });

  it('restores an authorized session from the server', async () => {
    const api = installMockAuthApi();
    await api.signIn();
    render(<AuthProvider><AuthGuard allowedRoles={['super_admin']}><div>Nội dung bảo vệ</div></AuthGuard></AuthProvider>);
    expect(await screen.findByText('Nội dung bảo vệ')).toBeDefined();
  });

  it('ignores forged browser storage and redirects an anonymous visitor', async () => {
    installMockAuthApi();
    localStorage.setItem('lx_auth_user', JSON.stringify({ role: 'super_admin' }));
    render(<AuthProvider><AuthGuard><div>Nội dung bảo vệ</div></AuthGuard></AuthProvider>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/login'));
    expect(screen.queryByText('Nội dung bảo vệ')).toBeNull();
  });

  it('blocks a signed-in annotator who opens a review URL directly', async () => {
    const api = installMockAuthApi();
    await api.signIn('annotator');
    render(<AuthProvider><AuthGuard permissionCheck={canAccessReview} requiresIdentity>
      <div>Nội dung review</div></AuthGuard></AuthProvider>);
    expect(await screen.findByText('403 - Quyền truy cập bị từ chối')).toBeDefined();
    expect(screen.queryByText('Nội dung review')).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it('blocks review when the session has no CVAT identity', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({
      ...toMockSession(MOCK_USERS[0]), identity_mapping: { status: 'missing' },
    })));
    render(<AuthProvider><AuthGuard permissionCheck={canAccessReview} requiresIdentity>
      <div>Nội dung review</div></AuthGuard></AuthProvider>);
    expect(await screen.findByText('IDENTITY_MAPPING_MISSING')).toBeDefined();
    expect(screen.queryByText('Nội dung review')).toBeNull();
  });

  it('removes protected content and redirects after a shared auth-expired event', async () => {
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    render(<AuthProvider><AuthGuard><div>Nội dung bảo vệ</div></AuthGuard></AuthProvider>);
    await screen.findByText('Nội dung bảo vệ');
    fireEvent(window, new CustomEvent(AUTH_EXPIRED_EVENT));
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/login'));
    expect(screen.queryByText('Nội dung bảo vệ')).toBeNull();
  });
});
