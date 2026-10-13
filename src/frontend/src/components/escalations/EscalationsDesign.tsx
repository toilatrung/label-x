'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/lib/api/errors';
import { getDecisionCases, type DecisionCase } from '@/lib/escalations/api';
import { useAuth } from '@/lib/auth/auth-context';
import { GAPS, LIST_TIP, type EscalationsTabKey, type ListRow } from '@/lib/mock/escalations';
import { EscalationsWorkspace } from './EscalationsWorkspace';
import { GuidelineGapModal, type GuidelineGapDraft } from './GuidelineGapModal';

const SvgArrow = () => <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" /></svg>;

interface ApiListRow extends ListRow { id: number }

function decisionLabel(item: DecisionCase) {
  if (item.outcome === 'confirm') return item.correct_label ? `Gán nhãn ${item.correct_label}` : 'Xác nhận lỗi';
  if (item.outcome === 'reject') return 'Bác bỏ';
  return 'Guideline còn thiếu';
}

function caseRow(item: DecisionCase): ApiListRow {
  return {
    id: item.id,
    a: `CASE-${String(item.id).padStart(3, '0')}`,
    b: item.reason,
    c: item.rule_id,
    d: decisionLabel(item),
    e: item.case_version,
    tone: '',
  };
}

/** Guideline Gaps dùng mock theo sketchup vì API riêng chưa có; Decision Cases và Adjudication dùng API thật. */
export function EscalationsDesign() {
  const { session } = useAuth();
  const [tab, setTab] = useState<EscalationsTabKey>('gaps');
  const [gapOpen, setGapOpen] = useState(false);
  const [createdGaps, setCreatedGaps] = useState<ListRow[]>([]);
  const casesQuery = useQuery({
    queryKey: ['decision-cases', session?.user.id, 'escalations-list'],
    queryFn: ({ signal }) => getDecisionCases({}, signal),
    enabled: Boolean(session) && tab === 'cases',
    retry: false,
  });
  const allCases = casesQuery.data ?? [];
  const rows: Array<ListRow | ApiListRow> = tab === 'gaps' ? [...createdGaps, ...GAPS.rows] : allCases.map(caseRow);
  const cols = tab === 'gaps' ? GAPS.cols : ['Mã', 'Tình huống', 'Quy tắc', 'Quyết định', 'Phiên bản'];
  const tabs: { key: EscalationsTabKey; label: string; count: number | null }[] = [
    { key: 'gaps', label: 'Guideline Gaps', count: 6 + createdGaps.length },
    { key: 'cases', label: 'Decision Cases', count: casesQuery.data ? allCases.length : null },
    { key: 'adj', label: 'Adjudication', count: null },
  ];

  const addMockGap = (draft: GuidelineGapDraft) => {
    const nextNumber = 13 + createdGaps.length;
    setCreatedGaps(current => [{
      a: `GAP-${String(nextNumber).padStart(3, '0')}`,
      b: draft.content,
      c: draft.rule,
      d: draft.issueId ? `Issue #${draft.issueId}` : '0 case',
      e: 'Đề xuất sửa',
      tone: 'info',
    }, ...current]);
    setGapOpen(false);
  };

  const showList = tab === 'gaps' || (tab === 'cases' && casesQuery.isSuccess);

  return (
    <div className="lx-page">
      <div className="lx-head">
        <div className="lx-head__text">
          <h1 className="lx-h1">Escalations</h1>
          <p className="lx-lead">Guideline Gap ghi lại chỗ hướng dẫn còn thiếu, Decision Case là các quyết định đã được phê duyệt. Từ đó, người có thẩm quyền phân xử các issue chưa đủ căn cứ hoặc reviewer bất đồng.</p>
        </div>
        <div className="lx-actions">
          {tab === 'gaps' && <button type="button" className="lx-btn lx-btn--primary" onClick={() => setGapOpen(true)}>Tạo Guideline Gap</button>}
        </div>
      </div>

      <section className="lx-card" aria-label="Escalations">
        <div className="lx-tabs lx-tabs--inset" role="tablist" aria-label="Escalations">
          {tabs.map(item => (
            <button key={item.key} type="button" role="tab" aria-selected={tab === item.key}
              className={`lx-tab${tab === item.key ? ' is-active' : ''}`} onClick={() => setTab(item.key)}>
              {item.label}{item.count !== null && <span className="lx-count">{item.count}</span>}
            </button>
          ))}
        </div>
        {tab === 'cases' && casesQuery.isPending && <div className="lx-card__body lx-muted" role="status">Đang tải Decision Cases…</div>}
        {tab === 'cases' && casesQuery.isError && (
          <div className="lx-card__body">
            <div className="lx-callout" role="alert">
              <div className="lx-callout__text"><strong>Không tải được Decision Cases.</strong><div>{errorMessage(casesQuery.error)}</div></div>
              <button className="lx-btn lx-btn--sm" type="button" onClick={() => casesQuery.refetch()}>Thử lại</button>
            </div>
          </div>
        )}
        {showList && (
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-880">
              <thead><tr>{cols.map(col => <th key={col}>{col}</th>)}<th></th></tr></thead>
              <tbody>
                {rows.map(row => (
                  <tr key={row.a}>
                    <td className="lx-mono">{row.a}</td><td className="lx-cell__main">{row.b}</td>
                    <td className="lx-muted">{row.c}</td><td className="lx-muted">{row.d}</td>
                    <td><span className={`lx-badge${row.tone ? ` lx-badge--${row.tone}` : ''}`}>{row.e}</span></td>
                    <td className="r"><button type="button" className="lx-iconbtn" onClick={() => setTab('adj')} data-tip={LIST_TIP} aria-label={LIST_TIP}><SvgArrow /></button></td>
                  </tr>
                ))}
                {rows.length === 0 && <tr><td colSpan={6} className="lx-muted">Chưa có dữ liệu trong phạm vi hiện tại.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {tab === 'adj' && <EscalationsWorkspace />}
      {gapOpen && <GuidelineGapModal onClose={() => setGapOpen(false)} onCreate={addMockGap} />}
    </div>
  );
}
