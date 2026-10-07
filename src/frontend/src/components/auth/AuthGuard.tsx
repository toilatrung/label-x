'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth/auth-context';
import { UserRole } from '@/types/auth';
import { ForbiddenView } from '@/components/auth/ForbiddenView';

interface AuthGuardProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
  permissionCheck?: (role: UserRole) => boolean;
  requiredPermissionName?: string;
}

export function AuthGuard({
  children,
  allowedRoles,
  permissionCheck,
  requiredPermissionName,
}: AuthGuardProps) {
  const { user, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  React.useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return (
      <div style={{ minHeight: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: 'var(--ink-subtle)', fontSize: '14px' }}>Đang tải thông tin phiên làm việc...</span>
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return null;
  }

  // Kiểm tra quyền theo vai trò (Role-based access control)
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return (
      <ForbiddenView
        requiredPermission={requiredPermissionName || allowedRoles.join(', ')}
        reason="Vai trò hiện tại của bạn không nằm trong danh sách được phép truy cập chức năng này."
      />
    );
  }

  if (permissionCheck && !permissionCheck(user.role)) {
    return (
      <ForbiddenView
        requiredPermission={requiredPermissionName}
        reason="Chức năng này bị giới hạn theo ma trận phân quyền của hệ thống."
      />
    );
  }

  return <>{children}</>;
}
