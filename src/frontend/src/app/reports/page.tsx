'use client';

import React, { Suspense } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessReports } from '@/lib/auth/roles';
import { QualityReportBody, QualityReportHeader } from '@/components/reports/QualityReportView';

export default function QualityReportPage() {
  return (
    <AuthGuard permissionCheck={canAccessReports} requiredPermissionName="Quyền Báo cáo và phát hành">
      <Suspense fallback={<div>Đang tải Quality Report…</div>}>
        <AppShell activeKey="reports" flowStep={1} pageHeader={<QualityReportHeader />}>
          <QualityReportBody />
        </AppShell>
      </Suspense>
    </AuthGuard>
  );
}
