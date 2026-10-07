"use client";

/**
 * Màn tra cứu guideline — /configuration/guidelines (T-003, CR-101).
 *
 * Chỉ đọc: GET /api/guidelines/rules/ (docs/04-api/openapi.yaml, guidelines_rules_list).
 * Lọc theo version, family (nhóm lỗi) và class_name; phân trang bằng cursor next/previous.
 * Hợp đồng không trả tổng số rule (PaginatedGuidelineRuleList chỉ có next/previous/results),
 * nên màn hình chỉ hiển thị số rule của trang hiện tại, không tự suy ra tổng.
 */

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import React, { useState } from "react";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { AppShell } from "@/components/layout/AppShell";
import { apiClient } from "@/lib/api/client";
import type { components, operations } from "@/lib/api/contract";
import { canAccessGuidelines } from "@/lib/auth/roles";

type GuidelineRule = components["schemas"]["GuidelineRule"];
type PaginatedGuidelineRuleList = components["schemas"]["PaginatedGuidelineRuleList"];
type IssueFamily = components["schemas"]["IssueFamily"];
type ApiErrorBody = components["schemas"]["Error"];
type RulesQuery = NonNullable<operations["guidelines_rules_list"]["parameters"]["query"]>;

const FAMILY_OPTIONS: { value: IssueFamily; label: string }[] = [
  { value: "E1", label: "E1 · Thiếu box" },
  { value: "E2", label: "E2 · Sai lớp" },
  { value: "E3", label: "E3 · Trùng box" },
  { value: "structural", label: "Cảnh báo cấu trúc" },
];

interface Filters {
  version: string;
  family: IssueFamily | "";
  className: string;
}

const EMPTY_FILTERS: Filters = { version: "", family: "", className: "" };

class GuidelineRequestError extends Error {
  constructor(public status: number, public code?: ApiErrorBody["code"], message?: string) {
    super(message || `HTTP ${status}`);
  }
}

/** Lấy giá trị cursor từ URL next/previous do API trả về. */
function cursorFrom(link: string | null | undefined): string | null {
  if (!link) return null;
  try {
    return new URL(link, "http://localhost").searchParams.get("cursor");
  } catch {
    return null;
  }
}

async function fetchRules(filters: Filters, cursor: string | null): Promise<PaginatedGuidelineRuleList> {
  const query: RulesQuery = {};
  if (filters.version) query.version = filters.version;
  if (filters.family) query.family = filters.family;
  if (filters.className) query.class_name = filters.className;
  if (cursor) query.cursor = cursor;

  const { data, error, response } = await apiClient.GET("/api/guidelines/rules/", {
    params: { query },
  });
  if (error || !data) {
    const body = error as ApiErrorBody | undefined;
    throw new GuidelineRequestError(response.status, body?.code, body?.message);
  }
  return data;
}

function errorText(error: GuidelineRequestError): { title: string; body: string } {
  if (error.status === 404 || error.code === "NOT_FOUND") {
    return { title: "Không tìm thấy guideline", body: error.message };
  }
  if (error.code === "FORBIDDEN" || error.status === 403) {
    return {
      title: "Không có quyền truy cập",
      body: "Tài khoản hiện tại không có quyền xem guideline trong phạm vi này.",
    };
  }
  if (error.code === "VALIDATION_ERROR" || error.status === 400) {
    return { title: "Bộ lọc không hợp lệ", body: error.message };
  }
  return { title: "Không tải được dữ liệu", body: "Đã xảy ra lỗi khi tải danh sách rule từ máy chủ." };
}

