'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { EscalationsDesign } from '@/components/escalations/EscalationsDesign';
import { canAccessEscalations } from '@/lib/auth/roles';

export default function EscalationsPage() {
  return (
    <AuthGuard
      permissionCheck={canAccessEscalations}
      requiresIdentity
      requiredPermissionName="QA Lead / Super Admin, có liên kết CVAT"
    >
      <AppShell activeKey="escalations">
        <EscalationsDesign />
      </AppShell>
    </AuthGuard>
  );
}
