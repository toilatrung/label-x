'use client';

import React from 'react';
import type { components } from '@/lib/api/contract';
import type { AiEvidence } from '@/lib/review/workspace-api';
import { AiReEvaluate } from './AiReEvaluate';

type Evidence = components['schemas']['Evidence'];
type EngineRunStatus = components['schemas']['EngineRunStatus'];

export interface ReviewEvidenceTableProps {
  onEvaluationUpdated?: () => void;
  evidenceList: Evidence[];
  engineStatuses?: EngineRunStatus[];
  currentAnnotationClass?: string;
  /** Evidence AI (classifier/Qwen) của issue từ GET /api/frames/{id}/workspace/ (MBE-01). */
  aiEvidence?: AiEvidence[];
  /** Reviewer, QA Lead, QC Admin, Super Admin trong phạm vi Dataset được đánh giá lại candidate bằng AI. */
  canReEvaluate?: boolean;
}

const AI_SOURCE_LABELS: Record<string, string> = {
  qwen: 'Mô hình thị giác – ngôn ngữ (VLM)',
  classifier: 'Đối chiếu detector',
  detector: 'Đối chiếu detector',
};

const AI_STATUS: Record<string, { label: string; note: string }> = {
  pending: { label: 'Đang chờ', note: 'Chưa có kết quả đánh giá.' },
  running: { label: 'Đang đánh giá', note: 'Chưa có kết quả để đối chiếu.' },
  failed: { label: 'Đánh giá thất bại', note: 'Chưa có bằng chứng AI cho lần đánh giá này.' },
  cancelled: { label: 'Đã hủy đánh giá', note: 'Chưa có bằng chứng AI cho lần đánh giá này.' },
};

const REASONS: Record<string, string> = {
  label_conflict: 'Nhãn annotation và dự đoán cần được đối chiếu.',
  detector_no_match: 'Detector chưa ghép được vùng phát hiện với annotation.',
  classifier_confident: 'Kết quả detector đạt ngưỡng cấu hình; hệ thống không yêu cầu VLM.',
  low_score: 'Độ tin cậy detector thấp hơn ngưỡng cấu hình.',
  unknown: 'Mô hình chưa nhận diện được lớp phù hợp.',
  classifier_unavailable: 'Chưa có kết quả detector dùng để đối chiếu.',
  classifier_untrusted: 'Nguồn kết quả detector chưa được xác minh.',
  manual_recheck: 'Reviewer yêu cầu đánh giá lại.',
  budget_exhausted: 'Đã hết ngân sách đánh giá AI của lần chạy.',
  no_reference: 'Không có dữ liệu tham chiếu để đo lường.',
  disabled: 'Không được bật trong cấu hình phân tích.',
};

