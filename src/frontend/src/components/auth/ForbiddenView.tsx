'use client';

import React from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth/auth-context';
import { ROLE_LABELS } from '@/lib/auth/roles';
import type { ApiError } from '@/types/auth';

interface ForbiddenViewProps {
  requiredPermission?: string;
  reason?: string;
  errorCode?: ApiError['code'];
}

export function ForbiddenView({ requiredPermission, reason, errorCode = 'FORBIDDEN' }: ForbiddenViewProps) {
  const { user } = useAuth();
  const roleName = user?.role ? ROLE_LABELS[user.role] : 'Chưa có quyền trong phạm vi này';

  return (
    <div style={{ maxWidth: '640px', margin: '48px auto', padding: '0 var(--space-4)' }}>
      <div className="lx-card" style={{ padding: 'var(--space-6)', textAlign: 'center' }}>
        <div style={{ display: 'inline-flex', padding: 'var(--space-3)', background: 'var(--warning-soft)', borderRadius: '50%', marginBottom: 'var(--space-4)' }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--warning)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>

        <h1 style={{ fontSize: '20px', fontWeight: 600, margin: '0 0 var(--space-2)' }}>
          403 - Quyền truy cập bị từ chối
        </h1>

        <p style={{ color: 'var(--ink-muted)', fontSize: '14px', lineHeight: 1.5, margin: '0 0 var(--space-4)' }}>
          {reason || 'Bạn không có đủ quyền để truy cập trang này.'}
        </p>

        <div style={{ background: 'var(--surface-sunken)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 'var(--space-3)', margin: '0 0 var(--space-6)', textAlign: 'left', fontSize: '13px' }}>
          <div style={{ marginBottom: '4px' }}>
            <span style={{ color: 'var(--ink-subtle)' }}>Vai trò hiện tại: </span>
            <strong>{roleName}</strong>
          </div>
          {requiredPermission && (
            <div>
              <span style={{ color: 'var(--ink-subtle)' }}>Yêu cầu: </span>
              <code>{requiredPermission}</code>
            </div>
          )}
          <div style={{ marginTop: '4px' }}>
            <span style={{ color: 'var(--ink-subtle)' }}>Mã lỗi: </span>
            <span className="lx-mono">{errorCode}</span>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'center' }}>
          <Link href="/" className="lx-btn lx-btn--primary">
            Quay về Trang chủ
          </Link>
        </div>
      </div>
    </div>
  );
}
