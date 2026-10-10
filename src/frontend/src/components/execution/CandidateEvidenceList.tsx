'use client';

import React from 'react';
import type { components } from '@/lib/api/contract';

export type Candidate = components['schemas']['Candidate'];

export interface CandidateEvidenceListProps {
  candidates?: Candidate[] | null;
  rawCount?: number | null;
  dedupCount?: number | null;
  isLoading?: boolean;
  error?: string | null;
}

export function CandidateEvidenceList({
  candidates,
  rawCount,
  dedupCount,
  isLoading = false,
  error = null,
}: CandidateEvidenceListProps) {
  const hasDedup = dedupCount !== undefined && dedupCount !== null;
  const hasRaw = rawCount !== undefined && rawCount !== null;

  return (
    <section className="lx-card" aria-label="Danh sách Candidate và Evidence">
      <header className="lx-card__head">
        <div>
          <span className="lx-cell__main">Candidate nghi vấn & Evidence</span>
        </div>
        <span className="lx-subtle">Chỉ đọc · Lineage theo run</span>
      </header>

      <div className="lx-card__body lx-stack" style={{ gap: 12 }}>
        {hasDedup && (
          <div className="lx-callout lx-callout--info">
            <span className="lx-callout__text" style={{ fontSize: '13px' }}>
              {hasRaw
                ? `Candidate: ${rawCount} bản ghi thô → ${dedupCount} sau khi gộp trùng.`
                : `Candidate: ${dedupCount} sau khi gộp trùng.`}
            </span>
          </div>
        )}

        {error ? (
          <div className="lx-callout" role="alert">
            <strong>Không tải được danh sách candidate</strong>
            <div>{error}</div>
          </div>
        ) : isLoading ? (
          <div className="lx-scroll">
            <table className="lx-table">
              <tbody>
                <tr>
                  <td className="c lx-subtle" colSpan={6}>
                    Đang tải candidate và evidence…
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        ) : candidates === undefined || candidates === null ? (
          <div className="lx-callout lx-callout--neutral" role="status">
            <strong>Chưa có dữ liệu candidate</strong>
            <div>
              Chưa có dữ liệu candidate từ backend cho lần chạy này.
            </div>
          </div>
        ) : candidates.length === 0 ? (
          <div className="lx-callout lx-callout--neutral" role="status">
            <strong>Chưa có candidate nghi vấn</strong>
            <div>
              Chưa có candidate nghi vấn nào cho lần chạy này (không tự động xem là đạt kết quả).
            </div>
          </div>
        ) : (
          <div className="lx-scroll">
            <table className="lx-table">
              <thead>
                <tr>
                  <th style={{ width: '80px' }}>Engine</th>
                  <th style={{ width: '130px' }}>Frame</th>
                  <th style={{ width: '90px' }}>Nhóm lỗi</th>
                  <th style={{ width: '120px' }}>Neo (Anchor)</th>
                  <th>Evidence (Bằng chứng)</th>
                  <th style={{ width: '90px' }}>Mức độ</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((cand, idx) => {
                  const ev = cand.evidence || {};
                  return (
                    <tr key={`${cand.engine}-${cand.frame.cvat_task_id}-${cand.frame.frame_number}-${idx}`}>
                      <td>
                        <span className="lx-badge lx-badge--info">{cand.engine}</span>
                        <div className="lx-cell__sub lx-mono">v{cand.engine_version}</div>
                      </td>
                      <td>
                        <div className="lx-mono">
                          Task #{cand.frame.cvat_task_id}
                        </div>
                        <div className="lx-cell__sub lx-mono">
                          Frame #{cand.frame.frame_number}
                        </div>
                      </td>
                      <td>
                        <span className="lx-mono">{cand.family}</span>
                      </td>
                      <td>
                        <div className="lx-cell__main">{cand.anchor.kind}</div>
                        {cand.anchor.rule_id && (
                          <div className="lx-cell__sub lx-mono">Rule: {cand.anchor.rule_id}</div>
                        )}
                      </td>
                      <td>
                        <div className="lx-stack" style={{ gap: 4 }}>
                          {ev.rule_id && (
                            <div>
                              <strong>Quy tắc: </strong>
                              <span className="lx-mono">{ev.rule_id}</span>
                            </div>
                          )}
                          {ev.prediction_class && (
                            <div>
                              <strong>Lớp dự đoán: </strong>
                              <span className="lx-mono">{ev.prediction_class}</span>
                            </div>
                          )}

                          {ev.prediction_bbox && (
                            <div>
                              <strong>BBox dự đoán: </strong>
                              <span className="lx-mono">
                                [{ev.prediction_bbox.x1}, {ev.prediction_bbox.y1}, {ev.prediction_bbox.x2}, {ev.prediction_bbox.y2}]
                              </span>
                            </div>
                          )}
                          {ev.iou !== undefined && ev.iou !== null && (
                            <div>
                              <strong>IoU: </strong>
                              <span className="lx-mono">{(ev.iou as number).toFixed(4)}</span>
                            </div>
                          )}
                          {ev.expected && (
                            <div>
                              <strong>Kỳ vọng: </strong>
                              <span>{ev.expected}</span>
                            </div>
                          )}
                          {ev.actual && (
                            <div>
                              <strong>Thực tế: </strong>
                              <span>{ev.actual}</span>
                            </div>
                          )}
                          {ev.confidence !== undefined && ev.confidence !== null && (
                            <div>
                              <strong>Độ tin cậy: </strong>
                              <span className="lx-mono">{(ev.confidence as number).toFixed(2)}</span>
                            </div>
                          )}
                        </div>
                      </td>
                      <td>
                        {cand.severity ? (
                          <span className="lx-badge">{cand.severity}</span>
                        ) : (
                          <span className="lx-subtle">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <footer className="lx-card__foot">
        <span>
          Candidate là nghi vấn do engine sinh ra, mang tính bất biến sau khi ghi (FR-AGG-01). Mọi quyết định xác nhận lỗi thuộc về Reviewer tại Review Center.
        </span>
      </footer>
    </section>
  );
}
