'use client';

import React, { useState } from 'react';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { SampleDataBadge } from '@/components/ui/SampleDataBadge';
import {
  CASES, ESCALATION_TABS, GAPS, LIST_TIP, type EscalationsTabKey,
} from '@/lib/mock/escalations';
import { EscalationsWorkspace } from './EscalationsWorkspace';

const SvgArrow = () => <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" /></svg>;

/**
 * Một trang ba tab theo Escalations.dc.html. Gaps và Decision Cases là dữ liệu minh họa (BLOCKER-030);
 * tab Adjudication dùng dữ liệu thật qua EscalationsWorkspace (API T-038/T-039).
 */
export function EscalationsDesign() {
  const [tab, setTab] = useState<EscalationsTabKey>('gaps');
  const list = tab === 'gaps' ? GAPS : tab === 'cases' ? CASES : null;
  return (
    <div className="lx-page">
      <div className="lx-head">
        <div className="lx-head__text">
          <h1 className="lx-h1">Escalations</h1>
          <p className="lx-lead">Guideline Gap ghi lại chỗ hướng dẫn còn thiếu, Decision Case là các quyết định đã được phê duyệt. Từ đó, người có thẩm quyền phân xử các issue chưa đủ căn cứ hoặc reviewer bất đồng.</p>
        </div>
        <div className="lx-actions">
          {tab === 'gaps' && <button type="button" className="lx-btn lx-btn--primary">Tạo Guideline Gap</button>}
        </div>
      </div>

      <section className="lx-card" aria-label="Escalations">
        <div className="lx-tabs lx-tabs--inset" role="tablist" aria-label="Escalations">
          {ESCALATION_TABS.map(item => (
            <button key={item.key} type="button" role="tab" aria-selected={tab === item.key}
              className={`lx-tab${tab === item.key ? ' is-active' : ''}`} onClick={() => setTab(item.key)}>
              {item.label}{item.count !== null && <span className="lx-count">{item.count}</span>}
            </button>
          ))}
        </div>
        {tab !== 'adj' && <div className="lx-card__body lx-row"><SampleDataBadge /><NotConnectedNotice /></div>}
        {list && (
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-880">
              <thead><tr>{list.cols.map(col => <th key={col}>{col}</th>)}<th></th></tr></thead>
              <tbody>
                {list.rows.map(row => (
                  <tr key={row.a}>
                    <td className="lx-mono">{row.a}</td><td className="lx-cell__main">{row.b}</td>
                    <td className="lx-muted">{row.c}</td><td className="lx-muted">{row.d}</td>
                    <td><span className={`lx-badge${row.tone ? ` lx-badge--${row.tone}` : ''}`}>{row.e}</span></td>
                    <td className="r"><button type="button" className="lx-iconbtn" onClick={() => setTab('adj')} data-tip={LIST_TIP} aria-label={LIST_TIP}><SvgArrow /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {tab === 'adj' && <EscalationsWorkspace />}
    </div>
  );
}
