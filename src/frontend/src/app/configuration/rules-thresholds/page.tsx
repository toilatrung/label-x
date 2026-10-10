"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { AppShell } from "@/components/layout/AppShell";
import { EngineThresholdsTable } from "@/components/execution/EngineThresholdsTable";
import { apiClient, ApiRequestError } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import { useAuth } from "@/lib/auth/auth-context";
import { canAccessConfiguration, canAccessGuidelines } from "@/lib/auth/roles";
import type { components } from "@/lib/api/contract";

type PaginatedMappingList = components["schemas"]["PaginatedRuleMappingList"];
type ConfigVersion = components["schemas"]["ConfigVersion"];

function cursorFrom(link: string | null | undefined): string | null {
  if (!link) return null;
  try {
    return new URL(link, "http://localhost").searchParams.get("cursor");
  } catch {
    return null;
  }
}

async function fetchMappings(cursor: string | null): Promise<PaginatedMappingList> {
  const query: Record<string, string> = {};
  if (cursor) query.cursor = cursor;
  const { data, error, response } = await apiClient.GET("/api/guidelines/mappings/", {
    params: { query },
  });
  if (error || !data) throw new ApiRequestError(response.status, error, response.headers);
  return data;
}

async function fetchPublishedConfig(): Promise<ConfigVersion | null> {
  const { data, error, response } = await apiClient.GET("/api/config-versions/", {
    params: { query: { status: "published" } },
  });
  if (error || !data) throw new ApiRequestError(response.status, error, response.headers);
  const configs = data.results ?? [];
  return configs.length > 0 ? configs[0] : null;
}

function RulesThresholds() {
  const { hasPermission } = useAuth();
  const canViewConfig = hasPermission(canAccessConfiguration);

  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const pageIndex = cursors.length - 1;
  const cursor = cursors[pageIndex];

  const mappingQuery = useQuery({
    queryKey: ["guideline-mappings", cursor],
    queryFn: () => fetchMappings(cursor),
    retry: false,
  });

  const configQuery = useQuery({
    queryKey: ["published-config-version"],
    queryFn: fetchPublishedConfig,
    enabled: canViewConfig,
    retry: false,
  });

  const mappingFailure = mappingQuery.isError ? errorMessage(mappingQuery.error) : null;
  const configFailure = configQuery.isError ? errorMessage(configQuery.error) : null;

  const mappings = mappingQuery.data?.results ?? [];
  const nextCursor = cursorFrom(mappingQuery.data?.next);

  return (
    <div className="lx-page">
      <div className="lx-head">
        <div className="lx-head__text">
          <h1 className="lx-h1">Rules và Thresholds</h1>
          <p className="lx-lead">
            Quy tắc kiểm tra tự động, ngưỡng engine hiệu lực và mapping nhóm lỗi/lớp tới rule ID. Màn hình chỉ xem.
          </p>
        </div>
      </div>

      {mappingFailure && (
        <div className="lx-callout" role="alert">
          <strong>Không tải được mapping</strong>
          <div>{mappingFailure}</div>
        </div>
      )}

      {/* 1. Ngưỡng engine chỉ đọc từ API thật (T-029) */}
      <EngineThresholdsTable
        config={configQuery.data ?? null}
        isLoading={configQuery.isLoading}
        error={configFailure}
        hasPermission={canViewConfig}
      />

      {/* 2. Mapping guideline tĩnh nạp theo CR-107 */}
      <section className="lx-card" aria-label="Mapping rule guideline">
        <header className="lx-card__head">
          <span className="lx-cell__main">Mapping guideline</span>
          <span className="lx-subtle">Chỉ đọc</span>
        </header>
        <div className="lx-scroll">
          <table className="lx-table">
            <thead>
              <tr>
                <th>Nhóm lỗi</th>
                <th>Lớp</th>
                <th>Lớp cặp</th>
                <th>Rule ID</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {mappingQuery.isLoading ? (
                <tr>
                  <td colSpan={5} className="c lx-subtle">
                    Đang tải…
                  </td>
                </tr>
              ) : mappings.length === 0 ? (
                <tr>
                  <td colSpan={5} className="c lx-subtle">
                    Chưa có mapping guideline.
                  </td>
                </tr>
              ) : (
                mappings.map((mapping, index) => (
                  <tr
                    key={`${mapping.guideline_version}-${mapping.error_group}-${mapping.class_name}-${mapping.paired_class}-${mapping.rule_id}-${index}`}
                  >
                    <td>{mapping.error_group || "Tất cả"}</td>
                    <td>{mapping.class_name || "Tất cả"}</td>
                    <td>{mapping.paired_class || "Tất cả"}</td>
                    <td>
                      <span className="lx-mono">{mapping.rule_id}</span>
                    </td>
                    <td>
                      <span className="lx-mono">{mapping.guideline_version}</span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <footer className="lx-card__foot">
          <span>
            Trang {(pageIndex + 1).toLocaleString("en-US")} · {mappings.length.toLocaleString("en-US")} mapping trên trang hiện tại.
          </span>
          <nav className="lx-pager" aria-label="Phân trang mapping">
            <button
              type="button"
              className="lx-btn lx-btn--subtle"
              disabled={pageIndex === 0 || mappingQuery.isFetching}
              onClick={() => setCursors(cursors.slice(0, -1))}
            >
              Trang trước
            </button>
            <button
              type="button"
              className="lx-btn lx-btn--subtle"
              disabled={!nextCursor || mappingQuery.isFetching || mappingQuery.isError}
              onClick={() => nextCursor && setCursors([...cursors, nextCursor])}
            >
              Trang sau
            </button>
          </nav>
        </footer>
      </section>
    </div>
  );
}

export default function RulesThresholdsPage() {
  return (
    <AuthGuard
      permissionCheck={canAccessGuidelines}
      requiredPermissionName="Reviewer / Quality Assurance Lead / Quality Control Admin / Super Admin"
    >
      <AppShell activeKey="configuration">
        <RulesThresholds />
      </AppShell>
    </AuthGuard>
  );
}
