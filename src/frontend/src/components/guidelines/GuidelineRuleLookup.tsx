"use client";

import { useQuery } from "@tanstack/react-query";
import React, { useId, useState } from "react";
import { apiClient, ApiRequestError } from "@/lib/api/client";
import { errorMessage } from "@/lib/api/errors";
import type { components, operations } from "@/lib/api/contract";
import { canAccessGuidelines } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/auth-context";

type GuidelineRule = components["schemas"]["GuidelineRule"];
type PaginatedGuidelineRuleList = components["schemas"]["PaginatedGuidelineRuleList"];
type IssueFamily = components["schemas"]["IssueFamily"];
type RulesQuery = NonNullable<operations["guidelines_rules_list"]["parameters"]["query"]>;

const FAMILY_OPTIONS: { value: IssueFamily; label: string }[] = [
  { value: "E1", label: "E1 · Thiếu box" },
  { value: "E2", label: "E2 · Sai lớp" },
  { value: "E3", label: "E3 · Trùng box" },
  { value: "structural", label: "Cảnh báo cấu trúc" },
];

export interface GuidelineRuleFilters {
  ruleId: string;
  version: string;
  family: IssueFamily | "";
  className: string;
}

const EMPTY_FILTERS: GuidelineRuleFilters = { ruleId: "", version: "", family: "", className: "" };

/** Lấy giá trị cursor từ URL next/previous do API trả về. */
function cursorFrom(link: string | null | undefined): string | null {
  if (!link) return null;
  try {
    return new URL(link, "http://localhost").searchParams.get("cursor");
  } catch {
    return null;
  }
}

async function fetchRules(filters: GuidelineRuleFilters, cursor: string | null, signal: AbortSignal): Promise<PaginatedGuidelineRuleList> {
  if (filters.ruleId) {
    const { data, error, response } = await apiClient.GET("/api/guidelines/rules/{rule_id}/", {
      params: { path: { rule_id: filters.ruleId }, query: filters.version ? { version: filters.version } : {} }, signal,
    });
    if (error || !data) throw new ApiRequestError(response.status, error, response.headers);
    return { results: [data], next: null, previous: null };
  }
  const query: RulesQuery = {};
  if (filters.version) query.version = filters.version;
  if (filters.family) query.family = filters.family;
  if (filters.className) query.class_name = filters.className;
  if (cursor) query.cursor = cursor;

  const { data, error, response } = await apiClient.GET("/api/guidelines/rules/", {
    params: { query }, signal,
  });
  if (error || !data) {
    throw new ApiRequestError(response.status, error, response.headers);
  }
  return data;
}

export interface GuidelineRuleLookupProps {
  initialFilters?: Partial<GuidelineRuleFilters>;
  compact?: boolean;
}

/** Read-only rule lookup for ModelsGuidelines and Workspace evidence panels. */
export function GuidelineRuleLookup({ initialFilters, compact = false }: GuidelineRuleLookupProps) {
  const initial: GuidelineRuleFilters = {
    ruleId: initialFilters?.ruleId?.trim() ?? "",
    version: initialFilters?.version?.trim() ?? "",
    family: initialFilters?.family ?? "",
    className: initialFilters?.className?.trim() ?? "",
  };
  return <RuleLookupPanel key={JSON.stringify(initial)} initial={initial} compact={compact} />;
}

