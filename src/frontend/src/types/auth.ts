import type { components } from '@/lib/api/contract';

export type UserRole = components['schemas']['Role'];
export type RoleAssignment = components['schemas']['RoleAssignment'];
export type AuthSession = components['schemas']['Session'];
export type LoginCredentials = components['schemas']['LoginRequest'];
export type ApiError = components['schemas']['Error'];

// Presentation fields come from the server session, never browser storage.
export type AuthUser = AuthSession['user'] & { fullName: string; role: UserRole | null };
