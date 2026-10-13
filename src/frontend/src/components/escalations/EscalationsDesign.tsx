'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/lib/api/errors';
import { getDecisionCases, type DecisionCase } from '@/lib/escalations/api';
import { useAuth } from '@/lib/auth/auth-context';
import type { EscalationsTabKey, Tone } from '@/lib/mock/escalations';
import { EscalationsWorkspace } from './EscalationsWorkspace';

const SvgArrow = () => <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" /></svg>;
const LIST_TIP = 'Phân xử các case liên quan';

interface ApiListRow {
  id: number;
  a: string;
  b: string;
  c: string;
  d: string;
  e: string;
  tone: Tone;
}

function displayCode(prefix: 'GAP' | 'CASE', id: number) {
  return `${prefix}-${String(id).padStart(3, '0')}`;
}

function decisionLabel(item: DecisionCase) {
  if (item.outcome === 'confirm') {
    return item.correct_label ? `Gán nhãn ${item.correct_label}` : 'Xác nhận lỗi';
  }
  if (item.outcome === 'reject') return 'Bác bỏ';
  return 'Guideline còn thiếu';
}

function caseRow(item: DecisionCase): ApiListRow {
  return {
    id: item.id,
    a: displayCode('CASE', item.id),
    b: item.reason,
    c: item.rule_id,
    d: decisionLabel(item),
    e: item.case_version,
    tone: '',
  };
}

function gapRow(item: DecisionCase): ApiListRow {
  return {
    id: item.id,
    a: displayCode('GAP', item.id),
    b: item.reason,
    c: item.rule_id,
    d: `Issue #${item.issue_id}`,
    e: `Đã ghi nhận · ${item.case_version}`,
    tone: 'info',
  };
}

/**
 * Trang ba tab theo Escalations.dc.html. Guideline Gap là Decision Case có
 * outcome guideline_gap; cả hai danh sách cùng lấy từ API đã triển khai.
 */
export function EscalationsDesign() {
  const { session } = useAuth();
  const [tab, setTab] = useState<EscalationsTabKey>('gaps');
  const casesQuery = useQuery({
    queryKey: ['decision-cases', session?.user.id, 'escalations-list'],
    queryFn: ({ signal }) => getDecisionCases({}, signal),
    enabled: Boolean(session) && tab !== 'adj',
    retry: false,
  });
  const allCases = casesQuery.data ?? [];
  const guidelineGaps = allCases.filter(item => item.outcome === 'guideline_gap');
  const rows = tab === 'gaps' ? guidelineGaps.map(gapRow) : allCases.map(caseRow);
  const cols = tab === 'gaps'
    ? ['Mã', 'Nội dung còn thiếu', 'Quy tắc', 'Case liên quan', 'Trạng thái']
    : ['Mã', 'Tình huống', 'Quy tắc', 'Quyết định', 'Phiên bản'];
  const tabs: { key: EscalationsTabKey; label: string; count: number | null }[] = [
    { key: 'gaps', label: 'Guideline Gaps', count: casesQuery.data ? guidelineGaps.length : null },
    { key: 'cases', label: 'Decision Cases', count: casesQuery.data ? allCases.length : null },
    { key: 'adj', label: 'Adjudication', count: null },
  ];
  return (
    <div className="lx-page">
      <div className="lx-head">
        <div className="lx-head__text">
          <h1 className="lx-h1">Escalations</h1>
          <p className="lx-lead">Guideline Gap ghi lại chỗ hướng dẫn còn thiếu, Decision Case là các quyết định đã được phê duyệt. Từ đó, người có thẩm quyền phân xử các issue chưa đủ căn cứ hoặc reviewer bất đồng.</p>
        </div>
        <div className="lx-actions">
          {tab === 'gaps' && <button type="button" className="lx-btn lx-btn--primary" onClick={() => setTab('adj')}>Tạo Guideline Gap</button>}
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
        {tab !== 'adj' && casesQuery.isPending && <div className="lx-card__body lx-muted" role="status">Đang tải dữ liệu escalation…</div>}
        {tab !== 'adj' && casesQuery.isError && (
          <div className="lx-card__body">
            <div className="lx-callout" role="alert">
              <div className="lx-callout__text"><strong>Không tải được dữ liệu escalation.</strong><div>{errorMessage(casesQuery.error)}</div></div>
              <button className="lx-btn lx-btn--sm" type="button" onClick={() => casesQuery.refetch()}>Thử lại</button>
            </div>
          </div>
        )}
        {tab !== 'adj' && casesQuery.isSuccess && (
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-880">
              <thead><tr>{cols.map(col => <th key={col}>{col}</th>)}<th></th></tr></thead>
              <tbody>
                {rows.map(row => (
                  <tr key={row.id}>
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
    </div>
  );
}
