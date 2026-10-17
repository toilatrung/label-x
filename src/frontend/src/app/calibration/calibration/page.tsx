'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessCalibration } from '@/lib/auth/roles';
import { CalibrationHeader, CalibrationBody } from '@/components/calibration/CalibrationView';

export default function CalibrationPage() {
  return (
    <AuthGuard permissionCheck={canAccessCalibration} requiredPermissionName="Quyền Calibration & Audit">
      <AppShell activeKey="calibration" showFlowNav={false} pageHeader={<CalibrationHeader />}>
        <CalibrationBody />
      </AppShell>
    </AuthGuard>
  );
}
