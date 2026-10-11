// Demo accounts and mock endpoints are always disabled in production builds.
export const isMockAuth = process.env.NODE_ENV !== 'production' &&
  process.env.NEXT_PUBLIC_AUTH_MODE === 'mock';

export function apiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL;
  // Default: same origin as the UI. next.config.ts proxies /api to the backend, which keeps
  // session and CSRF cookies first-party. Setting the variable calls the backend directly
  // (cross-site cookies: UI and API must then share one host name).
  if (isMockAuth || !configured) return typeof window === 'undefined' ? 'http://localhost:3000' : window.location.origin;
  // Environment paths end in /api; contract paths already include /api/.
  return configured.replace(/\/api\/?$/, '').replace(/\/$/, '');
}
