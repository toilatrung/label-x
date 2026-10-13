import type { ApiEndpoint } from '../types';
import { configVersion } from '../examples';

export const CONFIGURATION_ENDPOINTS = [
  { id: 'config_versions_list', method: 'GET', path: '/api/config-versions/', group: 'Configuration', summary: 'Danh sách phiên bản cấu hình', connection: 'backend', responseStatus: 200, response: { next: null, previous: null, results: [configVersion] } },
  { id: 'config_versions_create', method: 'POST', path: '/api/config-versions/', group: 'Configuration', summary: 'Tạo phiên bản cấu hình nháp', connection: 'backend', responseStatus: 201, response: { ...configVersion, status: 'draft', published_at: null } },
  { id: 'config_versions_publish', method: 'POST', path: '/api/config-versions/{id}/publish/', group: 'Configuration', summary: 'Publish phiên bản cấu hình', connection: 'backend', responseStatus: 200, response: configVersion },
  { id: 'review_policy_retrieve', method: 'GET', path: '/api/review-policy/', group: 'Configuration', summary: 'Chính sách lease và effort đang áp dụng', connection: 'backend', responseStatus: 200, response: { policy_version: 'pilot-1', source: 'settings', decision_status: 'approved', lease_ttl_seconds: 900, resume_reservation_seconds: 300, idle_threshold_seconds: 120, idle_gap_rule: 'exclude_over_threshold', immediate_exclusion_reasons: ['hidden', 'offline'], renew_on: 'successful_write' } },
  { id: 'workflow_rule_update', method: 'PATCH', path: '/api/auth/workflow-permissions/rules/{rule}/', group: 'Configuration', summary: 'Bật hoặc tắt quy tắc workflow', connection: 'mock', origin: 'design', responseStatus: 200, response: { rule: 'anti_self_review', enforced: true, updated_by: 7, updated_at: '2026-10-12T06:00:00Z' } },
  { id: 'models_list', method: 'GET', path: '/api/models/', group: 'Configuration', summary: 'Danh sách model và artifact version', connection: 'mock', origin: 'design', responseStatus: 200, response: { results: [
    { id: 5, name: 'Detector', version: 'v2.3', role: 'Phát hiện object độc lập', class_mapping: 'Taxonomy v3 · 12 lớp', taxonomy_version: 'v3', confidence_threshold: 0.6, status: 'active' },
    { id: 6, name: 'Classifier', version: 'v1.8', role: 'Kiểm tra lại nhãn của object', class_mapping: 'Taxonomy v3 · 12 lớp', taxonomy_version: 'v3', confidence_threshold: 0.7, status: 'active' },
    { id: 7, name: 'Mô hình thị giác – ngôn ngữ', version: 'v0.9', role: 'Kiểm tra có chọn lọc', class_mapping: 'Mô tả bằng văn bản', taxonomy_version: 'v3', confidence_threshold: null, status: 'experimental' },
  ] } },
  { id: 'models_update', method: 'PATCH', path: '/api/models/{id}/', group: 'Configuration', summary: 'Cập nhật cấu hình model', connection: 'mock', origin: 'design', responseStatus: 200, response: { id: 5, name: 'Detector', version: 'v2.3', confidence_threshold: 0.65, status: 'active', updated_by: 7 } },
  { id: 'config_version_rules', method: 'GET', path: '/api/config-versions/{id}/rules/', group: 'Configuration', summary: 'Rule, ngưỡng gate và chính sách lấy mẫu', connection: 'mock', origin: 'design', responseStatus: 200, response: { config_version_id: 7, rules: [
    { id: 'S-001', name: 'Thiếu thuộc tính bắt buộc', group: 'Schema', enabled: true, severity: 'critical', threshold_label: '—' },
    { id: 'G-009', name: 'Biên polygon lệch so với vật thể', group: 'Geometry', enabled: true, severity: 'medium', threshold_label: 'Dung sai 2 px', tolerance_px: 2 },
    { id: 'G-014', name: 'Bounding box quá nhỏ hoặc nằm ngoài khung', group: 'Geometry', enabled: true, severity: 'medium', threshold_label: 'Tối thiểu 24 px²', minimum_area: 24 },
    { id: 'D-002', name: 'Hai annotation chồng lấn cùng lớp', group: 'Duplicate', enabled: true, severity: 'medium', threshold_label: 'Intersection over Union ≥ 0.85', iou_threshold: 0.85 },
    { id: 'A-003', name: 'Thuộc tính occluded thiếu nhất quán', group: 'Attribute', enabled: false, severity: 'minor', threshold_label: '—' },
  ], gate_thresholds: configVersion.thresholds, sampling: configVersion.sampling } },
] satisfies ApiEndpoint[];
