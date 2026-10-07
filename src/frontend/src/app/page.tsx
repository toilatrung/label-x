'use client';

import React from 'react';
import Link from 'next/link';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, canAccessReview, canAccessConfiguration } from '@/lib/auth/roles';

export default function Home() {
  const { user, hasPermission } = useAuth();
  return <AuthGuard><AppShell activeKey="overview">
    <div className="lx-card" style={{ maxWidth: '1200px', margin: '0 auto', padding: 'var(--space-6)' }}>
      <h1 className="lx-h1">Trung tâm kiểm soát chất lượng</h1>
      <p className="lx-lead">Chào mừng, {user?.fullName}. Chọn chức năng được phép trong bộ dữ liệu hiện tại.</p>
      <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
        {hasPermission(canAccessAnalysis) && <Link href="/analysis" className="lx-btn lx-btn--primary">Phân tích chất lượng</Link>}
        {hasPermission(canAccessReview, true) && <Link href="/review" className="lx-btn">Trung tâm kiểm tra</Link>}
        {hasPermission(canAccessConfiguration) && <Link href="/configuration" className="lx-btn">Quy trình và phân quyền</Link>}
      </div>
      <p style={{ color: 'var(--ink-muted)', marginTop: 'var(--space-6)' }}>Các chức năng xử lý dữ liệu sẽ được bổ sung trong đợt tiếp theo.</p>
    </div>
  </AppShell></AuthGuard>;
}
