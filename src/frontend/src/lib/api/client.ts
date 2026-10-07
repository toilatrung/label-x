/**
 * API client cho guideline module — dùng openapi-fetch.
 *
 * Theo coding-standards.html: gọi API bằng openapi-fetch,
 * quản lý server state bằng TanStack Query.
 *
 * BASE_URL đọc từ env NEXT_PUBLIC_API_URL (mặc định :8000).
 */

import createClient from "openapi-fetch";
import type { paths } from "@/lib/api/schema";

// Base URL của backend — đặt trong .env.local:
//   NEXT_PUBLIC_API_URL=http://localhost:8000
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Client chung cho toàn bộ API — credentials: "include" để gửi session cookie.
export const apiClient = createClient<paths>({
  baseUrl: BASE_URL,
  credentials: "include",
});
