import type { ApiEndpoint } from '../types';
import { session } from '../examples';

export const AUTH_ENDPOINTS = [
  { id: 'auth_csrf', method: 'GET', path: '/api/auth/csrf/', group: 'Auth', summary: 'Đặt cookie CSRF', connection: 'backend', responseStatus: 204, response: null },
  { id: 'auth_login', method: 'POST', path: '/api/auth/login/', group: 'Auth', summary: 'Đăng nhập và tạo session', connection: 'backend', responseStatus: 200, response: session },
  { id: 'auth_logout', method: 'POST', path: '/api/auth/logout/', group: 'Auth', summary: 'Đăng xuất và huỷ session', connection: 'backend', responseStatus: 204, response: null },
  { id: 'auth_session', method: 'GET', path: '/api/auth/session/', group: 'Auth', summary: 'Lấy phiên đăng nhập hiện tại', connection: 'backend', responseStatus: 200, response: session },
  { id: 'auth_workflow_permissions', method: 'GET', path: '/api/auth/workflow-permissions/', group: 'Auth', summary: 'Ma trận phân quyền workflow', connection: 'backend', responseStatus: 200, response: { roles: ['annotator', 'reviewer', 'qa_lead', 'qc_admin', 'super_admin'], permissions: [
    { feature: 'Quality Summary', annotator: 'Giới hạn', reviewer: 'Xem', qa_lead: 'Đầy đủ', qc_admin: 'Đầy đủ', super_admin: 'Đầy đủ' },
    { feature: 'Quality Analysis', annotator: null, reviewer: null, qa_lead: 'Chạy / xem', qc_admin: 'Cấu hình', super_admin: 'Chạy / cấu hình' },
    { feature: 'Review Queues và Workspace', annotator: null, reviewer: 'Review', qa_lead: 'Review / giám sát', qc_admin: 'Xem', super_admin: 'Review / giám sát' },
    { feature: 'Rework', annotator: 'Thực hiện', reviewer: 'Yêu cầu / xác minh', qa_lead: 'Yêu cầu / giám sát', qc_admin: null, super_admin: 'Thực hiện / xác minh' },
    { feature: 'Adjudication', annotator: null, reviewer: null, qa_lead: 'Có', qc_admin: null, super_admin: 'Có (ghi đè)' },
    { feature: 'Calibration và Audit', annotator: 'Tham gia', reviewer: 'Tham gia', qa_lead: 'Quản lý', qc_admin: 'Cấu hình', super_admin: 'Quản lý / cấu hình' },
    { feature: 'Phê duyệt phát hành', annotator: null, reviewer: null, qa_lead: 'Người được cấp quyền', qc_admin: null, super_admin: 'Có (ghi đè)' },
    { feature: 'Configuration', annotator: null, reviewer: null, qa_lead: 'Giới hạn', qc_admin: 'Có', super_admin: 'Có, gồm cả Permissions' },
  ], rules: { anti_self_review: true, super_admin_override_reason: true, audit_logging: true, rework_verification: true } } },
] satisfies ApiEndpoint[];
