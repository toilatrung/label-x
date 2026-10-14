'use client';

import React, { Suspense } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessReports } from '@/lib/auth/roles';
import { QualityGateBody, QualityGateHeader } from '@/components/reports/QualityGateView';

export default function QualityGatePage() {
  return (
    <AuthGuard permissionCheck={canAccessReports} requiredPermissionName="Quyền Báo cáo và phát hành">
      <Suspense fallback={<div>Đang tải Quality Gate…</div>}>
        <AppShell activeKey="reports" flowStep={2} pageHeader={<QualityGateHeader />}>
          <QualityGateBody />
        </AppShell>
      </Suspense>
    </AuthGuard>
  );
}
