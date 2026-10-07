// Demo accounts and mock endpoints are always disabled in production builds.
export const isMockAuth = process.env.NODE_ENV !== 'production' &&
  (process.env.NEXT_PUBLIC_AUTH_MODE === 'mock' || !process.env.NEXT_PUBLIC_AUTH_MODE);

export function apiBaseUrl(): string {
  if (isMockAuth) return typeof window === 'undefined' ? 'http://localhost:3000' : window.location.origin;
  // Environment paths end in /api; contract paths already include /api/.
  return (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/api\/?$/, '').replace(/\/$/, '');
}
