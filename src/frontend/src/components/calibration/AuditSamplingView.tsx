'use client';

import React, { useState } from 'react';
import { DemoRegionNotice } from './DemoRegionNotice';
import { RANDOM_AUDIT_FIELDS, RANDOM_AUDIT_ROWS, RISK_ROWS } from '@/lib/calibration/sample-data';

type Tab = 'random' | 'risk';
const TABS: ReadonlyArray<[Tab, string]> = [['random', 'Kiểm tra ngẫu nhiên'], ['risk', 'Lấy mẫu theo rủi ro']];

export function AuditSamplingHeader() {
  return (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Audit Sampling</h1>
        <p className="lx-lead">Hai luồng lấy mẫu độc lập: kiểm tra ngẫu nhiên để ước lượng chất lượng, lấy mẫu theo rủi ro để tìm lỗi. Không suy ra tỷ lệ lỗi toàn dataset từ mẫu theo rủi ro.</p>
      </div>
      <div className="lx-actions">
        {/* TODO(backend): POST /api/audit-samples/ (chặn, không gọi API giả) */}
        <button type="button" className="lx-btn lx-btn--primary">Tạo mẫu mới</button>
      </div>
    </div>
  );
}

export function AuditSamplingBody() {
  const [tab, setTab] = useState<Tab>('random');
  return (
    <>
      {/* TODO(backend): GET /api/audit-samples/?stream=random|risk */}
      <DemoRegionNotice />
      <section className="lx-card" aria-label="Lấy mẫu kiểm toán">
        <div className="lx-tabs" role="tablist" style={{ padding: '0 var(--space-3)' }}>
          {TABS.map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={tab === key} className={`lx-tab${tab === key ? ' is-active' : ''}`} onClick={() => setTab(key)}>{label}</button>)}
        </div>
        {tab === 'random' && (
          <>
            <div className="lx-card__body lx-grid lx-grid--4">
              {RANDOM_AUDIT_FIELDS.map((f) => (
                <div key={f.k} className="lx-field"><span className="lx-label">{f.k}</span><span className={[f.mono ? 'lx-mono' : '', f.warn ? 'is-warn' : ''].filter(Boolean).join(' ') || undefined} style={f.warn ? { fontWeight: 600 } : undefined}>{f.v}</span></div>
              ))}
            </div>
            <div className="lx-scroll">
              <table className="lx-table" style={{ minWidth: 640 }}>
                <thead><tr><th>Frame</th><th>Task · Job</th><th>Trạng thái review</th><th>Kết quả</th></tr></thead>
                <tbody>
                  {RANDOM_AUDIT_ROWS.map((r) => (
                    <tr key={r.frame}>
                      <td className="lx-mono">{r.frame}</td><td className="lx-muted">{r.job}</td>
                      <td><span className={`lx-badge${r.status.tone ? ` lx-badge--${r.status.tone}` : ''}`}>{r.status.label}</span></td>
                      <td className={r.result ? undefined : 'lx-subtle'}>{r.result ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {tab === 'risk' && (
          <>
            <div className="lx-callout lx-callout--info" style={{ borderRadius: 0 }}><span className="lx-callout__text" style={{ fontSize: 13 }}>Mẫu theo rủi ro thiên lệch có chủ đích nên chỉ dùng để tìm lỗi nhanh hơn, không dùng để ước lượng chất lượng chung.</span></div>
            <div className="lx-scroll">
              <table className="lx-table" style={{ minWidth: 640 }}>
                <thead><tr><th>Tiêu chí rủi ro</th><th className="r">Frame được chọn</th><th className="r">Lỗi đã xác nhận</th><th className="r">Tỷ lệ</th></tr></thead>
                <tbody>{RISK_ROWS.map((r) => <tr key={r.name}><td className="lx-cell__main">{r.name}</td><td className="r">{r.n}</td><td className="r">{r.errors}</td><td className="r">{r.rate}</td></tr>)}</tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </>
  );
}
