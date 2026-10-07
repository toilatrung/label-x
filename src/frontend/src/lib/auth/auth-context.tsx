'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { AuthSession, AuthUser, LoginCredentials, UserRole } from '@/types/auth';
import { apiClient, ApiRequestError, AUTH_EXPIRED_EVENT } from '@/lib/api/client';
import { hasDatasetPermission, rolesForDataset } from './roles';

type LoginResult = { success: boolean; error?: string };
interface AuthContextType {
  session: AuthSession | null;
  user: AuthUser | null;
  datasetId: number | null;
  setDatasetId: (id: number | null) => void;
  isLoading: boolean;
  isAuthenticated: boolean;
  authError: string | null;
  hasPermission: (check: (role: UserRole) => boolean, requiresIdentity?: boolean) => boolean;
  login: (credentials: LoginCredentials) => Promise<LoginResult>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);
const errorMessage = (error: unknown) => error instanceof ApiRequestError ? error.message :
  'Không kết nối được máy chủ. Vui lòng thử lại.';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [datasetId, setDatasetId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const revision = useRef(0);
  const initialRequest = useRef<AbortController | null>(null);
  const acceptSession = useCallback((value: AuthSession) => {
    setSession(value);
    // A global grant does not prove that any particular dataset exists.
    setDatasetId(value.roles.find((assignment) => assignment.dataset_id !== null)?.dataset_id ?? null);
    setAuthError(null);
  }, []);

  useEffect(() => {
    let mounted = true;
    const version = ++revision.current;
    const controller = new AbortController();
    initialRequest.current = controller;
    const expired = () => {
      ++revision.current;
      setSession(null);
      setDatasetId(null);
      setAuthError(null);
      setIsLoading(false);
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    apiClient.GET('/api/auth/session/', { cache: 'no-store', signal: controller.signal }).then(({ data, error, response }) => {
      if (!mounted || version !== revision.current) return;
      if (error || !data) throw new ApiRequestError(response.status, error);
      acceptSession(data);
    }).catch((error: unknown) => {
      if (!mounted || version !== revision.current) return;
      setSession(null);
      if (!(error instanceof ApiRequestError && error.detail?.code === 'NOT_AUTHENTICATED')) setAuthError(errorMessage(error));
    }).finally(() => {
      if (mounted && version === revision.current) setIsLoading(false);
    });
    return () => {
      mounted = false;
      controller.abort();
      window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
    };
  }, [acceptSession]);

  const login = async (credentials: LoginCredentials): Promise<LoginResult> => {
    initialRequest.current?.abort();
    ++revision.current; // A late initial session read must not overwrite a login.
    setIsLoading(true);
    setAuthError(null);
    try {
      const csrf = await apiClient.GET('/api/auth/csrf/');
      if (!csrf.response.ok) throw new ApiRequestError(csrf.response.status);
      const { data, error, response } = await apiClient.POST('/api/auth/login/', { body: credentials });
      if (error || !data) throw new ApiRequestError(response.status, error);
      acceptSession(data);
      return { success: true };
    } catch (error) {
      const message = errorMessage(error);
      setAuthError(message);
      return { success: false, error: message };
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    initialRequest.current?.abort();
    ++revision.current;
    setAuthError(null);
    try {
      const csrf = await apiClient.GET('/api/auth/csrf/');
      if (!csrf.response.ok) throw new ApiRequestError(csrf.response.status);
      const result = await apiClient.POST('/api/auth/logout/');
      if (!result.response.ok) throw new ApiRequestError(result.response.status);
      setSession(null);
      setDatasetId(null);
    } catch (error) {
      // Keep the session visible on a network failure: the server has not confirmed logout.
      setAuthError(errorMessage(error));
    }
  };

  const roles = rolesForDataset(session, datasetId);
  const user: AuthUser | null = session ? {
    ...session.user, fullName: session.user.display_name, role: roles[0] ?? null,
  } : null;

  return <AuthContext.Provider value={{
    session, user, datasetId, setDatasetId, isLoading, isAuthenticated: !!session,
    authError, login, logout,
    hasPermission: (check, requiresIdentity = false) => hasDatasetPermission(session, datasetId, check, requiresIdentity),
  }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextType {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used within an AuthProvider');
  return value;
}
