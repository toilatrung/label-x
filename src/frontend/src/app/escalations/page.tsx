'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { EscalationsWorkspace } from '@/components/escalations/EscalationsWorkspace';
import { canAccessEscalations } from '@/lib/auth/roles';

export default function EscalationsPage() {
  return (
    <AuthGuard
      permissionCheck={canAccessEscalations}
      requiresIdentity
      requiredPermissionName="QA Lead / Super Admin, có liên kết CVAT"
    >
      <AppShell
        activeKey="escalations"
        flowStep={2}
        pageHeader={
          <div className="lx-head">
            <div className="lx-head__text">
              <h1 className="lx-h1">Escalations &amp; Decision Cases</h1>
              <p className="lx-lead">
                Xem evidence và quyết định reviewer, phân xử theo guideline, rồi tra cứu kết luận có version.
              </p>
            </div>
          </div>
        }
      >
        <EscalationsWorkspace />
      </AppShell>
    </AuthGuard>
  );
}
