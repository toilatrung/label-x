'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { ReworkTracking } from '@/components/review/ReworkTracking';
import { canAccessReview } from '@/lib/auth/roles';

export default function ReworkTrackingPage() {
  return (
    <AuthGuard
      permissionCheck={canAccessReview}
      requiresIdentity
      requiredPermissionName="Reviewer / Quality Assurance Lead / Quality Control Admin / Super Admin, có liên kết CVAT"
    >
      <AppShell
        activeKey="review"
        flowStep={3}
        pageHeader={
          <div className="lx-head">
            <div className="lx-head__text">
              <h1 className="lx-h1">Rework Tracking</h1>
              <p className="lx-lead">Theo dõi các yêu cầu sửa từ lúc tạo đến khi được xác minh. Annotator sửa trực tiếp trên CVAT; snapshot gốc luôn giữ nguyên.</p>
            </div>
          </div>
        }
      >
        <div className="lx-page"><ReworkTracking /></div>
      </AppShell>
    </AuthGuard>
  );
}
