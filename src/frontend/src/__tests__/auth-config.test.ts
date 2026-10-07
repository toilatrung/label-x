import { describe, it, expect, vi } from 'vitest';

describe('Mock auth deployment boundary', () => {
  it.each(['', 'mock', 'backend'])('disables mock in production even with mode %s', async (mode) => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('NEXT_PUBLIC_AUTH_MODE', mode);
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://backend.example/api');
    vi.resetModules();
    const { isMockAuth, apiBaseUrl } = await import('@/lib/auth/config');
    expect(isMockAuth).toBe(false);
    expect(apiBaseUrl()).toBe('https://backend.example');
  });

  it('returns 404 from all demo auth endpoints in production even if mock was requested', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('NEXT_PUBLIC_AUTH_MODE', 'mock');
    vi.resetModules();
    const { GET: csrf } = await import('@/app/api/auth/csrf/route');
    const { POST: login } = await import('@/app/api/auth/login/route');
    const { GET: session } = await import('@/app/api/auth/session/route');
    const { POST: logout } = await import('@/app/api/auth/logout/route');
    const { GET: mockUsers } = await import('@/app/api/auth/mock-users/route');
    const request = new Request('http://localhost:3000/api/auth/login/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: 'password123' }),
    });
    const responses = [await csrf(), await login(request), await session(request), await logout(request), await mockUsers()];
    for (const response of responses) {
      expect(response.status).toBe(404);
      expect(response.headers.get('set-cookie')).toBeNull();
    }
  });

  it('keeps mock available for local development and allows opting into the backend', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('NEXT_PUBLIC_AUTH_MODE', '');
    vi.resetModules();
    expect((await import('@/lib/auth/config')).isMockAuth).toBe(true);
    vi.stubEnv('NEXT_PUBLIC_AUTH_MODE', 'backend');
    vi.resetModules();
    expect((await import('@/lib/auth/config')).isMockAuth).toBe(false);
  });
});
