'use client';

import React, { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessReview } from '@/lib/auth/roles';
import { useAuth } from '@/lib/auth/auth-context';
import { ReviewWorkspace } from '@/components/review/ReviewWorkspace';
import { ReviewWorkspaceEmpty } from '@/components/review/ReviewWorkspaceEmpty';

function ReviewWorkspaceContent() {
  const searchParams = useSearchParams();
  const { session } = useAuth();

  const frameIdParam = searchParams.get('frame_id');
  const frameId =
    frameIdParam &&
    /^\d+$/.test(frameIdParam.trim()) &&
    Number.isSafeInteger(Number(frameIdParam)) &&
    Number(frameIdParam) > 0
      ? Number(frameIdParam)
      : null;

  // In accordance with T-037 requirement:
  // URL parameters do NOT grant writable lease authority.
  // No lease object, holder_user_id or expires_at may be fabricated.
  // Direct URL navigation without a verified LeaseGrant handoff from T-034 ReviewQueues
  // opens the workspace in read-only inspection mode (initialLease = null).
  const initialLease = null;

  const pageHeaderNode = (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Review Workspace</h1>
        <p className="lx-lead">
          Đối chiếu annotation với bằng chứng và hướng dẫn, sau đó ra quyết định. Trợ lý chỉ cung cấp bằng chứng; quyết định cuối cùng luôn thuộc về người review.
        </p>
      </div>
      <div className="lx-actions">
        <span className="lx-hint">
          {frameId ? `Frame #${frameId} · ` : ''}{session?.user?.display_name || 'Reviewer'}
        </span>
        <Link href="/review" className="lx-btn">
          Về hàng đợi
        </Link>
      </div>
    </div>
  );

  return (
    <AppShell activeKey="review" flowStep={2} pageHeader={pageHeaderNode}>
      {frameId ? (
        <ReviewWorkspace
          frameId={frameId}
          initialLease={initialLease}
        />
      ) : (
        <ReviewWorkspaceEmpty />
      )}
    </AppShell>
  );
}

export default function ReviewWorkspacePage() {
  return (
    <AuthGuard
      permissionCheck={canAccessReview}
      requiresIdentity
      requiredPermissionName="Reviewer / QA Lead / Super Admin, có liên kết CVAT"
    >
      <Suspense
        fallback={
          <div className="lx-card lx-card__body lx-ws__empty">
            Đang tải Review Workspace...
          </div>
        }
      >
        <ReviewWorkspaceContent />
      </Suspense>
    </AuthGuard>
  );
}
