"use client";

/**
 * Màn xem guideline — /configuration/guidelines
 *
 * Chức năng: Liệt kê guideline version đã nạp, chọn version để xem rules.
 * Chỉ đọc, không có thao tác tạo/sửa/xóa (scope T-003, CR-101 pilot).
 *
 * Design System: lx-* classes, bảng là chính (labelx-design SKILL.md).
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

type GuidelineRule = components["schemas"]["GuidelineRule"];
type GuidelineRuleListResponse = components["schemas"]["GuidelineRuleListResponse"];
type GuidelineVersion = components["schemas"]["GuidelineVersion"];
type GuidelineVersionListResponse = components["schemas"]["GuidelineVersionListResponse"];

async function fetchVersions(): Promise<GuidelineVersionListResponse> {
  const { data, error, response } = await apiClient.GET("/api/guidelines/");
  if (error || !data) {
    throw new Error(error?.message ?? `HTTP ${response.status}`);
  }
  return data;
}

async function fetchRules(versionTag: string): Promise<GuidelineRuleListResponse> {
  const { data, error, response } = await apiClient.GET("/api/guidelines/rules/", {
    params: { query: { version: versionTag } },
  });
  if (error || !data) {
    throw new Error(error?.message ?? `HTTP ${response.status}`);
  }
  return data;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("vi-VN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EmptyState({ message }: { message: string }) {
  return (
    <tr>
      <td
        colSpan={99}
        style={{
          padding: "var(--space-6)",
          textAlign: "center",
          color: "var(--ink-subtle)",
          fontSize: "13px",
        }}
      >
        {message}
      </td>
    </tr>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span className={`lx-badge ${active ? "lx-badge--success" : ""}`}>
      {active ? "Đang dùng" : "Đã thay thế"}
    </span>
  );
}

function VersionTable({
  versions,
  selectedTag,
  onSelect,
}: {
  versions: GuidelineVersion[];
  selectedTag: string | null;
  onSelect: (tag: string) => void;
}) {
  return (
    <div className="lx-scroll">
      <table className="lx-table" style={{ minWidth: 680 }}>
        <thead>
          <tr>
            <th>Phiên bản</th>
            <th>Tên guideline</th>
            <th>Nạp lúc</th>
            <th>Trạng thái</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {versions.length === 0 ? (
            <EmptyState message="Chưa có guideline nào được nạp." />
          ) : (
            versions.map((v, idx) => (
              <tr
                key={v.version_tag}
                style={selectedTag === v.version_tag ? { background: "var(--selected)" } : {}}
              >
                <td>
                  <span className="lx-mono">{v.version_tag}</span>
                </td>
                <td className="lx-cell__main">{v.name}</td>
                <td className="lx-muted">{formatDate(v.loaded_at)}</td>
                <td>
                  <StatusBadge active={idx === 0} />
                </td>
                <td className="r">
                  <button
                    className="lx-btn lx-btn--sm"
                    onClick={() => onSelect(v.version_tag)}
                    aria-label={`Xem rules của ${v.version_tag}`}
                  >
                    Xem rules
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function RuleTable({ rules }: { rules: GuidelineRule[] }) {
  return (
    <div className="lx-scroll" style={{ marginTop: "var(--space-4)" }}>
      <table className="lx-table" style={{ minWidth: 760 }}>
        <thead>
          <tr>
            <th style={{ width: 100 }}>Rule ID</th>
            <th style={{ width: 80 }}>Mục</th>
            <th>Nội dung</th>
          </tr>
        </thead>
        <tbody>
          {rules.length === 0 ? (
            <EmptyState message="Phiên bản này không có rule nào." />
          ) : (
            rules.map((r) => (
              <tr key={r.rule_id}>
                <td>
                  <span className="lx-mono">{r.rule_id}</span>
                </td>
                <td className="lx-muted">{r.section}</td>
                <td style={{ whiteSpace: "pre-wrap", lineHeight: 1.5, fontSize: 13 }}>
                  {r.content}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function GuidelinesPage() {
  const [selectedTag, setSelectedTag] = useState<string | null>(null);

  const versionsQuery = useQuery({
    queryKey: ["guideline-versions"],
    queryFn: fetchVersions,
  });

  const rulesQuery = useQuery({
    queryKey: ["guideline-rules", selectedTag],
    queryFn: () => fetchRules(selectedTag!),
    enabled: selectedTag !== null,
  });

  const versions: GuidelineVersion[] = versionsQuery.data?.results ?? [];
  const rules: GuidelineRule[] = rulesQuery.data?.results ?? [];

  // Tự chọn version đầu tiên khi dữ liệu load xong
  if (versions.length > 0 && selectedTag === null) {
    setSelectedTag(versions[0].version_tag);
  }

  return (
    <div className="lx" style={{ minHeight: "100vh", background: "var(--canvas)" }}>
      <main className="lx-page">
        {/* Page header */}
        <div className="lx-head">
          <div className="lx-head__text">
            <h1 className="lx-h1">Models và Guidelines</h1>
            <p className="lx-lead">
              Tra cứu phiên bản guideline và rule áp dụng cho annotation. Quality Control chỉ đọc
              guideline đã nạp; nội dung soạn ở nơi khác.
            </p>
          </div>
        </div>

        {/* Guideline versions */}
        <section className="lx-card" style={{ marginBottom: "var(--space-4)" }}>
          <div
            style={{
              padding: "var(--space-3) var(--space-4)",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span style={{ fontWeight: 600, fontSize: 14 }}>Phiên bản guideline</span>
            {versionsQuery.isLoading && (
              <span className="lx-subtle" style={{ fontSize: 13 }}>
                Đang tải…
              </span>
            )}
            {versionsQuery.isError && (
              <span style={{ color: "var(--danger)", fontSize: 13 }}>Không tải được dữ liệu.</span>
            )}
          </div>

          <VersionTable versions={versions} selectedTag={selectedTag} onSelect={setSelectedTag} />
        </section>

        {/* Rules của version được chọn */}
        {selectedTag !== null && (
          <section className="lx-card">
            <div
              style={{
                padding: "var(--space-3) var(--space-4)",
                borderBottom: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                gap: "var(--space-2)",
              }}
            >
              <span style={{ fontWeight: 600, fontSize: 14 }}>Rules —</span>
              <span className="lx-mono" style={{ fontSize: 13 }}>
                {selectedTag}
              </span>
              {rulesQuery.isLoading && (
                <span className="lx-subtle" style={{ fontSize: 13, marginLeft: "auto" }}>
                  Đang tải…
                </span>
              )}
              {rulesQuery.isError && (
                <span
                  style={{ color: "var(--danger)", fontSize: 13, marginLeft: "auto" }}
                >
                  Không tải được rules.
                </span>
              )}
              {!rulesQuery.isLoading && !rulesQuery.isError && (
                <span className="lx-subtle" style={{ fontSize: 13, marginLeft: "auto" }}>
                  {rules.length} rule
                </span>
              )}
            </div>

            <RuleTable rules={rules} />

            <div className="lx-card__foot">
              <span>
                Guideline chỉ đọc. Nội dung soạn ở nơi khác và nạp bằng lệnh{" "}
                <code>manage.py load_guideline</code>.
              </span>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
