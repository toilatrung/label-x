'use client';

import React, { useState } from 'react';
import type { components } from '@/lib/api/contract';
import { reviewBBox } from '@/lib/review/workspace-api';
import type { SnapshotAnnotation } from './ReviewCanvas';
import styles from './ReviewIssueAssessment.module.css';

type Issue = components['schemas']['Issue'];
type Frame = components['schemas']['FrameSummary'];
type BBox = components['schemas']['BBox'];

export function isUnmatchedAnnotation(issue: Issue): boolean {
  return String(issue.anchor.kind) === 'annotation_box' ||
    [issue.anchor.rule_id, ...(issue.rule_ids ?? [])].includes('faster-rcnn-unmatched-annotation');
}

export function assessmentText(issue: Issue, annotationClass?: string): string {
  const labels = [...new Set((issue.evidence ?? []).filter(ev => ev.engine === 'detector')
    .map(ev => ev.prediction_class?.trim()).filter((label): label is string => !!label))];
  if (issue.family === 'E2') {
    if (annotationClass && labels.length && labels.every(label => label === annotationClass)) {
      return `Annotation và detector đều là ${annotationClass}. Bằng chứng đang hiển thị chưa cho thấy sai khác về lớp. Kiểm tra vùng ảnh trước khi quyết định.`;
    }
    if (annotationClass && labels.length) {
      return `Annotation hiện tại là ${annotationClass}; detector đề xuất ${labels.join(', ')}. Hãy kiểm tra loại đối tượng trong vùng được đánh dấu.`;
    }
    return 'Cảnh báo nghi ngờ sai nhãn chưa có đủ thông tin để đối chiếu hai lớp. Cần xem ảnh và bằng chứng trước khi kết luận.';
  }
  if (issue.family === 'E1') return issue.origin === 'reviewer'
    ? 'Vùng này được reviewer đánh dấu là có thể thiếu annotation. Kiểm tra đối tượng và hướng dẫn trước khi quyết định.'
    : 'Detector phát hiện một vùng chưa ghép được với annotation. Kiểm tra xem đối tượng có cần được gán nhãn theo hướng dẫn hay không.';
  if (isUnmatchedAnnotation(issue)) return 'Annotation này chưa được detector ghép với một phát hiện tương ứng. Điều này chưa chứng minh annotation sai hoặc bị trùng.';
  if (issue.family === 'E3') return 'Các annotation được đánh dấu có thể trùng nhau. Kiểm tra xem chúng mô tả cùng một đối tượng hay hai đối tượng riêng biệt.';
  return 'Kiểm tra cảnh báo theo bằng chứng và quy tắc liên quan bên dưới. Hệ thống chưa thay đổi annotation.';
}

export function annotationForIssue(issue: Issue, annotations: SnapshotAnnotation[] = []) {
  return annotations.find(annotation => issue.anchor.objects.some(object => {
    const source = annotation.source;
    if (!source) return false;
    const namespace = source.kind === 'shape' ? 'cvat_shape' : source.kind === 'track' ? 'cvat_track' : source.kind;
    return [source.kind, namespace].includes(String(object.namespace)) && String(object.id) === String(source.id);
  }));
}

export function guidelineRuleForIssue(issue: Issue): string | undefined {
  return [...(issue.rule_ids ?? []), issue.anchor.rule_id].find(id => id &&
    !['faster-rcnn-detection', 'faster-rcnn-unmatched-annotation'].includes(id)) ?? undefined;
}

function rotatedBounds(box: BBox, rotation = 0): BBox {
  if (!Number.isFinite(rotation) || !rotation) return box;
  const radians = rotation * Math.PI / 180;
  const cx = (box.x1 + box.x2) / 2;
  const cy = (box.y1 + box.y2) / 2;
  const points = [[box.x1, box.y1], [box.x2, box.y1], [box.x2, box.y2], [box.x1, box.y2]].map(([x, y]) => [
    cx + (x - cx) * Math.cos(radians) - (y - cy) * Math.sin(radians),
    cy + (x - cx) * Math.sin(radians) + (y - cy) * Math.cos(radians),
  ]);
  return { x1: Math.min(...points.map(point => point[0])), y1: Math.min(...points.map(point => point[1])),
    x2: Math.max(...points.map(point => point[0])), y2: Math.max(...points.map(point => point[1])) };
}

