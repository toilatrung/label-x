"use client";

import React from "react";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { AppShell } from "@/components/layout/AppShell";
import { GuidelineRuleLookup } from "@/components/guidelines/GuidelineRuleLookup";
import { canAccessGuidelines } from "@/lib/auth/roles";

export default function GuidelinesPage() {
  return <AuthGuard permissionCheck={canAccessGuidelines}
    requiredPermissionName="Reviewer / Quality Assurance Lead / Quality Control Admin / Super Admin">
    <AppShell activeKey="configuration">
      <div className="lx-page lx-guideline-page">
        <div className="lx-head"><div className="lx-head__text">
          <h1 className="lx-h1">Models và Guidelines</h1>
          <p className="lx-lead">Tra cứu rule theo ID, nhóm lỗi và lớp. Quality Control chỉ đọc guideline đã nạp; nội dung được soạn ở nơi khác.</p>
        </div></div>
        <GuidelineRuleLookup />
      </div>
    </AppShell>
  </AuthGuard>;
}
