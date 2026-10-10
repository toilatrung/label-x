'use client';

import Link from 'next/link';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessAnalysis } from '@/lib/auth/roles';

export default function AnalysisPage() {
  return <AuthGuard permissionCheck={canAccessAnalysis} requiredPermissionName="Quyền Phân tích Chất lượng">
    <AppShell activeKey="analysis" flowStep={1} pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Phân tích chất lượng</h1><p className="lx-lead">Chọn cấu hình để chạy QC và theo dõi kết quả thực thi.</p></div></div>}>
      <div className="lx-card lx-card__body lx-execution-actions">
        <Link href="/analysis/config" className="lx-btn lx-btn--primary">Cấu hình và tạo QC run</Link>
        <Link href="/analysis/history" className="lx-btn">Lịch sử thực thi</Link>
      </div>
    </AppShell>
  </AuthGuard>;
}
