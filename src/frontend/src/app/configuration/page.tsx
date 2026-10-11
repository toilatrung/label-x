'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { apiClient, ApiRequestError } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import type { components } from '@/lib/api/contract';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { canAccessConfiguration, ROLE_LABELS } from '@/lib/auth/roles';
import type { UserRole } from '@/types/auth';

type WorkflowPermissions = components['schemas']['WorkflowPermissions'];

// Thiết kế chỉ hiển thị năm vai trò; Product Owner và Data/Model Owner không có cột trong WorkflowPermissions.dc.html.
const ROLE_ORDER: UserRole[] = ['annotator', 'reviewer', 'qa_lead', 'qc_admin', 'super_admin'];

// Mã quyền từ API → nhãn tiếng Việt theo thiết kế. Mã lạ giữ nguyên để không che dữ liệu thật.
const PERMISSION_LABELS: Record<string, string> = {
  none: '—', yes: 'Có', limited: 'Giới hạn', full_including_permissions: 'Có, gồm cả Permissions',
  view: 'Xem', view_assigned: 'Xem được giao', view_all: 'Xem tất cả', view_kpi: 'Xem chỉ số',
  run_view: 'Chạy / xem', configure: 'Cấu hình', run_configure: 'Chạy / cấu hình',
  review: 'Review', review_monitor: 'Review / giám sát', execute: 'Thực hiện',
  request_verify: 'Yêu cầu / xác minh', request_monitor: 'Yêu cầu / giám sát', execute_verify: 'Thực hiện / xác minh',
  override_with_reason: 'Có (ghi đè)', participate: 'Tham gia', manage: 'Quản lý', manage_configure: 'Quản lý / cấu hình',
  authorized: 'Người được cấp quyền',
};

const permissionLabel = (code: string) => PERMISSION_LABELS[code] ?? code;
const functionLabel = (name: string) => name.replace(' & ', ' và ');

async function fetchWorkflowPermissions(): Promise<WorkflowPermissions> {
  const { data, error, response } = await apiClient.GET('/api/auth/workflow-permissions/');
  if (error || !data) throw new ApiRequestError(response.status, error, response.headers);
  return data;
}

function WorkflowPermissionsView() {
  const query = useQuery({ queryKey: ['workflow-permissions'], queryFn: fetchWorkflowPermissions, retry: false });
  const data = query.data;
  return (
    <div className="lx-page">
      <div className="lx-head"><div className="lx-head__text">
        <h1 className="lx-h1">Workflow và Permissions</h1>
        <p className="lx-lead">Phân quyền theo vai trò và các quy tắc quy trình. Backend luôn kiểm tra quyền; việc ẩn nút trên giao diện chỉ để thuận tiện.</p>
      </div></div>
      {query.isError && <div className="lx-callout" role="alert">
        <strong>Không tải được ma trận phân quyền</strong><div>{errorMessage(query.error)}</div>
      </div>}
      <div className="lx-cols">
        <section className="lx-card lx-main" aria-label="Quyền theo vai trò">
          <div className="lx-card__head"><h2 className="lx-h2">Quyền theo vai trò</h2></div>
          <div className="lx-scroll">
            <table className="lx-table lx-matrix lx-table--min-760">
              <thead><tr><th>Chức năng</th>{ROLE_ORDER.map(role => <th key={role} className="c">{ROLE_LABELS[role]}</th>)}</tr></thead>
              <tbody>
                {query.isLoading && <tr><td colSpan={ROLE_ORDER.length + 1}>Đang tải…</td></tr>}
                {data && data.matrix.length === 0 && <tr><td colSpan={ROLE_ORDER.length + 1} className="lx-subtle">Chưa có ma trận phân quyền.</td></tr>}
                {data?.matrix.map(row => <tr key={row.function}>
                  <td className="lx-cell__main">{functionLabel(row.function)}</td>
                  {ROLE_ORDER.map(role => {
                    const code = row.roles[role];
                    return <td key={role} className={`c ${code === 'none' ? 'lx-no' : 'lx-yes'}`}>{permissionLabel(code)}</td>;
                  })}
                </tr>)}
              </tbody>
            </table>
          </div>
        </section>
        <aside className="lx-card lx-side" aria-label="Quy tắc quy trình">
          <div className="lx-card__head"><h2 className="lx-h2">Quy tắc quy trình</h2></div>
          <div className="lx-card__body lx-stack lx-stack--rows">
            {/* TODO(backend): PATCH /api/auth/workflow-permissions/rules/{rule}/ (bật/tắt quy tắc); công tắc chỉ phản ánh `enforced`, không ghi */}
            <NotConnectedNotice detail="Công tắc quy tắc chỉ hiển thị trạng thái áp dụng hiện tại" />
            {data?.rules.map(rule => <div key={rule.rule} className="lx-row lx-row--between lx-row--nowrap">
              <div>
                <div className="lx-cell__main">{rule.name}</div>
                <div className="lx-hint">{rule.description}</div>
                <span className={rule.enforced ? 'lx-badge lx-badge--success' : 'lx-badge'}>{rule.enforced ? 'Đã áp dụng' : 'Chờ triển khai'}</span>
              </div>
              <label className="lx-switch"><input type="checkbox" checked={rule.enforced} disabled readOnly aria-label={rule.name} /><span></span></label>
            </div>)}
          </div>
        </aside>
      </div>
    </div>
  );
}

export default function ConfigurationPage() {
  return <AuthGuard permissionCheck={canAccessConfiguration} requiredPermissionName="QA Lead / QC Admin / Super Admin">
    <AppShell activeKey="configuration"><WorkflowPermissionsView /></AppShell>
  </AuthGuard>;
}
