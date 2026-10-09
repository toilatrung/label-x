"use client";

import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { AppShell } from "@/components/layout/AppShell";
import { apiClient, ApiRequestError } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/contract";
import { canAccessGuidelines } from "@/lib/auth/roles";

type PaginatedMappingList = components["schemas"]["PaginatedRuleMappingList"];

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

function RulesThresholds() {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const pageIndex = cursors.length - 1;
  const cursor = cursors[pageIndex];

  const query = useQuery({
    queryKey: ["guideline-mappings", cursor],
    queryFn: () => fetchMappings(cursor),
    retry: false,
  });
  const failure = query.isError ? errorMessage(query.error) : null;
  const mappings = query.data?.results ?? [];
  const nextCursor = cursorFrom(query.data?.next);

  return (
    <div className="lx-page">
      <div className="lx-head">
        <div className="lx-head__text">
          <h1 className="lx-h1">Rules và Thresholds</h1>
          <p className="lx-lead">
            Mapping nhóm lỗi/lớp tới rule ID. Màn hình chỉ xem; nội dung được quản trị qua tệp guideline.
          </p>
        </div>
      </div>
      {failure && (
        <div className="lx-callout" role="alert">
          <strong>Không tải được mapping</strong>
          <div>{failure}</div>
        </div>
      )}
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
              {query.isLoading ? (
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
              disabled={pageIndex === 0 || query.isFetching}
              onClick={() => setCursors(cursors.slice(0, -1))}
            >
              Trang trước
            </button>
            <button
              type="button"
              className="lx-btn lx-btn--subtle"
              disabled={!nextCursor || query.isFetching || query.isError}
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