function AiEvidenceCell({ item, annotationClass }: { item: AiEvidence; annotationClass?: string }) {
  const state = AI_STATUS[item.status];
  const checkedLabel = item.status === 'completed' && item.suggestion?.status === 'checked'
    ? item.suggestion.class_name : null;
  return <div className="lx-stack lx-gap-1">
    {state ? <><b>{state.label}</b><span className="lx-subtle">{state.note}</span></>
      : checkedLabel ? <><b>Đề xuất: {checkedLabel}</b>
        {annotationClass && <span>{checkedLabel === annotationClass ? 'Cùng lớp với annotation hiện tại.' : `Khác lớp annotation hiện tại (${annotationClass}).`}</span>}
      </> : <span>Chưa có đề xuất nhãn để đối chiếu.</span>}
    {item.status === 'completed' && item.suggestion?.rationale && <p>{item.suggestion.rationale}</p>}
    {item.reason_code && REASONS[item.reason_code] && <span className="lx-subtle">{REASONS[item.reason_code]}</span>}
    {item.review_required && <span className="lx-badge lx-badge--warning">Cần reviewer quyết định</span>}
    <details><summary>Chi tiết lần đánh giá</summary>
      <span className="lx-mono">{item.reason_code || item.status} · #{item.evaluation_id}</span>
    </details>
  </div>;
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
  aiEvidence = [],
  canReEvaluate = false,
  onEvaluationUpdated,
}: ReviewEvidenceTableProps) {
  // A frame-level engine status is separate from the latest assessment of this issue.
  const latest = new Map<string, AiEvidence>();
  for (const item of aiEvidence) {
    const source = item.source === 'vlm' ? 'qwen' : item.source;
    const previous = latest.get(source);
    if (!previous || item.generation > previous.generation ||
      (item.generation === previous.generation && item.evaluation_id > previous.evaluation_id)) latest.set(source, item);
  }
  const reevaluationTargets = new Map<number, AiEvidence>();
  for (const item of latest.values()) {
    if (item.snapshot_revision) reevaluationTargets.set(item.candidate_id, item);
  }
  const percent = (value: number | null | undefined) => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
    ? `${Math.round(value * 100)}%` : null;
  return <div className="lx-stack lx-gap-2">
    <h3 className="lx-h2 lx-h2--sm lx-m-0">Bằng chứng mô hình</h3>
    {evidenceList.map((ev, index) => <div key={index} className="lx-stack lx-gap-1">
      <b>{ENGINE_LABELS[ev.engine] || ev.engine}{ev.prediction_class ? ` · ${ev.prediction_class}` : ''}</b>
      {percent(ev.confidence) && <span>Độ tin cậy nhận diện lớp: <b>{percent(ev.confidence)}</b>.</span>}
      {percent(ev.iou) && <span>Mức khớp vị trí hai vùng: <b>{percent(ev.iou)}</b>.</span>}
      {(percent(ev.confidence) || percent(ev.iou)) && <span className="lx-subtle">Các chỉ số này không phải xác suất cảnh báo đúng.</span>}
      {(ev.expected || ev.actual) && <span>{ev.expected && <>Kỳ vọng: <b>{ev.expected}</b> </>}{ev.actual && <>Thực tế: <b>{ev.actual}</b></>}</span>}
      <details><summary>Chi tiết kỹ thuật bằng chứng {index + 1}</summary>
        {typeof ev.confidence === 'number' && Number.isFinite(ev.confidence) && <div>độ tin cậy {ev.confidence.toFixed(2)}</div>}
        {typeof ev.iou === 'number' && Number.isFinite(ev.iou) && <div>Intersection over Union (IoU) {ev.iou.toFixed(2)}</div>}
        {ev.rule_id && <div>Quy tắc: {ev.rule_id}</div>}
        {ev.prediction_bbox && <div className="lx-mono">Prediction bbox: [{ev.prediction_bbox.x1}, {ev.prediction_bbox.y1}, {ev.prediction_bbox.x2}, {ev.prediction_bbox.y2}]</div>}
      </details>
    </div>)}
    {!evidenceList.length && <p className="lx-subtle">Chưa có bằng chứng mô hình cho cảnh báo này.</p>}
    <h3 className="lx-h2 lx-h2--sm">Đánh giá AI của cảnh báo</h3>
    {!latest.size && <p className="lx-subtle">Chưa có đánh giá AI cho cảnh báo này.</p>}
    {[...latest.entries()].map(([source, item]) => <div key={source} className="lx-stack lx-gap-2">
      <b>{AI_SOURCE_LABELS[source] ?? source}</b>
      <AiEvidenceCell item={item} annotationClass={currentAnnotationClass} />
    </div>)}
    {canReEvaluate && [...reevaluationTargets.values()].map(item => <AiReEvaluate key={item.candidate_id}
      candidateId={item.candidate_id} expectedRevision={item.snapshot_revision} onEvaluationUpdated={onEvaluationUpdated} />)}
    {!!engineStatuses.length && <details>
      <summary>Trạng thái phân tích toàn ảnh</summary>
      <p className="lx-subtle">Trạng thái này áp dụng cho toàn ảnh; không phải kết luận cho cảnh báo đang chọn.</p>
      {engineStatuses.map((engine, index) => <p key={index}>
        <b>{ENGINE_LABELS[engine.engine] || engine.engine}</b>: {engine.status === 'checked' ? 'Đã phân tích'
          : engine.status === 'failed' ? 'Phân tích thất bại' : 'Chưa phân tích'}
        {engine.failed_units !== undefined && engine.failed_units > 0 && ` · ${engine.failed_units} đơn vị lỗi`}
        {engine.reason && <span> · {REASONS[engine.reason] || 'Chưa có diễn giải lý do.'} <code>{engine.reason}</code></span>}
      </p>)}
    </details>}
  </div>;
}
