'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth/auth-context';
import type { MockUserRecord } from '@/lib/auth/mock-users';
import { ROLE_LABELS } from '@/lib/auth/roles';
import { apiBaseUrl, isMockAuth } from '@/lib/auth/config';
import { FALLBACK_ERROR_MESSAGE } from '@/lib/api/errors';

export default function LoginPage() {
  const { login, isAuthenticated, isLoading, authError } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [mockUsers, setMockUsers] = useState<MockUserRecord[]>([]);

  // Demo accounts come from a dev-only route handler; production builds never fetch or bundle them.
  React.useEffect(() => {
    if (process.env.NODE_ENV === 'production' || !isMockAuth) return;
    const controller = new AbortController();
    fetch(new Request(apiBaseUrl() + '/api/auth/mock-users/', { cache: 'no-store', signal: controller.signal }))
      .then((response) => (response.ok ? response.json() : []))
      .then((users: MockUserRecord[]) => setMockUsers(users))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  React.useEffect(() => {
    if (isAuthenticated) {
      router.push('/');
    }
  }, [isAuthenticated, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const result = await login({ username, password });
    if (!result.success) {
      setError(result.error || FALLBACK_ERROR_MESSAGE);
      setLoading(false);
    }
  };

  const handleQuickPick = (u: MockUserRecord) => {
    setUsername(u.username);
    setPassword(u.password);
    setError(null);
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--canvas)', padding: 'var(--space-4)' }}>
      <div className="lx-card" style={{ width: '100%', maxWidth: '440px', padding: 'var(--space-6)' }}>
        <div style={{ textAlign: 'center', marginBottom: 'var(--space-6)' }}>
          <div style={{ fontSize: '26px', fontWeight: 800, color: 'var(--ink)' }}>
            Label<span style={{ color: 'var(--brand)' }}>X</span>
          </div>
          <div style={{ fontSize: '13px', color: 'var(--ink-muted)', marginTop: '4px' }}>
            Hệ thống Kiểm soát Chất lượng Annotation CVAT
          </div>
        </div>

        {(error || authError) && (
          <div
            role="alert"
            className="lx-callout"
          >
            {error || authError}
          </div>
        )}

        <form onSubmit={handleSubmit} className="lx-stack">
          <div className="lx-field">
            <label htmlFor="username" className="lx-label">
              Tên đăng nhập
            </label>
            <input
              id="username"
              type="text"
              className="lx-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={isMockAuth ? 'admin, reviewer, annotator...' : 'Tên đăng nhập của bạn'}
              required
            />
          </div>

          <div className="lx-field">
            <label htmlFor="password" className="lx-label">
              Mật khẩu
            </label>
            <input
              id="password"
              type="password"
              className="lx-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Nhập mật khẩu"
              required
            />
          </div>

          <button
            type="submit"
            className="lx-btn lx-btn--primary"
            style={{ width: '100%', justifyContent: 'center', height: '36px' }}
            disabled={loading || isLoading}
          >
            {loading ? 'Đang xác thực...' : 'Đăng nhập vào LabelX'}
          </button>
        </form>

        {isMockAuth && mockUsers.length > 0 && <div style={{ marginTop: 'var(--space-6)', borderTop: '1px solid var(--border)', paddingTop: 'var(--space-4)' }}>
          <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--ink-subtle)', marginBottom: '8px' }}>
            Tài khoản mẫu thử nghiệm (chọn nhanh):
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {mockUsers.map((u) => (
              <button
                key={u.id}
                type="button"
                className="lx-btn lx-btn--ghost lx-btn--sm"
                style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--space-2)', height: 'auto', padding: 'var(--space-2)', width: '100%', textAlign: 'left', border: '1px solid var(--border)' }}
                onClick={() => handleQuickPick(u)}
              >
                <span>
                  <strong>{u.username}</strong> ({u.fullName})
                </span>
                <span className="lx-badge lx-badge--info" style={{ fontSize: '11px' }}>
                  {ROLE_LABELS[u.role]}
                </span>
              </button>
            ))}
          </div>
        </div>}
      </div>
    </div>
  );
}
