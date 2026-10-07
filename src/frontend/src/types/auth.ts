export type UserRole = 'super_admin' | 'qc_admin' | 'qa_lead' | 'reviewer' | 'annotator';

export interface AuthUser {
  id: string;
  username: string;
  fullName: string;
  role: UserRole;
  email: string;
  datasetScope?: string | null;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface AuthResponse {
  user: AuthUser;
  token?: string;
}

export interface ApiError {
  code: string;
  message: string;
  requestId?: string;
  details?: Record<string, unknown>;
}
