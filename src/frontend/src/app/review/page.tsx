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
      <AppShell activeKey="review" flowStep={1}>
        <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
          <div className="lx-card" style={{ padding: 'var(--space-6)' }}>
            <h1 style={{ fontSize: '20px', fontWeight: 600, margin: '0 0 var(--space-2)' }}>
              Trung tâm kiểm tra (Review Center)
            </h1>
            <p style={{ color: 'var(--ink-muted)', fontSize: '14px', margin: '0 0 var(--space-4)' }}>
              Hàng đợi kiểm duyệt và không gian làm việc của Reviewer. Annotator không được vào màn hình này.
            </p>
            <div style={{ padding: 'var(--space-4)', background: 'var(--surface-sunken)', borderRadius: 'var(--radius-md)' }}>
              <span className="lx-badge lx-badge--success">Quyền truy cập hợp lệ</span>
              <p style={{ fontSize: '13px', marginTop: '8px', color: 'var(--ink-muted)' }}>
                Hàng đợi và chức năng kiểm tra ảnh sẽ được bổ sung trong đợt tiếp theo.
              </p>
            </div>
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
