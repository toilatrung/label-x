'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessCalibration } from '@/lib/auth/roles';
import { PerformanceHeader, PerformanceBody } from '@/components/calibration/PerformanceView';

export default function PerformanceEvaluationPage() {
  return (
    <AuthGuard permissionCheck={canAccessCalibration} requiredPermissionName="Quyền Calibration & Audit">
      <AppShell activeKey="calibration" showFlowNav={false} pageHeader={<PerformanceHeader />}>
        <PerformanceBody />
      </AppShell>
    </AuthGuard>
  );
}
