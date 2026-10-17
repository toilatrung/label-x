'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessReports } from '@/lib/auth/roles';
import { ReleaseHistoryBody } from '@/components/reports/ReleaseHistoryView';

const header = (
  <div className="lx-head">
    <div className="lx-head__text">
      <h1 className="lx-h1">Release History</h1>
      <p className="lx-lead">Lịch sử các lần phát hành. Mỗi lần phát hành có manifest ghi lại đầy đủ snapshot, phiên bản, quyết định và người phê duyệt.</p>
    </div>
  </div>
);

export default function ReleaseHistoryPage() {
  return (
    <AuthGuard permissionCheck={canAccessReports} requiredPermissionName="Quyền Báo cáo và phát hành">
      <AppShell activeKey="reports" flowStep={3} pageHeader={header}>
        <ReleaseHistoryBody />
      </AppShell>
    </AuthGuard>
  );
}