function ComparisonCrop({ frame, box, region, title, color, rotation = 0 }: {
  frame: Frame; box: BBox | null; region: BBox; title: string; color: string; rotation?: number;
}) {
  const [failed, setFailed] = useState(false);
  if (!frame.image_url || failed) return <p className="lx-subtle">Không tải được ảnh đối chiếu. Xem ảnh chính hoặc mở trong CVAT.</p>;
  return <svg className={styles.crop} role="img" aria-label={title}
    viewBox={`${region.x1} ${region.y1} ${region.x2 - region.x1} ${region.y2 - region.y1}`}>
    <image href={frame.image_url} width={frame.width!} height={frame.height!} onError={() => setFailed(true)} />
    {box && <rect x={box.x1} y={box.y1} width={box.x2 - box.x1} height={box.y2 - box.y1}
      transform={`rotate(${Number.isFinite(rotation) ? rotation : 0} ${(box.x1 + box.x2) / 2} ${(box.y1 + box.y2) / 2})`}
      stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" fill="none" />}
  </svg>;
}

export function ReviewIssueAssessment({ issue, frame, annotation, comparisonAnnotation, currentAnnotationClass }: {
  issue: Issue; frame: Frame; annotation?: SnapshotAnnotation; comparisonAnnotation?: SnapshotAnnotation; currentAnnotationClass?: string;
}) {
  const [fullImage, setFullImage] = useState(false);
  const detectorEvidence = (issue.evidence ?? []).filter(ev => ev.engine === 'detector' && ev.prediction_class);
  const prediction = detectorEvidence[0];
  const annotationBox = reviewBBox(annotation?.bbox);
  const predictionBox = reviewBBox(comparisonAnnotation?.bbox ?? prediction?.prediction_bbox);
  const boxes = [annotationBox && rotatedBounds(annotationBox, annotation?.rotation),
    predictionBox && rotatedBounds(predictionBox, comparisonAnnotation?.rotation)].filter((box): box is BBox => !!box);
  const width = frame.width ?? 0;
  const height = frame.height ?? 0;
  const hasDimensions = Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0;
  let region: BBox | null = null;
  if (hasDimensions && boxes.length) {
    const x1 = Math.min(...boxes.map(box => box.x1));
    const y1 = Math.min(...boxes.map(box => box.y1));
    const x2 = Math.max(...boxes.map(box => box.x2));
    const y2 = Math.max(...boxes.map(box => box.y2));
    const pad = Math.max(x2 - x1, y2 - y1) * 0.15;
    region = fullImage ? { x1: 0, y1: 0, x2: width, y2: height }
      : { x1: Math.max(0, x1 - pad), y1: Math.max(0, y1 - pad), x2: Math.min(width, x2 + pad), y2: Math.min(height, y2 + pad) };
    if (region.x2 <= region.x1 || region.y2 <= region.y1) region = null;
  }
  const unavailable = (box: BBox | null, subject: string) => !box
    ? `Chưa có vùng ${subject} để đối chiếu.` : !hasDimensions
      ? 'Chưa có kích thước ảnh đã xác minh để hiển thị vùng đối chiếu.'
      : 'Vùng đối chiếu nằm ngoài ảnh hoặc không hợp lệ.';
  return <section className="lx-stack lx-gap-2" aria-label="Điểm cần kiểm tra và đối chiếu">
    <h2 className="lx-h2">Điểm cần kiểm tra</h2>
    <p className={styles.explanation}>{assessmentText(issue, currentAnnotationClass)}</p>
    <h3 className="lx-h2 lx-h2--sm">Đối chiếu bằng chứng</h3>
    <div className={styles.comparison}>
      <div className={styles.card}>
        <span className="lx-muted">Annotation hiện tại</span>
        <b>{currentAnnotationClass || 'Chưa có thông tin nhãn'}</b>
        {region && annotationBox ? <ComparisonCrop key={frame.image_url} frame={frame} box={annotationBox} region={region} title="Vùng annotation hiện tại" color="#f2c14e" rotation={annotation?.rotation} />
          : <p className="lx-subtle">{unavailable(annotationBox, 'annotation')}</p>}
      </div>
      <div className={styles.card}>
        <span className="lx-muted">{comparisonAnnotation ? 'Annotation cần đối chiếu' : 'Đề xuất detector'}</span>
        <b>{comparisonAnnotation?.label || prediction?.prediction_class || 'Chưa có đề xuất nhãn'}</b>
        {region && predictionBox ? <ComparisonCrop key={frame.image_url} frame={frame} box={predictionBox} region={region} title={comparisonAnnotation ? 'Vùng annotation cần đối chiếu' : 'Vùng detector đề xuất'} color="#16877e" rotation={comparisonAnnotation?.rotation} />
          : <p className="lx-subtle">{unavailable(predictionBox, 'detector')}</p>}
      </div>
    </div>
    {detectorEvidence.length > 1 && <p className="lx-subtle">Hiển thị cặp đầu tiên. Các bằng chứng detector còn lại nằm bên dưới.</p>}
    {region && frame.image_url && <button type="button" className="lx-btn lx-btn--xs" aria-pressed={fullImage} onClick={() => setFullImage(value => !value)}>
      {fullImage ? 'Xem cận cảnh đối tượng' : 'Xem ngữ cảnh toàn ảnh'}
    </button>}
  </section>;
}
