import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { ForbiddenView } from '@/components/auth/ForbiddenView';
import { AuthProvider } from '@/lib/auth/auth-context';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/',
}));

describe('AuthGuard & ForbiddenView', () => {
  it('renders ForbiddenView with 403 status code and reason', () => {
    render(
      <AuthProvider>
        <ForbiddenView
          requiredPermission="Quyền Admin"
          reason="Bạn không có quyền thực hiện hành động này."
        />
      </AuthProvider>
    );

    expect(screen.getByText('403 - Quyền truy cập bị từ chối')).toBeDefined();
    expect(screen.getByText('FORBIDDEN')).toBeDefined();
    expect(screen.getByText('Bạn không có quyền thực hiện hành động này.')).toBeDefined();
    expect(screen.getByText('Quay về Trang chủ')).toBeDefined();
  });

  it('renders children inside AuthGuard when authorized', () => {
    localStorage.setItem(
      'lx_auth_user',
      JSON.stringify({
        id: 'test-admin',
        username: 'admin',
        fullName: 'Super Admin',
        role: 'super_admin',
        email: 'admin@example.test',
      })
    );

    render(
      <AuthProvider>
        <AuthGuard allowedRoles={['super_admin']}>
          <div>Nội dung bảo vệ cho Super Admin</div>
        </AuthGuard>
      </AuthProvider>
    );

    expect(screen.getByText('Nội dung bảo vệ cho Super Admin')).toBeDefined();
  });
});
