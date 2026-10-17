'use client';

import React, { useState } from 'react';
import { MODEL_ROWS, REVIEWER_ROWS } from '@/lib/calibration/sample-data';

type Tab = 'reviewer' | 'model';
const TABS: ReadonlyArray<[Tab, string]> = [['reviewer', 'Hiệu chỉnh reviewer'], ['model', 'Hiệu chỉnh mô hình']];
const DASH = <span className="lx-subtle">—</span>;

export function CalibrationHeader() {
  return (
    <div className="lx-head">
      <div className="lx-head__text">
        <h1 className="lx-h1">Calibration</h1>
        <p className="lx-lead">Hiệu chỉnh reviewer và hiệu chỉnh mô hình là hai việc riêng, có tập dữ liệu, metric và cách điều chỉnh khác nhau. Không trộn hai loại này.</p>
      </div>
      <div className="lx-actions">
        {/* TODO(backend): POST /api/calibration/assignments/ (chặn, không gọi API giả) */}
        <button type="button" className="lx-btn lx-btn--primary">Giao bài hiệu chỉnh</button>
      </div>
    </div>
  );
}

export function CalibrationBody() {
  const [tab, setTab] = useState<Tab>('reviewer');
  return (
    <>
      {/* TODO(backend): GET /api/calibration/reviewers/ ; GET /api/calibration/models/ */}
      <section className="lx-card" aria-label="Hiệu chỉnh">
        <div className="lx-tabs lx-tabs--inset" role="tablist">
          {TABS.map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={tab === key} className={`lx-tab${tab === key ? ' is-active' : ''}`} onClick={() => setTab(key)}>{label}</button>)}
        </div>
        {tab === 'reviewer' && (
          <>
            <div className="lx-scroll">
              <table className="lx-table lx-table--min-760">
                <thead><tr><th>Reviewer</th><th className="r">Thống nhất với adjudicator</th><th className="r">Bỏ sót lỗi nghiêm trọng</th><th className="r">Cảnh báo sai</th><th>Bài hiệu chỉnh gần nhất</th></tr></thead>
                <tbody>{REVIEWER_ROWS.map((r) => <tr key={r.name}><td className="lx-cell__main">{r.name}</td><td className="r">{r.agree}</td><td className={r.missedWarn ? 'r is-warn' : 'r'}>{r.missed}</td><td className="r">{r.falseAlarm}</td><td className="lx-muted">{r.last}</td></tr>)}</tbody>
              </table>
            </div>
            <div className="lx-card__foot"><span>Reviewer không nhìn thấy đáp án chuẩn khi làm bài. Kết quả được phân tích theo loại issue và độ khó.</span></div>
          </>
        )}
        {tab === 'model' && (
          <>
            <div className="lx-scroll">
              <table className="lx-table lx-table--min-760">
                <thead><tr><th>Lớp</th><th className="r">Ngưỡng tin cậy</th><th className="r">Precision</th><th className="r">Recall</th><th>Trạng thái đánh giá</th></tr></thead>
                <tbody>
                  {MODEL_ROWS.map((m) => (
                    <tr key={m.name}>
                      <td className="lx-cell__main">{m.name}</td><td className="r">{m.threshold}</td>
                      <td className={m.warn ? 'r is-warn' : 'r'}>{m.precision ?? DASH}</td><td className="r">{m.recall ?? DASH}</td>
                      <td><span className={`lx-badge lx-badge--${m.status.tone}`}>{m.status.label}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="lx-card__foot"><span>Precision và recall chỉ tính khi có Ground Truth đúng phạm vi. Mức đồng thuận giữa mô hình và annotator không thay cho độ chính xác.</span></div>
          </>
        )}
      </section>
    </>
  );
}
