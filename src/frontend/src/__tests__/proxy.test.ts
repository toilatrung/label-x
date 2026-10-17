import { afterEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { proxy } from '@/proxy';

afterEach(() => vi.unstubAllEnvs());

describe('server runtime API proxy', () => {
  it('reads the target on every request and preserves query parameters', () => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('NEXT_PUBLIC_AUTH_MODE', 'mock');
    const request = new NextRequest('https://label-x.williamtrinh.online/api/runs?status=running');
    for (const target of ['http://backend:8000', 'http://another-backend:9000']) {
      vi.stubEnv('LABELX_API_PROXY_TARGET', target);
      expect(proxy(request).headers.get('x-middleware-rewrite')).toBe(`${target}/api/runs/?status=running`);
    }
  });

  it.each(['/api/auth/login/', '/static/admin/css/base.css', '/admin/login/'])('preserves %s', path => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('LABELX_API_PROXY_TARGET', 'http://backend:8000/');
    const request = new NextRequest(`https://label-x.williamtrinh.online${path}`, { method: 'POST' });
    expect(proxy(request).headers.get('x-middleware-rewrite')).toBe(`http://backend:8000${path}`);
    expect(request.method).toBe('POST');
  });

  it('allows local mock routes only outside production', () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.stubEnv('NEXT_PUBLIC_AUTH_MODE', 'mock');
    expect(proxy(new NextRequest('http://localhost:3000/api/auth/csrf/')).headers.get('x-middleware-next')).toBe('1');
  });

  it.each(['not-a-url', 'ftp://backend', 'http://user:password@backend', 'http://backend/prefix'])('rejects invalid origin %s', target => {
    vi.stubEnv('NODE_ENV', 'production');
    vi.stubEnv('LABELX_API_PROXY_TARGET', target);
    expect(proxy(new NextRequest('http://localhost:3000/api/runs/')).status).toBe(503);
  });
});
