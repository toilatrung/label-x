import React from 'react';
import { ACTIVE_CALIBRATIONS, PERF_BENCHMARKS, PERF_METRICS, PERF_SCOPES, SAMPLING_STREAMS } from '@/lib/calibration/sample-data';
import Link from 'next/link';

export function PerformanceHeader() {
  return (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Performance Evaluation</h1>
        <p className="lx-lead">Đánh giá chất lượng của chính quy trình kiểm tra: mức thống nhất của reviewer, độ chính xác của candidate và lỗi còn sót. Luôn ghi kèm cỡ mẫu và phương pháp.</p>
      </div>
      <div className="lx-actions">
        <select className="lx-select lx-select--inline" aria-label="Phạm vi đánh giá" disabled>{PERF_SCOPES.map((s) => <option key={s}>{s}</option>)}</select>
        <select className="lx-select lx-select--inline" aria-label="Benchmark" disabled>{PERF_BENCHMARKS.map((s) => <option key={s}>{s}</option>)}</select>
      </div>
    </div>
  );
}

export function PerformanceBody() {
  return (
    <>
      {/* TODO(backend): GET /api/evaluation/performance/ */}
      <div className="lx-grid lx-grid--4">
        {PERF_METRICS.map((m) => (
          <div key={m.key} className="lx-metric">
            <span className="lx-metric__k">{m.label}</span>
            <span className={`lx-metric__v${m.tone ? ` ${m.tone}` : ''}`}>{m.value}</span>
            {m.progress !== null && <div className="lx-progress lx-progress--warn" role="img" aria-label={`${m.progress}%`}><i style={{ width: `${m.progress}%` }} /></div>}
            <span className="lx-metric__n">{m.note}</span>
          </div>
        ))}
      </div>
      <div className="lx-cols">
        <section className="lx-card lx-main" aria-label="Kết quả theo luồng lấy mẫu">
          <div className="lx-card__head"><h2 className="lx-h2">Kết quả theo luồng lấy mẫu</h2></div>
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-520">
              <thead><tr><th>Luồng lấy mẫu</th><th className="r">Số mẫu</th><th className="r">Lỗi đã xác nhận</th><th className="r">Tỷ lệ</th><th>Dùng để</th></tr></thead>
              <tbody>{SAMPLING_STREAMS.map((s) => <tr key={s.name}><td className="lx-cell__main">{s.name}</td><td className="r">{s.n}</td><td className="r">{s.errors}</td><td className="r">{s.rate}</td><td className="lx-muted">{s.use}</td></tr>)}</tbody>
            </table>
          </div>
          <div className="lx-card__foot"><span>Hai luồng ngẫu nhiên và theo rủi ro được báo cáo riêng, không gộp.</span></div>
        </section>
        <section className="lx-card lx-side" aria-label="Việc hiệu chỉnh đang chạy">
          <div className="lx-card__head"><h2 className="lx-h2">Việc hiệu chỉnh đang chạy</h2><Link className="lx-link lx-text-13" href="/calibration/calibration">Mở Calibration</Link></div>
          <ul className="lx-list">
            {ACTIVE_CALIBRATIONS.map((a) => (
              <li key={a.name}>
                {a.progress ? (
                  <>
                    <div className="lx-row lx-row--between"><span className="lx-cell__main">{a.name}</span><span className="lx-num">{a.progress.label}</span></div>
                    <div className="lx-progress lx-mt-6"><i style={{ width: `${a.progress.pct}%` }} /></div>
                  </>
                ) : (
                  <><div className="lx-cell__main">{a.name}</div><div className="lx-cell__sub">{a.sub}</div></>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
