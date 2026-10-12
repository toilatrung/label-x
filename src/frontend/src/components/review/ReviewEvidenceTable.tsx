'use client';

import React from 'react';
import type { components } from '@/lib/api/contract';

type Evidence = components['schemas']['Evidence'];
type EngineRunStatus = components['schemas']['EngineRunStatus'];

export interface ReviewEvidenceTableProps {
  evidenceList: Evidence[];
  engineStatuses?: EngineRunStatus[];
  currentAnnotationClass?: string;
}

const ENGINE_LABELS: Record<string, string> = {
  detector: 'Mô hình phát hiện (detector)',
  vlm: 'Mô hình thị giác – ngôn ngữ (VLM)',
  schema: 'Kiểm tra schema',
  geometry: 'Kiểm tra hình học',
  duplicate: 'Kiểm tra trùng lặp',
  metric: 'Đo lường / Thống kê',
};

export function ReviewEvidenceTable({
  evidenceList,
  engineStatuses = [],
  currentAnnotationClass,
}: ReviewEvidenceTableProps) {
  return (
    <div className="lx-stack lx-gap-2">
      <h3 className="lx-h2 lx-h2--sm lx-m-0">
        Bằng chứng
      </h3>
      <table className="lx-table lx-text-12">
        <tbody>
          <tr>
            <td className="lx-muted lx-w-130">
              Annotation class
            </td>
            <td>
              {currentAnnotationClass ? (
                <b>{currentAnnotationClass}</b>
              ) : (
                <span className="lx-subtle">Không khả dụng (T-035 chưa serialize class nhãn ở top-level)</span>
              )}
            </td>
          </tr>

          {evidenceList.map((ev, idx) => {
            const hasConfidence = ev.confidence !== null && ev.confidence !== undefined && Number.isFinite(ev.confidence);
            const hasIou = ev.iou !== null && ev.iou !== undefined && Number.isFinite(ev.iou);
            const engineLabel = ENGINE_LABELS[ev.engine] || ev.engine;
            const pBBox = ev.prediction_bbox;

            return (
              <tr key={`ev-${idx}`}>
                <td className="lx-muted lx-w-130">
                  {engineLabel}
                </td>
                <td>
                  <div className="lx-stack lx-gap-1">
                    <div className="lx-row lx-gap-2 lx-items-center">
                      {ev.prediction_class && <b>{ev.prediction_class}</b>}
                      {hasConfidence && (
                        <span className="lx-subtle">
                          · độ tin cậy {ev.confidence!.toFixed(2)}
                        </span>
                      )}
                      {hasIou && (
                        <span className="lx-subtle">
                          · IoU {ev.iou!.toFixed(2)}
                        </span>
                      )}
                      {ev.rule_id && (
                        <span className="lx-tag lx-text-11">
                          Rule: {ev.rule_id}
                        </span>
                      )}
                    </div>

                    {pBBox && (
                      <div className="lx-subtle lx-mono lx-text-11">
                        Prediction bbox: [{pBBox.x1}, {pBBox.y1}, {pBBox.x2}, {pBBox.y2}]
                      </div>
                    )}

                    {(ev.expected || ev.actual) && (
                      <div className="lx-subtle lx-text-11">
                        {ev.expected && <span>Kỳ vọng: <b>{ev.expected}</b> </span>}
                        {ev.actual && <span>{ev.expected ? '· ' : ''}Thực tế: <b>{ev.actual}</b></span>}
                      </div>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}

          {/* Engine failed or not_checked rows */}
          {engineStatuses.map((eng, idx) => {
            if (eng.status === 'checked') return null;

            const engineTitle = ENGINE_LABELS[eng.engine] || eng.engine;

            return (
              <tr key={`eng-${idx}`}>
                <td className="lx-muted lx-w-130">
                  {engineTitle}
                </td>
                <td>
                  {eng.status === 'failed' ? (
                    <span className="lx-row lx-gap-2">
                      <span className="lx-badge lx-badge--danger">Failed</span>
                      <span className="lx-subtle">
                        {eng.failed_units !== undefined ? `${eng.failed_units} đơn vị lỗi` : 'lỗi thực thi'}
                      </span>
                    </span>
                  ) : eng.status === 'not_checked' ? (
                    <span className="lx-row lx-gap-2">
                      <span className="lx-badge lx-badge--warning">Not checked</span>
                      <span className="lx-subtle">
                        {eng.reason || 'chưa kiểm tra theo cấu hình'}
                      </span>
                    </span>
                  ) : (
                    <span className="lx-subtle">{eng.status}</span>
                  )}
                </td>
              </tr>
            );
          })}

          {evidenceList.length === 0 && engineStatuses.length === 0 && (
            <tr>
              <td colSpan={2} className="lx-muted lx-state--center-sm">
                Không có bằng chứng tự động cho issue này.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
