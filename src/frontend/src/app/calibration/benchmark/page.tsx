'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessCalibration } from '@/lib/auth/roles';
import { BenchmarkHeader, BenchmarkBody } from '@/components/calibration/BenchmarkView';

export default function BenchmarkPage() {
  return (
    <AuthGuard permissionCheck={canAccessCalibration} requiredPermissionName="Quyền Calibration & Audit">
      <AppShell activeKey="calibration" showFlowNav={false} pageHeader={<BenchmarkHeader />}>
        <BenchmarkBody />
      </AppShell>
    </AuthGuard>
  );
}
