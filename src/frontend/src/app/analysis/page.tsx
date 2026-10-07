'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessAnalysis } from '@/lib/auth/roles';

export default function AnalysisPage() {
  return (
    <AuthGuard
      permissionCheck={canAccessAnalysis}
      requiredPermissionName="Quyền Phân tích Chất lượng (QA Lead / QC Admin / Super Admin)"
    >
      <AppShell activeKey="analysis" flowStep={1}>
        <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
          <div className="lx-card lx-card__body lx-stack">
            <h1 className="lx-h1">
              Phân tích chất lượng (Quality Analysis)
            </h1>
            <p className="lx-lead">
              Màn hình dành riêng cho người có quyền kiểm tra và phân tích kết quả snapshot.
            </p>
            <div className="lx-stack">
              <span className="lx-badge lx-badge--success">Quyền truy cập hợp lệ</span>
              <p className="lx-muted">
                Chức năng tạo Snapshot và chạy phân tích sẽ được bổ sung trong đợt tiếp theo.
              </p>
            </div>
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
