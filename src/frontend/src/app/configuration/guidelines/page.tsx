"use client";

/**
 * Màn xem guideline — /configuration/guidelines
 *
 * Chức năng: Tra cứu phiên bản guideline và rule áp dụng cho annotation.
 * Chỉ đọc, không có thao tác tạo/sửa/xóa (scope T-003, CR-101 pilot).
 *
 * Design System: lx-* classes, bảng là chính (labelx-design SKILL.md).
 * Contract: OpenAPI contract types (contract.d.ts).
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/contract";

type GuidelineRule = components["schemas"]["GuidelineRule"];
type PaginatedGuidelineRuleList = components["schemas"]["PaginatedGuidelineRuleList"];
type ApiError = components["schemas"]["Error"];

interface CustomError extends Error {
  status?: number;
  code?: components["schemas"]["ErrorCode"];
}

async function fetchRules(versionTag?: string): Promise<PaginatedGuidelineRuleList> {
  const { data, error, response } = await apiClient.GET("/api/guidelines/rules/", {
    params: {
      query: versionTag ? { version: versionTag } : undefined,
    },
  });

  if (error || !data) {
    const errPayload = error as ApiError | undefined;
    const status = response?.status ?? 500;
    const code = errPayload?.code;
    const message =
      errPayload?.message ?? (response ? `HTTP ${response.status}` : "Không thể kết nối đến máy chủ.");

    const customErr: CustomError = new Error(message);
    customErr.status = status;
    customErr.code = code;
    throw customErr;
  }

  return data;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EmptyState({ message, colSpan }: { message: string; colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan} className="c lx-subtle lx-guideline-empty">
        {message}
      </td>
    </tr>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span className={`lx-badge ${active ? "lx-badge--success" : ""}`}>
      {active ? "Mới nhất" : "Đã thay thế"}
    </span>
  );
}

function VersionTable({
  versionTag,
  ruleCount,
  isSelected,
  onSelect,
  errorMessage,
}: {
  versionTag: string | null;
  ruleCount: number;
  isSelected: boolean;
  onSelect: (tag: string) => void;
  errorMessage?: string;
}) {
  return (
    <div className="lx-scroll">
      <table className="lx-table lx-guideline-table-version">
        <thead>
          <tr>
            <th>Phiên bản</th>
            <th>Trạng thái</th>
            <th>Số rule</th>
            <th className="r"></th>
          </tr>
        </thead>
        <tbody>
          {errorMessage ? (
            <EmptyState message={errorMessage} colSpan={4} />
          ) : !versionTag ? (
            <EmptyState message="Chưa có guideline nào được nạp." colSpan={4} />
          ) : (
            <tr aria-selected={isSelected ? "true" : undefined}>
              <td>
                <span className="lx-mono">{versionTag}</span>
              </td>
              <td>
                <StatusBadge active={true} />
              </td>
              <td className="lx-muted">{ruleCount} rule</td>
              <td className="r">
                <button
                  className="lx-btn lx-btn--sm"
                  onClick={() => onSelect(versionTag)}
                  aria-label={`Xem rules của ${versionTag}`}
                >
                  {isSelected ? "Đang xem" : "Xem rules"}
                </button>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function RuleTable({ rules }: { rules: GuidelineRule[] }) {
  return (
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
          {rules.length === 0 ? (
            <EmptyState message="Phiên bản này không có rule nào." colSpan={3} />
          ) : (
            rules.map((r) => (
              <tr key={r.rule_id}>
                <td>
                  <span className="lx-mono">{r.rule_id}</span>
                </td>
                <td className="lx-muted">{r.section}</td>
                <td className="lx-guideline-rule-content">
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

  const rulesQuery = useQuery({
    queryKey: ["guideline-rules", selectedTag],
    queryFn: () => fetchRules(selectedTag ?? undefined),
  });

  const rules: GuidelineRule[] = rulesQuery.data?.results ?? [];
  const latestVersion = rules[0]?.guideline_version ?? null;
  const currentVersion = selectedTag ?? latestVersion;

  const queryError = rulesQuery.error as CustomError | null;
  // Ưu tiên error code NOT_AUTHENTICATED (kể cả khi HTTP trả 403)
  const isNotAuthenticated =
    queryError?.code === "NOT_AUTHENTICATED" || queryError?.status === 401;
  // FORBIDDEN ưu tiên error code, loại trừ trường hợp NOT_AUTHENTICATED trả kèm 403
  const isForbidden =
    !isNotAuthenticated &&
    (queryError?.code === "FORBIDDEN" || queryError?.status === 403);

  return (
    <div className="lx lx-guideline-wrapper">
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

        {/* Thông báo lỗi quyền/xác thực */}
        {isNotAuthenticated && (
          <div className="lx-callout" role="alert">
            <div className="lx-callout__text">
              <strong>Chưa đăng nhập</strong>
              <div>
                {queryError?.message ||
                  "Bạn chưa đăng nhập hoặc phiên làm việc đã hết hạn. Vui lòng đăng nhập lại để xem thông tin guideline."}
              </div>
            </div>
          </div>
        )}

        {isForbidden && (
          <div className="lx-callout" role="alert">
            <div className="lx-callout__text">
              <strong>Không có quyền truy cập</strong>
              <div>
                {queryError?.message ||
                  "Bạn không có quyền xem thông tin guideline. Yêu cầu vai trò Reviewer, QA Lead, QC Admin hoặc Super Admin."}
              </div>
            </div>
          </div>
        )}

        {rulesQuery.isError && !isNotAuthenticated && !isForbidden && (
          <div className="lx-callout" role="alert">
            <div className="lx-callout__text">
              <strong>Không tải được dữ liệu</strong>
              <div>{queryError?.message || "Đã xảy ra lỗi khi tải danh sách rules từ máy chủ."}</div>
            </div>
          </div>
        )}

        {/* Guideline versions */}
        <section className="lx-card">
          <header className="lx-card__head">
            <span className="lx-cell__main">Phiên bản guideline</span>
            {rulesQuery.isLoading && <span className="lx-subtle">Đang tải…</span>}
            {isNotAuthenticated && (
              <span className="lx-badge lx-badge--danger">Chưa đăng nhập</span>
            )}
            {isForbidden && (
              <span className="lx-badge lx-badge--danger">Không có quyền</span>
            )}
            {rulesQuery.isError && !isNotAuthenticated && !isForbidden && (
              <span className="lx-badge lx-badge--danger">Lỗi kết nối</span>
            )}
          </header>

          <VersionTable
            versionTag={currentVersion}
            ruleCount={rules.length}
            isSelected={true}
            onSelect={setSelectedTag}
            errorMessage={
              isNotAuthenticated
                ? "Chưa đăng nhập — vui lòng đăng nhập để xem guideline."
                : isForbidden
                ? "Không có quyền truy cập — tài khoản hiện tại không có quyền xem guideline."
                : rulesQuery.isError
                ? "Không tải được dữ liệu guideline từ máy chủ."
                : undefined
            }
          />
        </section>

        {/* Rules của version được chọn */}
        {currentVersion && !rulesQuery.isError && (
          <section className="lx-card">
            <header className="lx-card__head">
              <div className="lx-guideline-head-title">
                <span className="lx-cell__main">Rules —</span>
                <span className="lx-mono">{currentVersion}</span>
              </div>
              {rulesQuery.isLoading && <span className="lx-subtle">Đang tải…</span>}
              {!rulesQuery.isLoading && (
                <span className="lx-subtle">{rules.length} rule</span>
              )}
            </header>

            <RuleTable rules={rules} />

            <footer className="lx-card__foot">
              <span>
                Guideline chỉ đọc. Nội dung soạn ở nơi khác và nạp bằng lệnh{" "}
                <code>manage.py load_guideline</code>.
              </span>
            </footer>
          </section>
        )}
      </main>
    </div>
  );
}
