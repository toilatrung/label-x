'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { errorMessage } from '@/lib/api/errors';
import {
  cursorFrom,
  getDecisionCases,
  getGuidelineGaps,
  type DecisionCase,
  type GuidelineGap,
} from '@/lib/escalations/api';
import { useAuth } from '@/lib/auth/auth-context';
import { LIST_TIP, type EscalationsTabKey, type ListRow } from '@/lib/mock/escalations';
import { EscalationsWorkspace } from './EscalationsWorkspace';
import { GuidelineGapModal, splitGapDescription } from './GuidelineGapModal';

const SvgArrow = () => <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" /></svg>;

interface ApiListRow extends ListRow { id: number; sub?: string | null }

const GAP_COLS = ['Mã', 'Nội dung còn thiếu', 'Quy tắc', 'Case liên quan', 'Trạng thái'];
const CASE_COLS = ['Mã', 'Tình huống', 'Quy tắc', 'Quyết định', 'Phiên bản'];

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

/** API chỉ có trạng thái open | resolved; nhãn "Đề xuất sửa / Chờ phê duyệt" của thiết kế chưa có nguồn dữ liệu. */
function gapRow(item: GuidelineGap): ApiListRow {
  const { content, reason } = splitGapDescription(item.description);
  const resolved = item.status === 'resolved';
  return {
    id: item.id,
    a: `GAP-${String(item.id).padStart(3, '0')}`,
    b: content,
    sub: reason,
    c: item.rule_id,
    d: item.issue_id ? `QC-${String(item.issue_id).padStart(5, '0')}` : 'Không gắn issue',
    e: resolved
      ? `Đã giải quyết${item.resolved_in_version ? ` · Guideline ${item.resolved_in_version}` : ''}`
      : 'Đang mở',
    tone: resolved ? 'success' : 'warning',
  };
}

