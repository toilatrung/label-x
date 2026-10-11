import React from 'react';
import { DemoRegionNotice } from './DemoRegionNotice';
import { MANIFEST, MANIFEST_TITLE, RELEASES } from '@/lib/reports/sample-data';

const DASH = <span className="lx-subtle">—</span>;

export function ReleaseHistoryBody() {
  return (
    <div className="lx-cols">
      <section className="lx-card lx-main" aria-label="Các lần phát hành">
        <div className="lx-card__head"><h2 className="lx-h2">Các lần phát hành</h2></div>
        {/* TODO(backend): GET /api/releases/ */}
        <div className="lx-card__body"><DemoRegionNotice /></div>
        <div className="lx-scroll">
          <table className="lx-table" style={{ minWidth: 640 }}>
            <thead><tr><th>Phiên bản</th><th>Quality Control Run</th><th className="r">Frame</th><th>Phê duyệt bởi</th><th>Ngày</th><th>Trạng thái</th></tr></thead>
            <tbody>
              {RELEASES.map((r) => (
                <tr key={r.version} aria-selected={r.selected || undefined}>
                  <td className="lx-cell__main">{r.version}</td>
                  <td className="lx-mono">{r.run}</td>
                  <td className="r">{r.frames}</td>
                  <td className="lx-muted">{r.approver ?? DASH}</td>
                  <td className="lx-muted">{r.date ?? DASH}</td>
                  <td><span className={`lx-badge lx-badge--${r.status.tone}`}>{r.status.label}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="lx-card lx-side" style={{ flexBasis: 420 }} aria-label="Manifest">
        <div className="lx-card__head">
          <h2 className="lx-h2">{MANIFEST_TITLE}</h2>
          {/* TODO(backend): GET /api/releases/{id}/manifest/ (tải JSON) */}
          <button type="button" className="lx-iconbtn" data-tip="Tải manifest (JSON)" aria-label="Tải manifest (JSON)">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3v7M5 7l3 3 3-3M3 13h10" /></svg>
          </button>
        </div>
        <div className="lx-card__body lx-stack">
          <DemoRegionNotice />
          <dl className="lx-kv">
            {MANIFEST.map((m) => (
              <React.Fragment key={m.k}><dt>{m.k}</dt><dd className={m.mono ? 'lx-mono' : undefined}>{m.v}</dd></React.Fragment>
            ))}
          </dl>
        </div>
      </section>
    </div>
  );
}
