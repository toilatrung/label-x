'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth/auth-context';
import { FALLBACK_ERROR_MESSAGE } from '@/lib/api/errors';
import { BrandLogo } from '@/components/ui/BrandLogo';
import styles from './login.module.css';

export default function LoginPage() {
  const { login, isAuthenticated, isLoading, authError } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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

  return (
    <main className={styles['lx-login']} lang="en">
      <header className={styles['lx-login__brand']}><BrandLogo /></header>

      <h1 className={styles['lx-login__headline']}>
        <span>Annotation</span>
        <span>Quality Control</span>
        <span>Platform</span>
      </h1>

      <section className={styles['lx-login__panel']} aria-labelledby="login-title">
        <h2 id="login-title" className={styles['lx-login__title']}>Sign in</h2>

        <form onSubmit={handleSubmit} className={styles['lx-login__form']} aria-busy={loading || isLoading}>
          <div className="lx-field">
            <label htmlFor="username" className={styles['lx-login__label']}>
              Email or username
            </label>
            <input
              id="username"
              name="username"
              type="text"
              className={`lx-input ${styles['lx-login__input']}`}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Email or username"
              autoComplete="username"
              required
            />
          </div>

          <div className="lx-field">
            <label htmlFor="password" className={styles['lx-login__label']}>
              Password
            </label>
            <input
              id="password"
              name="password"
              type="password"
              className={`lx-input ${styles['lx-login__input']}`}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              required
            />
          </div>

          {(error || authError) && (
            <div role="alert" lang="vi" className={`lx-callout ${styles['lx-login__error']}`}>
              {error || authError}
            </div>
          )}

          <button
            type="submit"
            className={`lx-btn lx-btn--primary ${styles['lx-login__submit']}`}
            disabled={loading || isLoading}
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

      </section>
    </main>
  );
}
