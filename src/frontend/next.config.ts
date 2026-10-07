import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Contract paths end in a slash; POST requests must not redirect.
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
