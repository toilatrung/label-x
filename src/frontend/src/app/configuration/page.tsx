'use client';

import React from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { apiClient, ApiRequestError } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import type { components } from '@/lib/api/contract';
import { canAccessConfiguration, ROLE_LABELS } from '@/lib/auth/roles';
import type { UserRole } from '@/types/auth';

type WorkflowPermissions = components['schemas']['WorkflowPermissions'];

const ROLE_ORDER: UserRole[] = ['annotator', 'reviewer', 'qa_lead', 'qc_admin', 'super_admin', 'product_owner', 'data_model_owner'];

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
        <h1 className="lx-h1">Quy trình và phân quyền</h1>
        <p className="lx-lead">Ma trận quyền theo vai trò và các quy tắc quy trình do máy chủ áp dụng. Màn hình chỉ xem.</p>
      </div></div>
      {query.isError && <div className="lx-callout" role="alert">
        <strong>Không tải được ma trận phân quyền</strong><div>{errorMessage(query.error)}</div>
      </div>}
      <section className="lx-card" aria-label="Ma trận phân quyền">
        <header className="lx-card__head"><span className="lx-cell__main">Ma trận vai trò</span><span className="lx-subtle">Chỉ đọc</span></header>
        <div className="lx-scroll">
          <table className="lx-table">
            <thead><tr><th>Chức năng</th>{ROLE_ORDER.map(role => <th key={role}>{ROLE_LABELS[role]}</th>)}</tr></thead>
            <tbody>
              {query.isLoading && <tr><td colSpan={ROLE_ORDER.length + 1}>Đang tải…</td></tr>}
              {data?.matrix.map(row => <tr key={row.function}>
                <td>{row.function}</td>
                {ROLE_ORDER.map(role => <td key={role}>{row.roles[role]}</td>)}
              </tr>)}
            </tbody>
          </table>
        </div>
      </section>
      <section className="lx-card" aria-label="Quy tắc quy trình">
        <header className="lx-card__head"><span className="lx-cell__main">Quy tắc quy trình</span></header>
        <div className="lx-scroll">
          <table className="lx-table">
            <thead><tr><th>Quy tắc</th><th>Mô tả</th><th>Trạng thái áp dụng</th></tr></thead>
            <tbody>
              {data?.rules.map(rule => <tr key={rule.rule}>
                <td>{rule.name}</td>
                <td>{rule.description}</td>
                <td>{rule.enforced ? 'Đã áp dụng' : 'Chờ triển khai'}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
      </section>
      <section className="lx-card" aria-label="Vai trò của tài khoản">
        <header className="lx-card__head"><span className="lx-cell__main">Vai trò của bạn</span></header>
        <div className="lx-scroll">
          <table className="lx-table">
            <thead><tr><th>Vai trò</th><th>Phạm vi</th></tr></thead>
            <tbody>{data?.user_roles.map((assignment, index) => <tr key={index}>
              <td>{ROLE_LABELS[assignment.role as UserRole]}</td>
              <td>{assignment.dataset_id === null || assignment.dataset_id === undefined ? 'Toàn hệ thống' : 'Dataset #' + assignment.dataset_id}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </section>
      <Link className="lx-btn" href="/configuration/guidelines">Tra cứu Models & Guidelines</Link>
    </div>
  );
}

export default function ConfigurationPage() {
  return <AuthGuard permissionCheck={canAccessConfiguration} requiredPermissionName="QA Lead / QC Admin / Super Admin">
    <AppShell activeKey="configuration"><WorkflowPermissionsView /></AppShell>
  </AuthGuard>;
}
