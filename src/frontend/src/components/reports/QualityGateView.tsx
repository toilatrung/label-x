'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { DemoRegionNotice } from './DemoRegionNotice';
import { GATE_CONDITIONS, GATE_SUMMARY, WAIVER_CONDITIONS } from '@/lib/reports/sample-data';

export function QualityGateBody() {
  const [condition, setCondition] = useState<string>(WAIVER_CONDITIONS[0]);
  const [reason, setReason] = useState('');
  const [pulse, setPulse] = useState(0);
  return (
    <div className="lx-cols">
      <section className="lx-card lx-main" aria-label="Điều kiện phát hành">
        <div className="lx-card__head"><h2 className="lx-h2">Điều kiện phát hành</h2><span className="lx-hint">{GATE_SUMMARY}</span></div>
        {/* TODO(backend): GET /api/runs/{id}/gate/ (runs_gate đã có trong contract, chưa nối) */}
        <div className="lx-card__body"><DemoRegionNotice /></div>
        <div className="lx-scroll">
          <table className="lx-table lx-table--min-720">
            <thead><tr><th>Điều kiện</th><th>Kết quả</th><th>Trạng thái</th><th>Cần làm</th></tr></thead>
            <tbody>
              {GATE_CONDITIONS.map((g) => (
                <tr key={g.name}>
                  <td className="lx-cell__main">{g.name}</td>
                  <td className="lx-muted">
                    {g.resultStrong ? <><span className={`${g.resultTone} lx-strong`}>{g.resultStrong}</span>{g.resultTail}</> : g.result}
                  </td>
                  <td><span className={`lx-badge${g.badge.tone ? ` lx-badge--${g.badge.tone}` : ''}`}>{g.badge.label}</span></td>
                  <td className={g.action || g.link ? undefined : 'lx-subtle'}>
                    {g.link ? <Link className="lx-link" href={g.link.href}>{g.link.label}</Link> : g.action ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <aside className="lx-card lx-side" aria-label="Phê duyệt phát hành">
        <div className="lx-card__head"><h2 className="lx-h2">Phê duyệt phát hành</h2></div>
        <div className="lx-card__body lx-stack">
          <DemoRegionNotice pulse={pulse} />
          <p className="lx-muted lx-m-0 lx-text-13">Chưa thể phát hành vì còn 3 điều kiện chưa đạt. Hệ thống không tự quyết định phát hành.</p>
          {/* TODO(backend): POST /api/releases/{id}/approve/ */}
          <button type="button" className="lx-btn lx-btn--primary lx-btn--block" disabled>Phê duyệt phát hành</button>
          <div className="lx-stack lx-stack--2 lx-stack--divided">
            <span className="lx-label">Hoặc xin waiver cho điều kiện chưa đạt</span>
            <div className="lx-field">
              <label className="lx-label" htmlFor="waiver-condition">Điều kiện</label>
              <select id="waiver-condition" className="lx-select" value={condition} onChange={(e) => setCondition(e.target.value)}>
                {WAIVER_CONDITIONS.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div className="lx-field">
              <label className="lx-label" htmlFor="waiver-reason">Lý do (bắt buộc)</label>
              <textarea id="waiver-reason" className="lx-textarea" value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="Nêu rõ người chịu trách nhiệm và căn cứ. Mọi waiver đều được ghi vào nhật ký kiểm toán." />
            </div>
            {/* TODO(backend): POST /api/waivers/ (waivers_create đã có trong contract; chưa gọi vì chưa nối) */}
            <button type="button" className="lx-btn" onClick={() => setPulse((n) => n + 1)}>Gửi xin waiver</button>
          </div>
        </div>
      </aside>
    </div>
  );
}
