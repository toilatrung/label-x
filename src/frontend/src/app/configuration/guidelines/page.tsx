"use client";

import React from "react";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { AppShell } from "@/components/layout/AppShell";
import { ModelsGuidelinesCard } from "@/components/configuration/ModelsGuidelinesCard";
import { GuidelineRuleLookup } from "@/components/guidelines/GuidelineRuleLookup";
import { canAccessGuidelines } from "@/lib/auth/roles";

export default function GuidelinesPage() {
  return <AuthGuard permissionCheck={canAccessGuidelines}
    requiredPermissionName="Reviewer / Quality Assurance Lead / Quality Control Admin / Super Admin">
    <AppShell activeKey="configuration">
      <div className="lx-page lx-guideline-page">
        <div className="lx-head"><div className="lx-head__text">
          <h1 className="lx-h1">Models và Guidelines</h1>
          <p className="lx-lead">Cấu hình các mô hình dùng để kiểm tra độc lập và ánh xạ phiên bản guideline với taxonomy. Quality Control chỉ quản lý phiên bản, nội dung guideline được soạn ở nơi khác.</p>
        </div></div>
        <ModelsGuidelinesCard />
        <GuidelineRuleLookup />
      </div>
    </AppShell>
  </AuthGuard>;
}
