'use client';

import React from 'react';
import Link from 'next/link';
import { DemoRegionNotice, signalNoticeAttention } from './DemoRegionNotice';
import { BENCHMARKS, BENCHMARK_DETAIL } from '@/lib/calibration/sample-data';

export function BenchmarkHeader() {
  return (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Ground Truth Benchmark</h1>
        <p className="lx-lead">Tập chuẩn do chuyên gia duyệt và khoá đáp án. Metric về độ chính xác chỉ tính khi có Ground Truth đúng phạm vi và taxonomy.</p>
      </div>
      <div className="lx-actions">
        {/* TODO(backend): POST /api/benchmarks/import-cvat/ ; POST /api/benchmarks/ (chặn, không gọi API giả) */}
        <button type="button" className="lx-btn" onClick={signalNoticeAttention}>Nhập từ CVAT</button>
        <button type="button" className="lx-btn lx-btn--primary" onClick={signalNoticeAttention}>Tạo benchmark</button>
      </div>
    </div>
  );
}

export function BenchmarkBody() {
  return (
    <>
      {/* TODO(backend): GET /api/benchmarks/ */}
      <DemoRegionNotice listenGlobal />
      <div className="lx-cols">
        <section className="lx-card lx-main" aria-label="Các phiên bản benchmark">
          <div className="lx-card__head"><h2 className="lx-h2">Các phiên bản benchmark</h2></div>
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-640">
              <thead><tr><th>Phiên bản</th><th>Phạm vi</th><th className="r">Frame</th><th>Chuyên gia duyệt</th><th>Trạng thái</th><th></th></tr></thead>
              <tbody>
                {BENCHMARKS.map((b) => (
                  <tr key={b.version} aria-selected={b.selected || undefined}>
                    <td className="lx-cell__main">{b.version}</td><td className="lx-muted">{b.scope}</td><td className="r">{b.frames}</td><td className="lx-muted">{b.expert}</td>
                    <td><span className={`lx-badge${b.status.tone ? ` lx-badge--${b.status.tone}` : ''}`}>{b.status.label}</span></td>
                    <td className="r"><Link className="lx-iconbtn" href="/calibration/calibration" data-tip="Xem benchmark" aria-label="Xem benchmark"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" /></svg></Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="lx-card lx-side" aria-label="Chi tiết benchmark">
          <div className="lx-card__head"><h2 className="lx-h2">Benchmark v1.2</h2><span className="lx-badge lx-badge--success">Đã khoá</span></div>
          <div className="lx-card__body lx-stack">
            <dl className="lx-kv">{BENCHMARK_DETAIL.map(([k, v]) => <React.Fragment key={k}><dt>{k}</dt><dd>{v}</dd></React.Fragment>)}</dl>
            <div className="lx-callout lx-callout--info"><span className="lx-callout__text lx-text-13">Benchmark đã khoá không thể sửa. Cần thay đổi thì tạo phiên bản mới.</span></div>
          </div>
        </section>
      </div>
    </>
  );
}
