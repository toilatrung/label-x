'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessReview } from '@/lib/auth/roles';
import { ReviewQueues } from '@/components/review/ReviewQueues';

export default function ReviewPage() {
  return (
    <AuthGuard
      permissionCheck={canAccessReview}
      requiresIdentity
      requiredPermissionName="Reviewer / QA Lead / Super Admin, có liên kết CVAT"
    >
      <AppShell
        activeKey="review"
        flowStep={1}
        pageHeader={
          <div className="lx-head">
            <div className="lx-head__text">
              <h1 className="lx-h1">Trung tâm kiểm tra (Review Queues)</h1>
              <p className="lx-lead">
                Hàng đợi kiểm duyệt ưu tiên frame theo rủi ro và mẫu kiểm định ngẫu nhiên.
              </p>
            </div>
          </div>
        }
      >
        <ReviewQueues />
      </AppShell>
    </AuthGuard>
  );
}
