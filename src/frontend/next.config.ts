import type { NextConfig } from "next";

// The browser calls the API on the UI's own origin and Next forwards /api to Django. Cookies
// (sessionid, csrftoken) then belong to the UI host only, so a CVAT on another port of the same
// host, or opening the UI as localhost vs 127.0.0.1, cannot break the session or CSRF header.
const mockAuth = process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_AUTH_MODE === "mock";
const apiProxyTarget = (process.env.LABELX_API_PROXY_TARGET || "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  // Contract paths end in a slash; POST requests must not redirect.
  skipTrailingSlashRedirect: true,
  // The mock auth route handlers own /api/auth/* only in mock mode; elsewhere they answer 404,
  // so the proxy must run before the filesystem.
  rewrites: async () => (mockAuth ? [] : {
    // Django needs the trailing slash of contract paths; Next drops it from :path*.
    beforeFiles: [
      { source: "/api/:path*/", destination: `${apiProxyTarget}/api/:path*/` },
      { source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` },
    ],
    afterFiles: [],
    fallback: [],
  }),
};

export default nextConfig;
