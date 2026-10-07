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
          <div className="lx-card" style={{ padding: 'var(--space-6)' }}>
            <h1 style={{ fontSize: '20px', fontWeight: 600, margin: '0 0 var(--space-2)' }}>
              Phân tích chất lượng (Quality Analysis)
            </h1>
            <p style={{ color: 'var(--ink-muted)', fontSize: '14px', margin: '0 0 var(--space-4)' }}>
              Màn hình dành riêng cho người có quyền kiểm tra và phân tích kết quả snapshot.
            </p>
            <div style={{ padding: 'var(--space-4)', background: 'var(--surface-sunken)', borderRadius: 'var(--radius-md)' }}>
              <span className="lx-badge lx-badge--success">Quyền truy cập hợp lệ</span>
              <p style={{ fontSize: '13px', marginTop: '8px', color: 'var(--ink-muted)' }}>
                Bạn đã được xác thực qua Route Guard thành công.
              </p>
            </div>
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
