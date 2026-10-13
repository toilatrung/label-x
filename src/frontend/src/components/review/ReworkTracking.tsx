'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import { errorMessage } from '@/lib/api/errors';
import { getReworks, type ReworkItem, type ReworkStatus } from '@/lib/review/rework-api';

type ReworkTabKey = 'todo' | 'verify' | 'closed';

const TAB_CONFIG: Array<{
  key: ReworkTabKey;
  label: string;
  tip: string;
  statuses: ReworkStatus[];
}> = [
  { key: 'todo', label: 'Chờ sửa', tip: 'Mở yêu cầu trên CVAT', statuses: ['fix_pending', 'reopened'] },
  { key: 'verify', label: 'Chờ xác minh', tip: 'Xác minh revision mới', statuses: ['recheck_pending'] },
  { key: 'closed', label: 'Đã đóng', tip: 'Xem yêu cầu trên CVAT', statuses: ['resolved'] },
];

const SEVERITY = {
  critical: { label: 'Nghiêm trọng', tone: 'danger' },
  medium: { label: 'Trung bình', tone: 'warning' },
  minor: { label: 'Nhẹ', tone: '' },
} as const;

function countOf(counts: Record<string, number> | undefined, status: ReworkStatus) {
  return counts?.[status] ?? 0;
}

/** Bước 3 của Review Center theo ReworkTracking.dc.html, dùng GET /api/rework/. */
export function ReworkTracking() {
  const { datasetId, session } = useAuth();
  const [tab, setTab] = useState<ReworkTabKey>('todo');
  const current = TAB_CONFIG.find(item => item.key === tab)!;
  const query = useQuery({
    queryKey: ['rework', session?.user.id, datasetId, tab],
    queryFn: async ({ signal }) => {
      const pages = await Promise.all(current.statuses.map(status => getReworks(datasetId!, status, signal)));
      return { rows: pages.flatMap(page => page.results), counts: pages[0]?.counts ?? {} };
    },
    enabled: Boolean(session && datasetId),
    retry: false,
  });
  const counts = query.data?.counts;
  const todoCount = countOf(counts, 'fix_pending') + countOf(counts, 'reopened');
  const verifyCount = countOf(counts, 'recheck_pending');
  const closedCount = countOf(counts, 'resolved');
  const total = todoCount + verifyCount + closedCount;
  const closedRate = total > 0 ? (closedCount / total) * 100 : 0;
  const tabCount = (key: ReworkTabKey) => key === 'todo' ? todoCount : key === 'verify' ? verifyCount : closedCount;

  return (
    <>
      <div className="lx-grid lx-grid--4">
        <div className="lx-metric"><span className="lx-metric__k">Tổng yêu cầu sửa</span><span className="lx-metric__v">{total.toLocaleString('vi-VN')}</span><span className="lx-metric__n">Trong phạm vi Dataset đang chọn</span></div>
        <div className="lx-metric"><span className="lx-metric__k">Chờ sửa</span><span className="lx-metric__v">{todoCount}</span><span className="lx-metric__n">Annotator chưa nộp lại</span></div>
        <div className="lx-metric"><span className="lx-metric__k">Chờ xác minh</span><span className="lx-metric__v">{verifyCount}</span><span className="lx-metric__n">Reviewer cần kiểm tra revision mới</span></div>
        <div className="lx-metric"><span className="lx-metric__k">Hoàn thành</span><span className="lx-metric__v">{closedRate.toFixed(1)}%</span>
          <div className="lx-progress" role="img" aria-label={`Hoàn thành ${Math.round(closedRate)}%`}><i style={{ width: `${closedRate}%` }} /></div>
          <span className="lx-metric__n">{closedCount} / {total} yêu cầu đã đóng</span></div>
      </div>
      <section className="lx-card" aria-label="Yêu cầu sửa">
        <div className="lx-tabs lx-tabs--inset" role="tablist" aria-label="Trạng thái yêu cầu sửa">
          {TAB_CONFIG.map(item => (
            <button key={item.key} type="button" role="tab" aria-selected={tab === item.key}
              className={`lx-tab${tab === item.key ? ' is-active' : ''}`} onClick={() => setTab(item.key)}>
              {item.label}<span className="lx-count">{tabCount(item.key)}</span>
            </button>
          ))}
        </div>
        {!datasetId && <div className="lx-card__body lx-muted">Vui lòng chọn Dataset để xem yêu cầu sửa.</div>}
        {query.isPending && datasetId && <div className="lx-card__body lx-muted" role="status">Đang tải yêu cầu sửa…</div>}
        {query.isError && (
          <div className="lx-card__body">
            <div className="lx-callout" role="alert">
              <div className="lx-callout__text"><strong>Không tải được yêu cầu sửa.</strong><div>{errorMessage(query.error)}</div></div>
              <button type="button" className="lx-btn lx-btn--sm" onClick={() => query.refetch()}>Thử lại</button>
            </div>
          </div>
        )}
        {query.isSuccess && (
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-900">
              <thead><tr><th>Mã yêu cầu</th><th>Issue</th><th>Frame · Object</th><th>Việc cần sửa</th><th>Annotator</th><th>Hạn</th><th>Mức độ</th><th></th></tr></thead>
              <tbody>
                {query.data.rows.map((item: ReworkItem) => {
                  const severity = SEVERITY[item.severity];
                  return (
                    <tr key={item.id}>
                      <td className="lx-mono">RW-{String(item.id).padStart(4, '0')}</td>
                      <td className="lx-mono">QC-{String(item.issue_id).padStart(5, '0')}</td>
                      <td className="lx-muted">Frame {String(item.frame_id).padStart(5, '0')} · —</td>
                      <td>{item.instruction}</td>
                      <td className="lx-muted">User #{item.annotator_user_id}</td>
                      <td className="lx-muted">{item.due_at.slice(0, 10)}</td>
                      <td><span className={`lx-badge${severity.tone ? ` lx-badge--${severity.tone}` : ''}`}>{severity.label}</span></td>
                      <td className="r">
                        <a className="lx-iconbtn" href={item.cvat_deep_link} target="_blank" rel="noopener noreferrer" data-tip={current.tip} aria-label={current.tip}>
                          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" /></svg>
                        </a>
                      </td>
                    </tr>
                  );
                })}
                {query.data.rows.length === 0 && <tr><td colSpan={8} className="lx-muted">Chưa có yêu cầu sửa ở trạng thái này.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
