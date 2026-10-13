'use client';

import React, { useEffect, useRef, useState } from 'react';
import { CLASS_ROWS, CONFUSED_PAIRS, ERROR_TYPES, EXPORT_FORMATS, REPORT_METRICS, REPORT_SCOPE, ROOT_CAUSES } from '@/lib/reports/sample-data';

type Tab = 'summary' | 'class' | 'cause';
const TABS: ReadonlyArray<[Tab, string]> = [['summary', 'Tóm tắt'], ['class', 'Theo lớp và loại hình'], ['cause', 'Nguyên nhân gốc']];
const DASH = <span className="lx-subtle">—</span>;

export function QualityReportHeader() {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    const onPointer = (e: MouseEvent) => { if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onPointer);
    return () => { document.removeEventListener('keydown', onKey); document.removeEventListener('mousedown', onPointer); };
  }, [open]);
  return (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Quality Report</h1>
        <p className="lx-lead">{REPORT_SCOPE}. Báo cáo luôn ghi rõ phạm vi, nguồn Ground Truth, coverage và những phần chưa đủ dữ liệu.</p>
      </div>
      <div className="lx-actions lx-actions--rel" ref={menuRef}>
        <span className="lx-badge lx-badge--danger">Release blocked</span>
        <button type="button" className="lx-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
          Xuất báo cáo
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 4.5 6 7.5 9 4.5" /></svg>
        </button>
        {open && (
          <div className="lx-menu lx-menu--end lx-menu--right" role="menu">
            {/* TODO(backend): POST /api/runs/{id}/report/export/ (pdf | csv | json) */}
            {EXPORT_FORMATS.map((f) => (
              <button key={f.key} type="button" className="lx-menu__item" role="menuitem" onClick={() => setOpen(false)}>
                <span className="lx-menu__t">{f.label}</span><span className="lx-menu__d">{f.note}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function QualityReportBody() {
  const [tab, setTab] = useState<Tab>('summary');
  return (
    <>
      {/* TODO(backend): GET /api/runs/{id}/report/ (metric, lỗi theo loại, theo lớp, nguyên nhân gốc) */}
      <div className="lx-grid lx-grid--4">
        {REPORT_METRICS.map((m) => (
          <div key={m.key} className="lx-metric">
            <span className="lx-metric__k">{m.label}</span>
            <span className={`lx-metric__v${m.tone ? ` ${m.tone}` : ''}`}>{m.value}</span>
            <span className="lx-metric__n">{m.note}</span>
          </div>
        ))}
      </div>

      <section className="lx-card" aria-label="Chi tiết báo cáo">
        <div className="lx-tabs lx-tabs--inset" role="tablist">
          {TABS.map(([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={tab === key} className={`lx-tab${tab === key ? ' is-active' : ''}`} onClick={() => setTab(key)}>{label}</button>
          ))}
        </div>

        {tab === 'summary' && (
          <div className="lx-card__body lx-cols">
            <div className="lx-main lx-stack lx-stack--3">
              <h2 className="lx-h2">Lỗi đã xác nhận theo loại</h2>
              {ERROR_TYPES.map((e) => (
                <div key={e.label} className="lx-bar"><span>{e.label}</span><div className="lx-bar__t"><i style={{ width: `${e.width}%` }} /></div><span className="lx-bar__n">{e.count}</span></div>
              ))}
            </div>
            <div className="lx-side lx-stack lx-stack--3">
              <h2 className="lx-h2">Cặp nhãn bị nhầm nhiều nhất</h2>
              <table className="lx-table lx-table--sm">
                <tbody>{CONFUSED_PAIRS.map((p) => <tr key={p.pair}><td>{p.pair}</td><td className="r">{p.count}</td></tr>)}</tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'class' && (
          <>
            <div className="lx-scroll">
              <table className="lx-table lx-table--min-700">
                <thead><tr><th>Lớp</th><th>Loại hình</th><th className="r">Intersection over Union</th><th className="r">Precision</th><th className="r">Recall</th><th className="r">Lỗi đã xác nhận</th></tr></thead>
                <tbody>
                  {CLASS_ROWS.map((c) => {
                    const w = c.warn ? 'r is-warn' : 'r';
                    return (
                      <tr key={c.name}>
                        <td className="lx-cell__main">{c.name}</td><td className="lx-muted">{c.kind}</td>
                        <td className={w}>{c.iou ?? DASH}</td><td className={w}>{c.precision ?? DASH}</td><td className={w}>{c.recall ?? DASH}</td>
                        <td className="r">{c.errors}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="lx-card__foot"><span>Lớp kém nhất được tô màu cảnh báo. Polyline chưa có Ground Truth nên ghi là chưa đánh giá, không ghi là đạt.</span></div>
          </>
        )}

        {tab === 'cause' && (
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-640">
              <thead><tr><th>Nguyên nhân gốc</th><th className="r">Số lỗi</th><th>Đề xuất</th></tr></thead>
              <tbody>{ROOT_CAUSES.map((r) => <tr key={r.cause}><td className="lx-cell__main">{r.cause}</td><td className="r">{r.count}</td><td className="lx-muted">{r.action}</td></tr>)}</tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
