import { vi } from 'vitest';
import { GET as csrf } from '@/app/api/auth/csrf/route';
import { POST as login } from '@/app/api/auth/login/route';
import { GET as session } from '@/app/api/auth/session/route';
import { POST as logout } from '@/app/api/auth/logout/route';

// A browser-like cookie jar connects components to the actual mock route handlers.
export function installMockAuthApi() {
  const jar = new Map<string, string>();
  const fetchSpy = vi.fn(async (input: Request) => {
    const headers = new Headers(input.headers);
    if (jar.size) headers.set('Cookie', [...jar].map(([key, value]) => key + '=' + value).join('; '));
    const request = new Request(input, { headers });
    const path = new URL(request.url).pathname;
    let response: Response;
    if (path === '/api/auth/csrf/' && request.method === 'GET') response = await csrf();
    else if (path === '/api/auth/login/' && request.method === 'POST') response = await login(request);
    else if (path === '/api/auth/session/' && request.method === 'GET') response = await session(request);
    else if (path === '/api/auth/logout/' && request.method === 'POST') response = await logout(request);
    else throw new Error('Unexpected API path: ' + path);
    for (const cookie of response.headers.getSetCookie()) {
      const [pair] = cookie.split(';');
      const split = pair.indexOf('=');
      const name = pair.slice(0, split);
      const value = pair.slice(split + 1);
      if (/Max-Age=0/i.test(cookie)) jar.delete(name);
      else jar.set(name, value);
      if (name === 'csrftoken') document.cookie = cookie;
    }
    return response;
  });
  vi.stubGlobal('fetch', fetchSpy);
  return {
    fetchSpy, jar,
    async signIn(username = 'admin', password = 'password123') {
      await fetchSpy(new Request('http://localhost:3000/api/auth/csrf/'));
      return fetchSpy(new Request('http://localhost:3000/api/auth/login/', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': jar.get('csrftoken')! },
        body: JSON.stringify({ username, password }),
      }));
    },
  };
}