function RuleLookupPanel({ initial, compact }: { initial: GuidelineRuleFilters; compact: boolean }) {
  const { session, hasPermission } = useAuth();
  const allowed = hasPermission(canAccessGuidelines);
  const id = useId();
  const [draft, setDraft] = useState<GuidelineRuleFilters>(initial);
  const [filters, setFilters] = useState<GuidelineRuleFilters>(initial);
  // Cursor của từng trang đã mở; phần tử đầu (null) là trang đầu tiên.
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const pageIndex = cursors.length - 1;
  const cursor = cursors[pageIndex];

  const rulesQuery = useQuery({
    queryKey: ["guideline-rules", session?.user.id, filters, cursor],
    queryFn: ({ signal }) => fetchRules(filters, cursor, signal),
    enabled: allowed,
    retry: false,
  });

  const applyFilters = (next: GuidelineRuleFilters) => {
    setFilters(next);
    setCursors([null]);
  };

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    applyFilters({ ...draft, ruleId: draft.ruleId.trim(), version: draft.version.trim(), family: draft.ruleId.trim() ? "" : draft.family, className: draft.ruleId.trim() ? "" : draft.className.trim() });
  };

  const onReset = () => {
    setDraft(EMPTY_FILTERS);
    applyFilters(EMPTY_FILTERS);
  };

  const rules: GuidelineRule[] = rulesQuery.data?.results ?? [];
  const versions = [...new Set(rules.map((rule) => rule.guideline_version))];
  const nextCursor = cursorFrom(rulesQuery.data?.next);
  const failure = rulesQuery.isError
    ? { title: "Không tải được guideline", body: errorMessage(rulesQuery.error) }
    : null;
  const hasFilter = Boolean(filters.ruleId || filters.version || filters.family || filters.className);

  if (!allowed) return <div className="lx-callout" role="alert">Bạn không có quyền tra cứu guideline.</div>;

  return (
    <div className={`lx-rule-lookup${compact ? " lx-rule-lookup--compact" : ""}`}>
      {failure && (
        <div className="lx-callout" role="alert">
          <div className="lx-callout__text">
            <strong>{failure.title}</strong>
            <div>{failure.body}</div>
          </div>
        </div>
      )}

      <section className="lx-card" aria-busy={rulesQuery.isFetching} aria-label="Danh sách rule guideline">
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
            <label className="lx-label" htmlFor={`${id}-rule`}>Rule ID</label>
            <input id={`${id}-rule`} className="lx-input lx-mono" value={draft.ruleId}
              onChange={event => setDraft({ ...draft, ruleId: event.target.value })} placeholder="Ví dụ: VEH-03" />
          </div>
          <div className="lx-field">
            <label className="lx-label" htmlFor={`${id}-family`}>Nhóm lỗi</label>
            <select
              id={`${id}-family`}
              disabled={Boolean(draft.ruleId.trim())}
              className="lx-select lx-select--inline"
              value={draft.family}
              onChange={(event) => setDraft({ ...draft, family: event.target.value as GuidelineRuleFilters["family"] })}
            >
              <option value="">Tất cả nhóm lỗi</option>
              {FAMILY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
          <div className="lx-field">
            <label className="lx-label" htmlFor={`${id}-class`}>Tên lớp</label>
            <input
              id={`${id}-class`}
              disabled={Boolean(draft.ruleId.trim())}
              className="lx-input"
              value={draft.className}
              onChange={(event) => setDraft({ ...draft, className: event.target.value })}
              placeholder="Ví dụ: car"
            />
          </div>
          <div className="lx-field">
            <label className="lx-label" htmlFor={`${id}-version`}>Guideline version</label>
            <input
              id={`${id}-version`}
              className="lx-input"
              value={draft.version}
              onChange={(event) => setDraft({ ...draft, version: event.target.value })}
              placeholder="Bản mới nhất"
            />
          </div>
          <div className="lx-guideline-filters__actions">
            <button type="submit" className="lx-btn lx-btn--primary">Lọc</button>
            {hasFilter && (
              <button type="button" className="lx-btn" onClick={onReset}>Xoá bộ lọc</button>
            )}
          </div>
        </form>
        {draft.ruleId.trim() && <p className="lx-hint lx-rule-lookup__note">Tra chính xác Rule ID và version; nhóm lỗi và lớp không áp dụng trong chế độ này.</p>}

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
              {rulesQuery.isPending ? (
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
                    <td><span className="lx-mono">{rule.rule_id}</span><div className="lx-cell__sub">{rule.guideline_version}</div></td>
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
            này. Guideline chỉ đọc.
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
