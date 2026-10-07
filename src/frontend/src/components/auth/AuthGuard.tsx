'use client';

import React from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth/auth-context';
import type { UserRole } from '@/types/auth';
import { ForbiddenView } from './ForbiddenView';

interface AuthGuardProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
  permissionCheck?: (role: UserRole) => boolean;
  requiredPermissionName?: string;
  requiresIdentity?: boolean;
}

export function AuthGuard({ children, allowedRoles, permissionCheck, requiredPermissionName,
  requiresIdentity = false }: AuthGuardProps) {
  const { session, isAuthenticated, isLoading, hasPermission, authError, accessError, clearAccessError } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => { clearAccessError(); }, [pathname, clearAccessError]);
  React.useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace('/login');
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) return <div className="lx-card" style={{ padding: 'var(--space-6)' }}>
    Đang tải thông tin phiên làm việc...
  </div>;
  if (!session) return null;

  if (accessError) return <ForbiddenView reason={accessError.message} errorCode={accessError.code} />;
  if (requiresIdentity && session.identity_mapping.status !== 'mapped') return <ForbiddenView
    reason="Tài khoản chưa được liên kết với CVAT. Vui lòng liên hệ người quản trị."
    errorCode="IDENTITY_MAPPING_MISSING" />;
  if (!hasPermission((role) => (!allowedRoles || allowedRoles.includes(role)) &&
    (!permissionCheck || permissionCheck(role)), requiresIdentity)) return <ForbiddenView
    requiredPermission={requiredPermissionName}
    reason="Bạn không có quyền mở chức năng này trong bộ dữ liệu đang chọn." />;

  return <>{authError && <div role="alert" className="lx-card" style={{ color: 'var(--danger)', padding: 'var(--space-3)' }}>
    {authError}
  </div>}{children}</>;
}
