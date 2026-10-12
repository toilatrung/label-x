import type { ApiEndpoint } from '../types';
import { session } from '../examples';

export const AUTH_ENDPOINTS = [
  { id: 'auth_csrf', method: 'GET', path: '/api/auth/csrf/', group: 'Auth', summary: 'Đặt cookie CSRF', connection: 'backend', responseStatus: 204, response: null },
  { id: 'auth_login', method: 'POST', path: '/api/auth/login/', group: 'Auth', summary: 'Đăng nhập và tạo session', connection: 'backend', responseStatus: 200, response: session },
  { id: 'auth_logout', method: 'POST', path: '/api/auth/logout/', group: 'Auth', summary: 'Đăng xuất và huỷ session', connection: 'backend', responseStatus: 204, response: null },
  { id: 'auth_session', method: 'GET', path: '/api/auth/session/', group: 'Auth', summary: 'Lấy phiên đăng nhập hiện tại', connection: 'backend', responseStatus: 200, response: session },
  { id: 'auth_workflow_permissions', method: 'GET', path: '/api/auth/workflow-permissions/', group: 'Auth', summary: 'Ma trận phân quyền workflow', connection: 'backend', responseStatus: 200, response: { roles: ['annotator', 'reviewer', 'qa_lead', 'qc_admin', 'super_admin'], rules: { anti_self_review: true, separation_of_duties: true } } },
] satisfies ApiEndpoint[];
