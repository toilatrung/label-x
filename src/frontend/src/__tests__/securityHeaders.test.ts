import { describe, expect, it } from 'vitest';
import nextConfig from '../../next.config';

// Matches the Django API (config/production.py) so frontend and backend answer alike.
const EXPECTED: Record<string, string> = {
  'Strict-Transport-Security': 'max-age=31536000',
  'X-Frame-Options': 'DENY',
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'same-origin',
};

async function rules() {
  expect(nextConfig.headers).toBeTypeOf('function');
  return (await nextConfig.headers!()) as { source: string; headers: { key: string; value: string }[] }[];
}

function headersFor(all: Awaited<ReturnType<typeof rules>>, path: string) {
  const found: Record<string, string> = {};
  for (const rule of all) {
    if (new RegExp(`^${rule.source}$`).test(path)) {
      for (const { key, value } of rule.headers) found[key] = value;
    }
  }
  return found;
}

describe('frontend security headers', () => {
  it.each(['/', '/login', '/snapshots', '/review/12/workspace', '/_next/static/chunks/app.js'])(
    'sets the full header set on %s',
    async (path) => {
      expect(headersFor(await rules(), path)).toEqual(EXPECTED);
    },
  );

  it.each(['/api/auth/session/', '/admin/login/', '/static/admin/css/base.css'])(
    'leaves backend-proxied %s to Django so headers are not duplicated',
    async (path) => {
      expect(headersFor(await rules(), path)).toEqual({});
    },
  );

  it('does not ship a Content-Security-Policy yet and keeps proxy/standalone settings', async () => {
    const keys = (await rules()).flatMap((rule) => rule.headers.map((h) => h.key.toLowerCase()));
    expect(keys).not.toContain('content-security-policy');
    expect(nextConfig.output).toBe('standalone');
    expect(nextConfig.skipTrailingSlashRedirect).toBe(true);
  });
});
