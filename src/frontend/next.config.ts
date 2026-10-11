import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Contract paths end in a slash; POST requests must not redirect.
  skipTrailingSlashRedirect: true,
  // Dev: mở LabelX qua 127.0.0.1 để cookie phiên tách khỏi CVAT (localhost:8080 dùng cùng tên
  // cookie sessionid/csrftoken; cookie không phân biệt cổng nên CVAT ghi đè phiên LabelX).
  allowedDevOrigins: ['127.0.0.1'],
};

export default nextConfig;
