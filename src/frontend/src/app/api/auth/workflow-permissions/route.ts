import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export const MOCK_WORKFLOW_PERMISSIONS = {
  roles: ['annotator', 'reviewer', 'qa_lead', 'qc_admin', 'super_admin'],
  matrix: [
    {
      function: 'Quality Summary',
      roles: {
        annotator: 'limited',
        reviewer: 'view',
        qa_lead: 'full_including_permissions',
        qc_admin: 'full_including_permissions',
        super_admin: 'full_including_permissions',
      },
    },
    {
      function: 'Quality Analysis',
      roles: {
        annotator: 'none',
        reviewer: 'none',
        qa_lead: 'run_view',
        qc_admin: 'configure',
        super_admin: 'run_configure',
      },
    },
    {
      function: 'Review Queues và Workspace',
      roles: {
        annotator: 'none',
        reviewer: 'review',
        qa_lead: 'review_monitor',
        qc_admin: 'view',
        super_admin: 'review_monitor',
      },
    },
    {
      function: 'Rework',
      roles: {
        annotator: 'execute',
        reviewer: 'request_verify',
        qa_lead: 'request_monitor',
        qc_admin: 'none',
        super_admin: 'execute_verify',
      },
    },
    {
      function: 'Adjudication',
      roles: {
        annotator: 'none',
        reviewer: 'none',
        qa_lead: 'yes',
        qc_admin: 'none',
        super_admin: 'override_with_reason',
      },
    },
    {
      function: 'Calibration và Audit',
      roles: {
        annotator: 'participate',
        reviewer: 'participate',
        qa_lead: 'manage',
        qc_admin: 'configure',
        super_admin: 'manage_configure',
      },
    },
    {
      function: 'Phê duyệt phát hành',
      roles: {
        annotator: 'none',
        reviewer: 'none',
        qa_lead: 'authorized',
        qc_admin: 'none',
        super_admin: 'override_with_reason',
      },
    },
    {
      function: 'Configuration',
      roles: {
        annotator: 'none',
        reviewer: 'none',
        qa_lead: 'limited',
        qc_admin: 'yes',
        super_admin: 'full_including_permissions',
      },
    },
  ],
  rules: [
    {
      rule: 'anti_self_review',
      name: 'Reviewer không review annotation của chính mình',
      description: 'Backend từ chối khi trùng người',
      enforced: true,
    },
    {
      rule: 'super_admin_override_reason',
      name: 'Ghi đè của Super Admin phải có lý do',
      description: 'Áp dụng cho quyết định, phân xử, waiver, phê duyệt phát hành, duyệt guideline',
      enforced: true,
    },
    {
      rule: 'audit_logging',
      name: 'Mọi thao tác ghi nhật ký kiểm toán',
      description: 'Gắn nhãn Super Admin khi dùng quyền ghi đè',
      enforced: true,
    },
    {
      rule: 'verify_after_rework',
      name: 'Yêu cầu xác minh sau khi sửa',
      description: 'Issue chỉ đóng sau khi reviewer xác minh',
      enforced: true,
    },
  ],
  user_roles: [
    { role: 'qa_lead', dataset_id: 14 },
    { role: 'qc_admin', dataset_id: 14 },
    { role: 'super_admin', dataset_id: null },
  ],
};

export async function GET(request: Request) {
  if (!isMockAuth && process.env.NODE_ENV === 'production') {
    return NextResponse.json(
      { code: 'NOT_FOUND', message: 'API mẫu chưa được bật.' },
      { status: 404 }
    );
  }

  void request;
  return NextResponse.json(MOCK_WORKFLOW_PERMISSIONS, {
    headers: { 'Cache-Control': 'no-store' },
  });
}
