'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessReports } from '@/lib/auth/roles';
import { QualityGateBody } from '@/components/reports/QualityGateView';

const header = (
  <div className="lx-head">
    <div className="lx-head__text">
      <h1 className="lx-h1">Quality Gate</h1>
      <p className="lx-lead">Điều kiện bắt buộc trước khi phát hành Road Vision Urban v1.4. Chỉ phát hành khi mọi điều kiện đạt hoặc có waiver được người có thẩm quyền duyệt.</p>
    </div>
    <div className="lx-actions"><span className="lx-badge lx-badge--danger">Blocked</span></div>
  </div>
);

export default function QualityGatePage() {
  return (
    <AuthGuard permissionCheck={canAccessReports} requiredPermissionName="Quyền Báo cáo và phát hành">
      <AppShell activeKey="reports" flowStep={2} pageHeader={header}>
        <QualityGateBody />
      </AppShell>
    </AuthGuard>
  );
}
