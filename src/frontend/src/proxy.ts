import { NextRequest, NextResponse } from 'next/server';

// Server-only runtime configuration. NEXT_PUBLIC_* values are frozen by next build.
export function proxy(request: NextRequest) {
  if (process.env.NODE_ENV !== 'production' && process.env.NEXT_PUBLIC_AUTH_MODE === 'mock') {
    return NextResponse.next();
  }
  let target: URL;
  try {
    target = new URL(process.env.LABELX_API_PROXY_TARGET || 'http://127.0.0.1:8000');
  } catch {
    return NextResponse.json({ message: 'API proxy target must be an HTTP(S) origin.' }, { status: 503 });
  }
  if (!['http:', 'https:'].includes(target.protocol) || target.username || target.password ||
      target.pathname !== '/' || target.search || target.hash) {
    return NextResponse.json({ message: 'API proxy target must be an HTTP(S) origin.' }, { status: 503 });
  }
  // A plain URL preserves the contract's trailing slash; NextURL can normalize it away.
  const destination = new URL(request.url);
  destination.protocol = target.protocol;
  destination.host = target.host;
  // Contract API paths require a slash, including POST, without a client redirect.
  if (destination.pathname.startsWith('/api/') && !destination.pathname.endsWith('/')) {
    destination.pathname += '/';
  }
  return NextResponse.rewrite(destination);
}

export const config = { matcher: ['/api/:path*', '/admin/:path*', '/static/:path*'] };
