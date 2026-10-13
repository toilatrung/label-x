'use client';

import React, { useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessReview } from '@/lib/auth/roles';
import { ReviewQueues } from '@/components/review/ReviewQueues';
import { useAuth } from '@/lib/auth/auth-context';

export default function ReviewPage() {
  const { session } = useAuth();
  const [workspaceState, setWorkspaceState] = useState<{
    isOpen: boolean;
    frameId?: number;
    runId?: number | null;
    leaseId?: number;
    taskCvatId?: number;
  }>({ isOpen: false });

  const pageHeader = workspaceState.isOpen ? (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Review Workspace</h1>
        <p className="lx-lead">
          Đối chiếu annotation với bằng chứng và hướng dẫn, sau đó ra quyết định. Trợ lý chỉ cung cấp bằng chứng; quyết định cuối cùng luôn thuộc về người review.
        </p>
      </div>
      <div className="lx-actions">
        <span className="lx-hint">
          {workspaceState.frameId ? `Frame #${workspaceState.frameId}` : ''}
          {workspaceState.taskCvatId ? ` · Task #${workspaceState.taskCvatId}` : ''}
          {workspaceState.runId != null ? ` · Run #${workspaceState.runId}` : ''}
          {` · ${session?.user?.display_name || session?.user?.username || 'Reviewer'}`}
        </span>
      </div>
    </div>
  ) : (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Trung tâm kiểm tra</h1>
        <p className="lx-lead">
          Ưu tiên ảnh cần kiểm tra. Chọn một ảnh để mở màn kiểm tra riêng.
        </p>
      </div>
    </div>
  );

  return (
    <AuthGuard
      permissionCheck={canAccessReview}
      requiresIdentity
      requiredPermissionName="Reviewer / QA Lead / Super Admin, có liên kết CVAT"
    >
      <AppShell
        activeKey="review"
        flowStep={workspaceState.isOpen ? 2 : 1}
        pageHeader={pageHeader}
      >
        <ReviewQueues onWorkspaceStateChange={setWorkspaceState} />
      </AppShell>
    </AuthGuard>
  );
}