function GuidelineRules() {
  const [draft, setDraft] = useState<Filters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  // Cursor của từng trang đã mở; phần tử đầu (null) là trang đầu tiên.
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const pageIndex = cursors.length - 1;
  const cursor = cursors[pageIndex];

  const rulesQuery = useQuery({
    queryKey: ["guideline-rules", filters, cursor],
    queryFn: () => fetchRules(filters, cursor),
    placeholderData: keepPreviousData,
    retry: false,
  });

  const applyFilters = (next: Filters) => {
    setFilters(next);
    setCursors([null]);
  };

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    applyFilters({ ...draft, version: draft.version.trim(), className: draft.className.trim() });
  };

  const onReset = () => {
    setDraft(EMPTY_FILTERS);
    applyFilters(EMPTY_FILTERS);
  };

  const rules: GuidelineRule[] = rulesQuery.data?.results ?? [];
  const versions = [...new Set(rules.map((rule) => rule.guideline_version))];
  const nextCursor = cursorFrom(rulesQuery.data?.next);
  const error = rulesQuery.error instanceof GuidelineRequestError ? rulesQuery.error : null;
  const failure = rulesQuery.isError
    ? errorText(error ?? new GuidelineRequestError(0))
    : null;
  const hasFilter = Boolean(filters.version || filters.family || filters.className);

  return (
    <div className="lx-page lx-guideline-page">
      <div className="lx-head">
        <div className="lx-head__text">
          <h1 className="lx-h1">Models và Guidelines</h1>
          <p className="lx-lead">
            Tra cứu rule guideline áp dụng cho annotation theo nhóm lỗi và lớp. Quality Control chỉ đọc
            guideline đã nạp; nội dung soạn ở nơi khác.
          </p>
        </div>
      </div>

      {failure && (
        <div className="lx-callout" role="alert">
          <div className="lx-callout__text">
            <strong>{failure.title}</strong>
            <div>{failure.body}</div>
          </div>
        </div>
      )}

      <section className="lx-card" aria-label="Danh sách rule guideline">
        <header className="lx-card__head">
          <span className="lx-cell__main">Rule guideline</span>
          <span className="lx-subtle">
            Guideline version:{" "}
            <span className="lx-mono" data-testid="guideline-version">
              {versions.length ? versions.join(", ") : "—"}
            </span>
          </span>
        </header>

        <form className="lx-toolbar lx-guideline-filters" onSubmit={onSubmit} role="search">
          <div className="lx-field">
            <label className="lx-label" htmlFor="guideline-family">Nhóm lỗi</label>
            <select
              id="guideline-family"
              className="lx-select lx-select--inline"
              value={draft.family}
              onChange={(event) => setDraft({ ...draft, family: event.target.value as Filters["family"] })}
            >
              <option value="">Tất cả nhóm lỗi</option>
              {FAMILY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
          <div className="lx-field">
            <label className="lx-label" htmlFor="guideline-class">Tên lớp</label>
            <input
              id="guideline-class"
              className="lx-input"
              value={draft.className}
              onChange={(event) => setDraft({ ...draft, className: event.target.value })}
              placeholder="Ví dụ: car"
            />
          </div>
          <div className="lx-field">
            <label className="lx-label" htmlFor="guideline-version">Guideline version</label>
            <input
              id="guideline-version"
              className="lx-input"
              value={draft.version}
              onChange={(event) => setDraft({ ...draft, version: event.target.value })}
              placeholder="Bỏ trống là bản mới nhất"
            />
          </div>
          <div className="lx-guideline-filters__actions">
            <button type="submit" className="lx-btn lx-btn--primary">Lọc</button>
            {hasFilter && (
              <button type="button" className="lx-btn" onClick={onReset}>Xoá bộ lọc</button>
            )}
          </div>
        </form>

        <div className="lx-scroll">
          <table className="lx-table lx-guideline-table-rules">
            <thead>
              <tr>
                <th className="lx-guideline-col-id">Rule ID</th>
                <th className="lx-guideline-col-section">Mục</th>
                <th>Nội dung</th>
              </tr>
            </thead>
            <tbody>
              {rulesQuery.isLoading ? (
                <tr><td colSpan={3} className="c lx-subtle lx-guideline-empty">Đang tải…</td></tr>
              ) : failure ? (
                <tr><td colSpan={3} className="c lx-subtle lx-guideline-empty">{failure.title}.</td></tr>
              ) : rules.length === 0 ? (
                <tr>
                  <td colSpan={3} className="c lx-subtle lx-guideline-empty">
                    {hasFilter ? "Không có rule nào khớp bộ lọc." : "Chưa có guideline nào được nạp."}
                  </td>
                </tr>
              ) : (
                rules.map((rule) => (
                  <tr key={`${rule.guideline_version}:${rule.rule_id}`}>
                    <td><span className="lx-mono">{rule.rule_id}</span></td>
                    <td className="lx-muted">{rule.section || "—"}</td>
                    <td className="lx-guideline-rule-content">{rule.content}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <footer className="lx-card__foot">
          <span>
            Trang {(pageIndex + 1).toLocaleString("en-US")} · {rules.length.toLocaleString("en-US")} rule trên trang
            này. Guideline chỉ đọc, nạp bằng lệnh <code>manage.py load_guideline</code>.
          </span>
          <nav className="lx-pager" aria-label="Phân trang rule">
            <button
              type="button"
              className="lx-btn lx-btn--sm"
              disabled={pageIndex === 0 || rulesQuery.isFetching}
              onClick={() => setCursors(cursors.slice(0, -1))}
            >
              Trang trước
            </button>
            <button
              type="button"
              className="lx-btn lx-btn--sm"
              disabled={!nextCursor || rulesQuery.isFetching || rulesQuery.isError}
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

export default function GuidelinesPage() {
  return (
    <AuthGuard
      permissionCheck={canAccessGuidelines}
      requiredPermissionName="Reviewer / Quality Assurance Lead / Quality Control Admin / Super Admin"
    >
      <AppShell activeKey="configuration">
        <GuidelineRules />
      </AppShell>
    </AuthGuard>
  );
}
