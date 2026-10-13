'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessCalibration } from '@/lib/auth/roles';
import { AuditSamplingHeader, AuditSamplingBody } from '@/components/calibration/AuditSamplingView';

export default function AuditSamplingPage() {
  return (
    <AuthGuard permissionCheck={canAccessCalibration} requiredPermissionName="Quyền Calibration & Audit">
      <AppShell activeKey="calibration" showFlowNav={false} pageHeader={<AuditSamplingHeader />}>
        <AuditSamplingBody />
      </AppShell>
    </AuthGuard>
  );
}
