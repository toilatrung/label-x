import type { NextConfig } from "next";

// src/proxy.ts resolves the backend at request time, including in standalone Docker images.
// Next serializes this timeout at build time; it is not a runtime image setting.
const proxyTimeout = Number(process.env.LABELX_API_PROXY_TIMEOUT_MS) || 300_000;

// Same values as the Django API (config/production.py, SecurityMiddleware defaults), so every
// LabelX response is covered. Paths forwarded to the backend by src/proxy.ts are excluded: Django
// already sets these headers there and repeating them would duplicate them. No CSP yet: a strict
// one must first be checked against the UI (inline styles/scripts) before it is enabled.
const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: { proxyTimeout, proxyClientMaxBodySize: "32mb" },
  devIndicators: false,
  async headers() {
    return [{ source: "/((?!api/|admin/|static/).*)", headers: securityHeaders }];
  },
  // Contract paths end in a slash; POST requests must not redirect.
  skipTrailingSlashRedirect: true,
  // Dev: allow opening LabelX via 127.0.0.1.
  allowedDevOrigins: ['127.0.0.1'],
};

export default nextConfig;