/** Guideline Gaps, Decision Cases và Adjudication đều dùng API thật (MBE-02). */
export function EscalationsDesign() {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<EscalationsTabKey>('gaps');
  const [gapOpen, setGapOpen] = useState(false);
  const [gapCursors, setGapCursors] = useState<(string | null)[]>([null]);
  const [createdGap, setCreatedGap] = useState<GuidelineGap | null>(null);
  const gapCursor = gapCursors.at(-1) ?? null;

  const gapsQuery = useQuery({
    queryKey: ['guideline-gaps', session?.user.id, gapCursor],
    queryFn: ({ signal }) => getGuidelineGaps({ cursor: gapCursor, signal }),
    enabled: Boolean(session),
    retry: false,
  });
  const casesQuery = useQuery({
    queryKey: ['decision-cases', session?.user.id, 'escalations-list'],
    queryFn: ({ signal }) => getDecisionCases({}, signal),
    enabled: Boolean(session) && tab === 'cases',
    retry: false,
  });

  const gaps = gapsQuery.data?.results ?? [];
  const nextGapCursor = cursorFrom(gapsQuery.data?.next);
  const allCases = casesQuery.data ?? [];
  const activeQuery = tab === 'gaps' ? gapsQuery : casesQuery;
  const rows: ApiListRow[] = tab === 'gaps' ? gaps.map(gapRow) : allCases.map(caseRow);
  const cols = tab === 'gaps' ? GAP_COLS : CASE_COLS;
  // Trang cursor không có tổng; khi còn trang sau, đếm hiển thị "50+" thay vì đoán số.
  const gapCount = gapsQuery.data
    ? (gapCursors.length === 1 && !nextGapCursor ? String(gaps.length) : `${gaps.length}+`)
    : null;
  const tabs: { key: EscalationsTabKey; label: string; count: string | null }[] = [
    { key: 'gaps', label: 'Guideline Gaps', count: gapCount },
    { key: 'cases', label: 'Decision Cases', count: casesQuery.data ? String(allCases.length) : null },
    { key: 'adj', label: 'Adjudication', count: null },
  ];

  const onGapCreated = (gap: GuidelineGap) => {
    setGapOpen(false);
    setCreatedGap(gap);
    setGapCursors([null]);
    void queryClient.invalidateQueries({ queryKey: ['guideline-gaps'] });
  };

  const showList = tab !== 'adj' && activeQuery.isSuccess;
  const listName = tab === 'gaps' ? 'Guideline Gaps' : 'Decision Cases';

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

      {tab === 'gaps' && createdGap && (
        <div className="lx-callout lx-callout--info" role="status">
          <div className="lx-callout__text">
            <strong>Đã tạo Guideline Gap GAP-{String(createdGap.id).padStart(3, '0')}</strong> · Quy tắc{' '}
            <span className="lx-mono">{createdGap.rule_id}</span>
            {createdGap.guideline_version ? <> · Guideline <span className="lx-mono">{createdGap.guideline_version}</span></> : null}
          </div>
        </div>
      )}

      <section className="lx-card" aria-label="Escalations">
        <div className="lx-tabs lx-tabs--inset" role="tablist" aria-label="Escalations">
          {tabs.map(item => (
            <button key={item.key} type="button" role="tab" aria-selected={tab === item.key}
              className={`lx-tab${tab === item.key ? ' is-active' : ''}`} onClick={() => setTab(item.key)}>
              {item.label}{item.count !== null && <span className="lx-count">{item.count}</span>}
            </button>
          ))}
        </div>
        {tab !== 'adj' && activeQuery.isPending && <div className="lx-card__body lx-muted" role="status">Đang tải {listName}…</div>}
        {tab !== 'adj' && activeQuery.isError && (
          <div className="lx-card__body">
            <div className="lx-callout" role="alert">
              <div className="lx-callout__text"><strong>Không tải được {listName}.</strong><div>{errorMessage(activeQuery.error)}</div></div>
              <button className="lx-btn lx-btn--sm" type="button" onClick={() => activeQuery.refetch()}>Thử lại</button>
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
                    <td className="lx-mono">{row.a}</td>
                    <td className="lx-cell__main">{row.b}{row.sub && <div className="lx-cell__sub">{row.sub}</div>}</td>
                    <td className="lx-muted">{row.c}</td><td className="lx-muted">{row.d}</td>
                    <td><span className={`lx-badge${row.tone ? ` lx-badge--${row.tone}` : ''}`}>{row.e}</span></td>
                    <td className="r"><button type="button" className="lx-iconbtn" onClick={() => setTab('adj')} data-tip={LIST_TIP} aria-label={LIST_TIP}><SvgArrow /></button></td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={6} className="lx-muted">
                    {tab === 'gaps' ? 'Chưa có Guideline Gap nào trong phạm vi hiện tại.' : 'Chưa có dữ liệu trong phạm vi hiện tại.'}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        {tab === 'gaps' && showList && (gapCursors.length > 1 || nextGapCursor) && (
          <footer className="lx-card__foot">
            <span>Hiển thị {gaps.length} Guideline Gap · Trang {gapCursors.length}</span>
            <nav className="lx-pager" aria-label="Phân trang Guideline Gap">
              <button className="lx-btn lx-btn--sm" type="button" disabled={gapCursors.length === 1 || gapsQuery.isFetching}
                onClick={() => setGapCursors(current => current.slice(0, -1))}>Trang trước</button>
              <button className="lx-btn lx-btn--sm" type="button" disabled={!nextGapCursor || gapsQuery.isFetching}
                onClick={() => { if (nextGapCursor) setGapCursors(current => [...current, nextGapCursor]); }}>Trang sau</button>
            </nav>
          </footer>
        )}
      </section>

      {tab === 'adj' && <EscalationsWorkspace />}
      {gapOpen && <GuidelineGapModal onClose={() => setGapOpen(false)} onCreated={onGapCreated} />}
    </div>
  );
}
