'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { SampleDataBadge } from '@/components/ui/SampleDataBadge';
import { REWORK_ROWS, REWORK_TABS, type ReworkTabKey } from '@/lib/mock/rework';
import { SAMPLE, formatCount, formatPercent } from '@/lib/mock/fixtures';

/** Bước 3 của Review Center theo ReworkTracking.dc.html. Dữ liệu minh họa; chưa có API (xem lib/mock/rework.ts). */
export function ReworkTracking() {
  const [tab, setTab] = useState<ReworkTabKey>('todo');
  const current = REWORK_TABS.find(item => item.key === tab)!;
  const { rework } = SAMPLE;
  return (
    <>
      <div className="lx-row"><SampleDataBadge /><NotConnectedNotice /></div>
      <div className="lx-grid lx-grid--4">
        <div className="lx-metric"><span className="lx-metric__k">Tổng yêu cầu sửa</span><span className="lx-metric__v">{formatCount(rework.total)}</span><span className="lx-metric__n">Từ {formatCount(SAMPLE.confirmedErrors)} lỗi đã xác nhận</span></div>
        <div className="lx-metric"><span className="lx-metric__k">Chờ sửa</span><span className="lx-metric__v">5</span><span className="lx-metric__n">Annotator chưa nộp lại</span></div>
        <div className="lx-metric"><span className="lx-metric__k">Chờ xác minh</span><span className="lx-metric__v">7</span><span className="lx-metric__n">Reviewer cần kiểm tra revision mới</span></div>
        <div className="lx-metric"><span className="lx-metric__k">Hoàn thành</span><span className="lx-metric__v">{formatPercent(rework.closedRate)}</span>
          <div className="lx-progress" role="img" aria-label={`Hoàn thành ${Math.round(rework.closedRate)}%`}><i style={{ width: `${rework.closedRate}%` }} /></div>
          <span className="lx-metric__n">{rework.closed} / {rework.total} yêu cầu đã đóng</span></div>
      </div>
      <section className="lx-card" aria-label="Yêu cầu sửa">
        <div className="lx-tabs lx-tabs--inset" role="tablist" aria-label="Trạng thái yêu cầu sửa">
          {REWORK_TABS.map(item => (
            <button key={item.key} type="button" role="tab" aria-selected={tab === item.key}
              className={`lx-tab${tab === item.key ? ' is-active' : ''}`} onClick={() => setTab(item.key)}>
              {item.label}<span className="lx-count">{item.count}</span>
            </button>
          ))}
        </div>
        <div className="lx-scroll">
          <table className="lx-table lx-table--min-900">
            <thead><tr><th>Mã yêu cầu</th><th>Issue</th><th>Frame · Object</th><th>Việc cần sửa</th><th>Annotator</th><th>Hạn</th><th>Mức độ</th><th></th></tr></thead>
            <tbody>
              {REWORK_ROWS[tab].map(item => (
                <tr key={item.id}>
                  <td className="lx-mono">{item.id}</td>
                  <td className="lx-mono">{item.issue}</td>
                  <td className="lx-muted">{item.where}</td>
                  <td>{item.action}</td>
                  <td className="lx-muted">{item.who}</td>
                  <td className="lx-muted">{item.due}</td>
                  <td><span className={`lx-badge${item.severityTone ? ` lx-badge--${item.severityTone}` : ''}`}>{item.severity}</span></td>
                  <td className="r">
                    {/* TODO(backend): GET /api/rework/{id}/ cho deep link; hiện mở Review Workspace */}
                    <Link className="lx-iconbtn" href="/review/workspace" data-tip={current.tip} aria-label={current.tip}>
                      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" /></svg>
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
