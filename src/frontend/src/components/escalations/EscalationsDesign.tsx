'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { SampleDataBadge } from '@/components/ui/SampleDataBadge';
import {
  CASES, ESCALATION_TABS, GAPS, LIST_TIP, PENDING, type EscalationsTabKey,
} from '@/lib/mock/escalations';
import { EscalationsWorkspace } from './EscalationsWorkspace';

const SvgArrow = () => <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" /></svg>;

function AdjudicationSample() {
  return (
    <div className="lx-cols">
      <section className="lx-card" aria-label="Chờ phân xử" style={{ flex: '1 1 380px', maxWidth: 460 }}>
        <div className="lx-card__head"><h2 className="lx-h2">Chờ phân xử</h2><span className="lx-hint">18 case</span></div>
        <ul className="lx-list" role="listbox" aria-label="Case chờ phân xử">
          {PENDING.map((item, index) => (
            <li key={item.id} role="option" aria-selected={index === 0}>
              <div className="lx-row" style={{ justifyContent: 'space-between' }}><b className="lx-mono">{item.id}</b><span className="lx-badge lx-badge--warning">{item.badge}</span></div>
              <div className="lx-cell__main" style={{ marginTop: 4 }}>{item.title}</div>
              <div className="lx-cell__sub">{item.sub}</div>
            </li>
          ))}
        </ul>
        <div className="lx-card__foot"><span>Hiển thị 4 / 18</span><span className="lx-pager"><button type="button" className="lx-btn lx-btn--sm">Xem thêm</button></span></div>
      </section>

      <section className="lx-card lx-main" aria-label="Chi tiết phân xử mẫu">
        <div className="lx-card__head">
          <h2 className="lx-h2"><span className="lx-mono">QC-00098</span> · Sai nhãn: bus hay truck</h2>
          <Link className="lx-link" href="/review/workspace" style={{ fontSize: 13 }}>Mở trong Review Workspace</Link>
        </div>
        <div className="lx-card__body lx-stack">
          <div className="lx-grid lx-grid--3">
            <div className="lx-stack" style={{ gap: 6 }}><span className="lx-label">Quyết định của reviewer</span>
              <table className="lx-table" style={{ fontSize: 12 }}><tbody>
                <tr><td>Bình Hồ</td><td><span className="lx-badge lx-badge--success">Xác nhận lỗi</span></td></tr>
                <tr><td>An Nguyễn</td><td><span className="lx-badge">Bác bỏ</span></td></tr>
              </tbody></table></div>
            <div className="lx-stack" style={{ gap: 6 }}><span className="lx-label">Bằng chứng</span>
              <div className="lx-muted" style={{ fontSize: 13 }}>Annotation: bus<br />Mô hình độc lập: truck · 0.77<br />Mô hình thị giác – ngôn ngữ: không chắc chắn</div></div>
            <div className="lx-stack" style={{ gap: 6 }}><span className="lx-label">Hướng dẫn liên quan</span>
              <div className="lx-muted" style={{ fontSize: 13 }}>VEH-03 · Guideline v1.2<br />Chưa nêu rõ xe buýt mini chở hàng.</div></div>
          </div>
          <div className="lx-field"><span className="lx-label">Kết luận phân xử</span>
            <div className="lx-choices">
              <label className="lx-choice"><input type="radio" name="sample-adj" defaultChecked /><span>Xác nhận lỗi</span></label>
              <label className="lx-choice"><input type="radio" name="sample-adj" /><span>Bác bỏ</span></label>
              <label className="lx-choice"><input type="radio" name="sample-adj" /><span>Guideline còn thiếu</span></label>
            </div></div>
          <div className="lx-grid lx-grid--3">
            <div className="lx-field"><label className="lx-label" htmlFor="g1">Quy tắc áp dụng</label><select id="g1" className="lx-select"><option>VEH-03 · Phân loại phương tiện</option><option>VEH-05 · Xe đặc chủng</option></select></div>
            <div className="lx-field"><label className="lx-label" htmlFor="g2">Nhãn đúng</label><select id="g2" className="lx-select"><option>truck</option><option>bus</option><option>car</option></select></div>
            <div className="lx-field"><label className="lx-label" htmlFor="g3">Sau khi phân xử</label><select id="g3" className="lx-select"><option>Tạo yêu cầu sửa cho annotator</option><option>Chỉ ghi nhận quyết định</option></select></div>
          </div>
          <div className="lx-field"><label className="lx-label" htmlFor="g4">Lý do phân xử</label><textarea id="g4" className="lx-textarea" placeholder="Nêu căn cứ để các case tương tự có thể tham chiếu." /></div>
          {/* TODO(backend): POST /api/issues/{id}/adjudications/ và POST /api/guideline-gaps/; nút chặn, không gọi API giả */}
          <div className="lx-actions" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="lx-btn">Tạo Guideline Gap</button>
            <button type="button" className="lx-btn lx-btn--primary">Lưu phân xử</button>
          </div>
        </div>
      </section>
    </div>
  );
}

/**
 * Một trang ba tab theo Escalations.dc.html. Gaps/Cases và bố cục phân xử là dữ liệu minh họa; chưa có API.
 * Khối "Phân xử theo dữ liệu thật" là EscalationsWorkspace đã nối API (T-039) giữ lại dưới thiết kế, FE-12 sẽ hợp nhất.
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
        <div className="lx-tabs" role="tablist" aria-label="Escalations" style={{ padding: '0 var(--space-3)' }}>
          {ESCALATION_TABS.map(item => (
            <button key={item.key} type="button" role="tab" aria-selected={tab === item.key}
              className={`lx-tab${tab === item.key ? ' is-active' : ''}`} onClick={() => setTab(item.key)}>
              {item.label}<span className="lx-count">{item.count}</span>
            </button>
          ))}
        </div>
        <div className="lx-card__body lx-row"><SampleDataBadge /><NotConnectedNotice /></div>
        {list && (
          <div className="lx-scroll">
            <table className="lx-table" style={{ minWidth: 880 }}>
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

      {tab === 'adj' && (
        <>
          <AdjudicationSample />
          <section aria-label="Phân xử theo dữ liệu thật" className="lx-stack">
            <h2 className="lx-h2">Phân xử theo dữ liệu thật</h2>
            <EscalationsWorkspace />
          </section>
        </>
      )}
    </div>
  );
}
