'use client';

import React from 'react';
import Link from 'next/link';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { useAuth } from '@/lib/auth/auth-context';
import { ROLE_LABELS, canAccessAnalysis, canAccessReview } from '@/lib/auth/roles';

export default function Home() {
  const { user } = useAuth();
  const role = user?.role || 'super_admin';

  return (
    <AuthGuard>
      <AppShell activeKey="overview" flowStep={1}>
        <div style={{ maxWidth: '1200px', margin: '0 auto' }}>
          {/* Header */}
          <div style={{ marginBottom: 'var(--space-6)' }}>
            <h1 style={{ fontSize: '24px', fontWeight: 700, margin: '0 0 8px', color: 'var(--ink)' }}>
              Trung tâm Kiểm soát Chất lượng (Quality Control Home)
            </h1>
            <p style={{ margin: 0, color: 'var(--ink-muted)', fontSize: '14px' }}>
              Chào mừng, <strong>{user?.fullName}</strong> ({ROLE_LABELS[role]}). Phiên làm việc hiện tại: Road Vision Urban · v1.4.
            </p>
          </div>

          {/* Metric cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}>
            <div className="lx-card" style={{ padding: 'var(--space-4)' }}>
              <div style={{ fontSize: '12px', color: 'var(--ink-subtle)', textTransform: 'uppercase', fontWeight: 600 }}>Tỷ lệ lỗi (Error Rate)</div>
              <div style={{ fontSize: '28px', fontWeight: 700, margin: '8px 0', color: 'var(--warning)' }}>2.4%</div>
              <div style={{ fontSize: '12px', color: 'var(--ink-muted)' }}>Mục tiêu: ≤ 2.0% (Chưa đạt QC Gate)</div>
            </div>

            <div className="lx-card" style={{ padding: 'var(--space-4)' }}>
              <div style={{ fontSize: '12px', color: 'var(--ink-subtle)', textTransform: 'uppercase', fontWeight: 600 }}>Khối lượng Review</div>
              <div style={{ fontSize: '28px', fontWeight: 700, margin: '8px 0', color: 'var(--ink)' }}>1,420</div>
              <div style={{ fontSize: '12px', color: 'var(--ink-muted)' }}>86 ảnh đang chờ xác minh</div>
            </div>

            <div className="lx-card" style={{ padding: 'var(--space-4)' }}>
              <div style={{ fontSize: '12px', color: 'var(--ink-subtle)', textTransform: 'uppercase', fontWeight: 600 }}>Coverage Guideline</div>
              <div style={{ fontSize: '28px', fontWeight: 700, margin: '8px 0', color: 'var(--success)' }}>98.6%</div>
              <div style={{ fontSize: '12px', color: 'var(--ink-muted)' }}>42/43 quy tắc được kiểm tra</div>
            </div>

            <div className="lx-card" style={{ padding: 'var(--space-4)' }}>
              <div style={{ fontSize: '12px', color: 'var(--ink-subtle)', textTransform: 'uppercase', fontWeight: 600 }}>Trạng thái Snapshot</div>
              <div style={{ fontSize: '28px', fontWeight: 700, margin: '8px 0', color: 'var(--info)' }}>PARTIAL</div>
              <div style={{ fontSize: '12px', color: 'var(--ink-muted)' }}>#QC-091 đang chạy lấy mẫu</div>
            </div>
          </div>

          {/* Quick Action Navigation according to permissions */}
          <div className="lx-card" style={{ padding: 'var(--space-6)' }}>
            <h2 style={{ fontSize: '16px', fontWeight: 600, margin: '0 0 var(--space-4)' }}>
              Thao tác theo phân quyền vai trò
            </h2>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 'var(--space-4)' }}>
              {canAccessAnalysis(role) ? (
                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)' }}>
                  <h3 style={{ fontSize: '14px', margin: '0 0 6px' }}>Phân tích Chất lượng</h3>
                  <p style={{ fontSize: '13px', color: 'var(--ink-muted)', margin: '0 0 12px' }}>Chạy snapshot kiểm tra quy tắc tự động và trích xuất lỗi.</p>
                  <Link href="/analysis" className="lx-btn lx-btn--primary lx-btn--sm">Truy cập Phân tích</Link>
                </div>
              ) : (
                <div style={{ border: '1px dashed var(--border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)', opacity: 0.6 }}>
                  <h3 style={{ fontSize: '14px', margin: '0 0 6px', color: 'var(--ink-subtle)' }}>Phân tích Chất lượng</h3>
                  <p style={{ fontSize: '13px', color: 'var(--ink-subtle)', margin: '0 0 12px' }}>Bị hạn chế: Chỉ dành cho QA Lead và Admin.</p>
                  <span className="lx-badge lx-badge--warning">Bị ẩn trên thanh điều hướng</span>
                </div>
              )}

              {canAccessReview(role) ? (
                <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)' }}>
                  <h3 style={{ fontSize: '14px', margin: '0 0 6px' }}>Trung tâm Review</h3>
                  <p style={{ fontSize: '13px', color: 'var(--ink-muted)', margin: '0 0 12px' }}>Hàng đợi kiểm duyệt và workspace sửa lỗi gán nhãn.</p>
                  <Link href="/review" className="lx-btn lx-btn--primary lx-btn--sm">Vào Review Center</Link>
                </div>
              ) : (
                <div style={{ border: '1px dashed var(--border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)', opacity: 0.6 }}>
                  <h3 style={{ fontSize: '14px', margin: '0 0 6px', color: 'var(--ink-subtle)' }}>Trung tâm Review</h3>
                  <p style={{ fontSize: '13px', color: 'var(--ink-subtle)', margin: '0 0 12px' }}>Bị hạn chế: Vai trò Annotator chỉ thực hiện Rework được giao.</p>
                  <span className="lx-badge lx-badge--warning">Bị ẩn trên thanh điều hướng</span>
                </div>
              )}

              <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-4)' }}>
                <h3 style={{ fontSize: '14px', margin: '0 0 6px' }}>Cấu hình & Phân quyền</h3>
                <p style={{ fontSize: '13px', color: 'var(--ink-muted)', margin: '0 0 12px' }}>Xem ma trận phân quyền theo vai trò (RBAC) và quy tắc kiểm soát.</p>
                <Link href="/configuration" className="lx-btn lx-btn--ghost lx-btn--sm" style={{ border: '1px solid var(--border)' }}>Xem ma trận quyền</Link>
              </div>
            </div>
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
