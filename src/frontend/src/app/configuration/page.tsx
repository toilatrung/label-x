'use client';

import React from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessConfiguration } from '@/lib/auth/roles';

export default function ConfigurationPage() {
  return (
    <AuthGuard
      permissionCheck={canAccessConfiguration}
      requiredPermissionName="Quyền Cấu hình hệ thống (QC Admin / Super Admin / QA Lead)"
    >
      <AppShell activeKey="configuration" flowStep={1}>
        <div style={{ maxWidth: '1100px', margin: '0 auto' }}>
          <div className="lx-card" style={{ padding: 'var(--space-6)' }}>
            <h1 style={{ fontSize: '20px', fontWeight: 600, margin: '0 0 var(--space-2)' }}>
              Workflow & Permissions (Ma trận phân quyền vai trò)
            </h1>
            <p style={{ color: 'var(--ink-muted)', fontSize: '14px', margin: '0 0 var(--space-6)' }}>
              Dựa theo tài liệu thiết kế <code>WorkflowPermissions.dc.html</code>.
            </p>

            <table className="lx-table" style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>Chức năng</th>
                  <th>Annotator (AN)</th>
                  <th>Reviewer (RV)</th>
                  <th>QA Lead (QA)</th>
                  <th>QC Admin (AD)</th>
                  <th>Super Admin (SA)</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Quality Summary</td>
                  <td>Giới hạn</td>
                  <td>Xem</td>
                  <td>Đầy đủ</td>
                  <td>Đầy đủ</td>
                  <td>Đầy đủ</td>
                </tr>
                <tr>
                  <td>Quality Analysis</td>
                  <td>— (Ẩn)</td>
                  <td>— (Ẩn)</td>
                  <td>Chạy / xem</td>
                  <td>Cấu hình</td>
                  <td>Chạy / cấu hình</td>
                </tr>
                <tr>
                  <td>Review Queues & Workspace</td>
                  <td>— (Ẩn)</td>
                  <td>Review</td>
                  <td>Review / giám sát</td>
                  <td>Xem</td>
                  <td>Review / giám sát</td>
                </tr>
                <tr>
                  <td>Rework</td>
                  <td>Thực hiện</td>
                  <td>Yêu cầu / xác minh</td>
                  <td>Yêu cầu / giám sát</td>
                  <td>—</td>
                  <td>Thực hiện / xác minh</td>
                </tr>
                <tr>
                  <td>Adjudication & Escalations</td>
                  <td>— (Ẩn)</td>
                  <td>— (Ẩn)</td>
                  <td>Có</td>
                  <td>—</td>
                  <td>Có (ghi đè)</td>
                </tr>
                <tr>
                  <td>Calibration & Audit</td>
                  <td>Tham gia</td>
                  <td>Tham gia</td>
                  <td>Quản lý</td>
                  <td>Cấu hình</td>
                  <td>Quản lý / cấu hình</td>
                </tr>
                <tr>
                  <td>Phê duyệt phát hành</td>
                  <td>—</td>
                  <td>—</td>
                  <td>Người được cấp quyền</td>
                  <td>—</td>
                  <td>Có (ghi đè)</td>
                </tr>
                <tr>
                  <td>Configuration</td>
                  <td>—</td>
                  <td>—</td>
                  <td>Giới hạn</td>
                  <td>Có</td>
                  <td>Có (toàn quyền)</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </AppShell>
    </AuthGuard>
  );
}
