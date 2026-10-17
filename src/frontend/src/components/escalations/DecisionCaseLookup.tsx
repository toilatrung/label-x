'use client';

import React, { useId, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/lib/api/errors';
import {
  getDecisionCase,
  getDecisionCases,
  type DecisionCase,
  type DecisionCaseFilters,
} from '@/lib/escalations/api';
import { useAuth } from '@/lib/auth/auth-context';

interface DecisionCaseLookupProps {
  initialIssueId?: number;
  compact?: boolean;
}

const EMPTY_FILTERS: DecisionCaseFilters = {};

/** Shared read-only Decision Case lookup for Escalations and Review Workspace. */
export function DecisionCaseLookup({
  initialIssueId,
  compact = false,
}: DecisionCaseLookupProps) {
  return (
    <DecisionCaseLookupPanel
      key={initialIssueId ?? 'empty'}
      initialIssueId={initialIssueId}
      compact={compact}
    />
  );
}

function DecisionCaseLookupPanel({
  initialIssueId,
  compact,
}: Required<Pick<DecisionCaseLookupProps, 'compact'>> & Pick<DecisionCaseLookupProps, 'initialIssueId'>) {
  const { session } = useAuth();
  const id = useId();
  const initial = initialIssueId ? { issueId: initialIssueId } : EMPTY_FILTERS;
  const [draftIssue, setDraftIssue] = useState(initialIssueId ? String(initialIssueId) : '');
  const [draftRule, setDraftRule] = useState('');
  const [draftVersion, setDraftVersion] = useState('');
  const [filters, setFilters] = useState<DecisionCaseFilters>(initial);
  const [searched, setSearched] = useState(Boolean(initialIssueId));
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const query = useQuery({
    queryKey: ['decision-cases', session?.user.id, filters],
    queryFn: ({ signal }) => getDecisionCases(filters, signal),
    enabled: searched,
    retry: false,
  });
  const detailQuery = useQuery({
    queryKey: ['decision-case', selectedId],
    queryFn: ({ signal }) => getDecisionCase(selectedId!, signal),
    enabled: selectedId !== null,
    retry: false,
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const issueId = /^\d+$/.test(draftIssue.trim()) ? Number(draftIssue) : undefined;
    setFilters({
      ...(issueId ? { issueId } : {}),
      ...(draftRule.trim() ? { ruleId: draftRule.trim() } : {}),
      ...(draftVersion.trim() ? { version: draftVersion.trim() } : {}),
    });
    setSearched(true);
  };

  const reset = () => {
    setDraftIssue('');
    setDraftRule('');
    setDraftVersion('');
    setFilters(EMPTY_FILTERS);
    setSearched(false);
    setSelectedId(null);
  };

  const cases: DecisionCase[] = query.data ?? [];

  return (
    <section
      className={`lx-card lx-case-lookup${compact ? ' lx-case-lookup--compact' : ''}`}
      aria-label="Tra cứu Decision Case"
      aria-busy={query.isFetching}
    >
      <header className="lx-card__head">
        <div>
          <h2 className="lx-h2">Tra cứu Decision Case</h2>
          <div className="lx-hint">Tìm đúng issue, rule và phiên bản kết luận đã lưu.</div>
        </div>
      </header>

      <form className="lx-toolbar lx-case-filters" role="search" onSubmit={submit}>
        <div className="lx-field">
          <label className="lx-label" htmlFor={`${id}-issue`}>Issue ID</label>
          <input
            id={`${id}-issue`}
            className="lx-input lx-mono"
            inputMode="numeric"
            value={draftIssue}
            onChange={(event) => setDraftIssue(event.target.value)}
            placeholder="Ví dụ: 42"
          />
        </div>
        <div className="lx-field">
          <label className="lx-label" htmlFor={`${id}-rule`}>Rule ID</label>
          <input
            id={`${id}-rule`}
            className="lx-input lx-mono"
            value={draftRule}
            onChange={(event) => setDraftRule(event.target.value)}
            placeholder="Ví dụ: VEH-03"
          />
        </div>
        <div className="lx-field">
          <label className="lx-label" htmlFor={`${id}-version`}>Case version</label>
          <input
            id={`${id}-version`}
            className="lx-input lx-mono"
            value={draftVersion}
            onChange={(event) => setDraftVersion(event.target.value)}
            placeholder="Ví dụ: v2"
          />
        </div>
        <div className="lx-row lx-case-filters__actions">
          <button className="lx-btn lx-btn--primary" type="submit">Tra cứu</button>
          {searched && <button className="lx-btn" type="button" onClick={reset}>Đặt lại</button>}
        </div>
      </form>

      {!searched ? (
        <div className="lx-card__body lx-muted">Nhập điều kiện để tra cứu Decision Case.</div>
      ) : query.isPending ? (
        <div className="lx-card__body lx-muted" role="status">Đang tải Decision Case…</div>
      ) : query.isError ? (
        <div className="lx-card__body">
          <div className="lx-callout" role="alert">
            <div className="lx-callout__text">
              <strong>Không tải được Decision Case.</strong>
              <div>{errorMessage(query.error)}</div>
            </div>
            <button className="lx-btn lx-btn--sm" type="button" onClick={() => query.refetch()}>
              Thử lại
            </button>
          </div>
        </div>
      ) : cases.length === 0 ? (
        <div className="lx-card__body lx-muted">Không có Decision Case khớp điều kiện.</div>
      ) : (
        <div className="lx-scroll">
          <table className="lx-table" aria-label="Kết quả Decision Case">
            <thead>
              <tr>
                <th>Case / Version</th>
                <th>Issue</th>
                <th>Kết luận</th>
                <th>Rule / Nhãn đúng</th>
                <th>Lý do</th>
                <th>Người phân xử</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {cases.map((decisionCase) => (
                <tr key={decisionCase.id}>
                  <td>
                    <span className="lx-mono">#{decisionCase.id}</span>
                    <div className="lx-cell__sub lx-mono">{decisionCase.case_version}</div>
                  </td>
                  <td className="lx-mono">#{decisionCase.issue_id}</td>
                  <td><span className="lx-badge lx-badge--info">{decisionCase.outcome}</span></td>
                  <td>
                    <div className="lx-mono">{decisionCase.rule_id}</div>
                    <div className="lx-cell__sub">{decisionCase.correct_label || 'Không đổi nhãn'}</div>
                  </td>
                  <td>{decisionCase.reason}</td>
                  <td>
                    <span className="lx-mono">User #{decisionCase.actor_user_id}</span>
                    <div className="lx-cell__sub">{new Date(decisionCase.created_at).toLocaleString('vi-VN')}</div>
                  </td>
                  <td className="r"><button className="lx-btn lx-btn--sm" type="button" onClick={() => setSelectedId(decisionCase.id)}>Chi tiết</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selectedId !== null && (
        <div className="lx-card__body lx-stack" aria-label={`Chi tiết Decision Case ${selectedId}`}>
          <div className="lx-row lx-row--between"><h3 className="lx-h2">Decision Case #{selectedId}</h3><button className="lx-btn lx-btn--sm" type="button" onClick={() => setSelectedId(null)}>Đóng</button></div>
          {detailQuery.isPending && <p className="lx-muted" role="status">Đang tải chi tiết…</p>}
          {detailQuery.isError && <div className="lx-callout" role="alert">{errorMessage(detailQuery.error)}</div>}
          {detailQuery.data && <dl className="lx-kv">
            <dt>Issue</dt><dd className="lx-mono">#{detailQuery.data.issue_id}</dd>
            <dt>Kết luận</dt><dd>{detailQuery.data.outcome}</dd>
            <dt>Rule</dt><dd className="lx-mono">{detailQuery.data.rule_id}</dd>
            <dt>Nhãn đúng</dt><dd>{detailQuery.data.correct_label ?? '—'}</dd>
            <dt>Phiên bản</dt><dd className="lx-mono">{detailQuery.data.case_version}</dd>
            <dt>Lý do</dt><dd>{detailQuery.data.reason}</dd>
            <dt>Lịch sử</dt><dd>{detailQuery.data.history.length > 0 ? detailQuery.data.history.map(item => `${item.case_version}: ${item.outcome}`).join(' · ') : '—'}</dd>
          </dl>}
        </div>
      )}
    </section>
  );
}
