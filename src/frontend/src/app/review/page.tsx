'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessReview } from '@/lib/auth/roles';

export default function ReviewPage() {
  return (
    <AuthGuard
      permissionCheck={canAccessReview}
      requiresIdentity
      requiredPermissionName="Reviewer / QA Lead / Super Admin, có liên kết CVAT"
    >
      <AppShell activeKey="review" flowStep={1} pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">
              Trung tâm kiểm tra (Review Center)
            </h1>
            <p className="lx-lead">
              Hàng đợi kiểm duyệt và không gian làm việc của Reviewer. Annotator không được vào màn hình này.
            </p></div></div>}>
        <div>
          <div className="lx-card lx-card__body lx-stack">

            <div className="lx-stack">
              <span className="lx-badge lx-badge--success">Quyền truy cập hợp lệ</span>
              <p className="lx-muted">
                Hàng đợi và chức năng kiểm tra ảnh sẽ được bổ sung trong đợt tiếp theo.
              </p>
            </div>
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
