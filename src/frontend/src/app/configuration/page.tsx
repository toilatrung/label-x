'use client';

import React from 'react';
import Link from 'next/link';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessConfiguration, ROLE_LABELS } from '@/lib/auth/roles';

export default function ConfigurationPage() {
  const { session } = useAuth();
  return <AuthGuard permissionCheck={canAccessConfiguration} requiredPermissionName="QA Lead / QC Admin / Super Admin">
    <AppShell activeKey="configuration">
      <div className="lx-card" style={{ maxWidth: '1100px', margin: '0 auto', padding: 'var(--space-6)' }}>
        <h1 className="lx-h1">Quy trình và phân quyền</h1>
        <p className="lx-lead">Vai trò của tài khoản trong các bộ dữ liệu được giao.</p>
        <table className="lx-table">
          <thead><tr><th>Vai trò</th><th>Phạm vi</th></tr></thead>
          <tbody>{session?.roles.map((assignment, index) => <tr key={index}>
            <td>{ROLE_LABELS[assignment.role]}</td>
            <td>{assignment.dataset_id === null ? 'Toàn hệ thống' : 'Dataset #' + assignment.dataset_id}</td>
          </tr>)}</tbody>
        </table>
        <p style={{ color: 'var(--ink-muted)' }}>Chức năng thay đổi cấu hình sẽ được bổ sung trong đợt tiếp theo.</p>
        <Link className="lx-btn" href="/configuration/guidelines">Tra cứu Models & Guidelines</Link>
      </div>
    </AppShell>
  </AuthGuard>;
}
