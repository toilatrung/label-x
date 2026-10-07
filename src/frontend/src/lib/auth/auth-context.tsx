'use client';

import React, { createContext, useContext, useState } from 'react';
import { AuthUser, LoginCredentials, UserRole } from '@/types/auth';
import { MOCK_USERS, findMockUser } from '@/lib/auth/mock-users';

interface AuthContextType {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (credentials: LoginCredentials) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
  switchRole: (role: UserRole) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const STORAGE_KEY = 'lx_auth_user';

function toSafeUser(user: { id: string; username: string; fullName: string; role: UserRole; email: string; datasetScope?: string | null }): AuthUser {
  return {
    id: user.id,
    username: user.username,
    fullName: user.fullName,
    role: user.role,
    email: user.email,
    datasetScope: user.datasetScope,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    if (typeof window === 'undefined') return null;
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        return JSON.parse(stored);
      }
      return null;
    } catch {
      return toSafeUser(MOCK_USERS[0]);
    }
  });

  const [isLoading, setIsLoading] = useState<boolean>(false);

  const login = async (credentials: LoginCredentials): Promise<{ success: boolean; error?: string }> => {
    setIsLoading(true);
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
      });

      if (res.ok) {
        const data = await res.json();
        const loggedUser: AuthUser = data.user;
        setUser(loggedUser);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(loggedUser));
        return { success: true };
      } else {
        const err = await res.json().catch(() => ({}));
        return { success: false, error: err.message || 'Tên đăng nhập hoặc mật khẩu không chính xác' };
      }
    } catch {
      const mock = findMockUser(credentials.username, credentials.password);
      if (mock) {
        const safe = toSafeUser(mock);
        setUser(safe);
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(safe)); } catch {}
        return { success: true };
      }
      return { success: false, error: 'Tên đăng nhập hoặc mật khẩu không chính xác' };
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async (): Promise<void> => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch {
      // Bỏ qua lỗi mạng
    }
    setUser(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {}
  };

  const switchRole = (role: UserRole) => {
    const target = MOCK_USERS.find((u) => u.role === role) || MOCK_USERS[0];
    const safe = toSafeUser(target);
    setUser(safe);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(safe));
    } catch {}
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
        switchRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
