import type { NextConfig } from "next";

// src/proxy.ts resolves the backend at request time, including in standalone Docker images.
// Next serializes this timeout at build time; it is not a runtime image setting.
const proxyTimeout = Number(process.env.LABELX_API_PROXY_TIMEOUT_MS) || 300_000;

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: { proxyTimeout, proxyClientMaxBodySize: "32mb" },
  devIndicators: false,
  // Contract paths end in a slash; POST requests must not redirect.
  skipTrailingSlashRedirect: true,
  // Dev: allow opening LabelX via 127.0.0.1.
  allowedDevOrigins: ['127.0.0.1'],
};

export default nextConfig;
