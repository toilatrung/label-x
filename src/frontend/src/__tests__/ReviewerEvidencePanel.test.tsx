import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import type { components } from '@/lib/api/contract';
import type { AiEvidence } from '@/lib/review/workspace-api';
import { ReviewIssueAssessment, assessmentText, annotationForIssue, guidelineRuleForIssue } from '@/components/review/ReviewIssueAssessment';
import { ReviewEvidenceTable } from '@/components/review/ReviewEvidenceTable';
import { ReviewCanvas, type SnapshotAnnotation } from '@/components/review/ReviewCanvas';

vi.mock('@/components/review/AiReEvaluate', () => ({ AiReEvaluate: () => <button>Đánh giá lại bằng AI</button> }));
type Issue = components['schemas']['Issue'];
const box = { x1: 20, y1: 30, x2: 100, y2: 90 };
const annotation: SnapshotAnnotation = { id: 'shape:8', source: { kind: 'shape', id: 8 }, label: 'car', bbox: box };
const issue: Issue = { id: 1, family: 'E2', origin: 'engine', state: 'in_review', n_i: 1,
  anchor: { kind: 'annotation', policy_version: 'anchor-v1', objects: [{ namespace: 'cvat_shape', id: '8' }], rule_id: 'faster-rcnn-detection' },
  evidence: [{ engine: 'detector', prediction_class: 'car', confidence: 1, iou: 0.96, prediction_bbox: box }], links: [], review_decisions: [] };
const frame: components['schemas']['FrameSummary'] = { id: 1, run_id: 1, frame_key: { cvat_task_id: 4, frame_number: 7 },
  image_url: 'https://storage.test/frame.jpg', width: 200, height: 100, review_state: 'in_review', missing_evidence: false };
const ai: AiEvidence = { issue_id: 1, candidate_id: 1, evaluation_id: 1, generation: 1, evaluation_source: 'automatic',
  status: 'completed', source: 'qwen', reason_code: 'label_conflict', reasons: [], review_required: true,
  suggestion: { status: 'checked', class_name: 'truck', rationale: 'OLD RESULT' }, evidence_refs: null, snapshot_revision: 'rev', poll_url: '' };

describe('Reviewer evidence panel', () => {
  it('explains matching classes without turning the stored E2 into a confirmed error', () => {
    render(<ReviewIssueAssessment issue={issue} frame={frame} annotation={annotation} currentAnnotationClass="car" />);
    expect(screen.getByText(/Annotation và detector đều là car/)).toBeInTheDocument();
    const left = screen.getByRole('img', { name: 'Vùng annotation hiện tại' });
    const right = screen.getByRole('img', { name: 'Vùng detector đề xuất' });
    expect(left.getAttribute('viewBox')).toBe(right.getAttribute('viewBox'));
    fireEvent.click(screen.getByRole('button', { name: 'Xem ngữ cảnh toàn ảnh' }));
    expect(left).toHaveAttribute('viewBox', '0 0 200 100');
    fireEvent.click(screen.getByRole('button', { name: 'Xem cận cảnh đối tượng' }));
    expect(left.getAttribute('viewBox')).not.toBe('0 0 200 100');
  });

  it('describes the actual competing labels and does not invent missing evidence', () => {
    expect(assessmentText({ ...issue, evidence: [{ engine: 'detector', prediction_class: 'bus' }] }, 'car'))
      .toContain('car; detector đề xuất bus');
    expect(assessmentText({ ...issue, evidence: [] }, 'car')).toContain('chưa có đủ thông tin');
    render(<ReviewIssueAssessment issue={{ ...issue, evidence: [] }} frame={{ ...frame, width: undefined }} currentAnnotationClass="car" />);
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByText('Chưa có đề xuất nhãn')).toBeInTheDocument();
  });

  it('does not describe an unmatched annotation as a proven duplicate', () => {
    const unmatched = { ...issue, family: 'E3' as const, anchor: { ...issue.anchor, rule_id: 'faster-rcnn-unmatched-annotation' } };
    expect(assessmentText(unmatched, 'car')).toContain('chưa chứng minh annotation sai hoặc bị trùng');
    expect(guidelineRuleForIssue(unmatched)).toBeUndefined();
    expect(guidelineRuleForIssue({ ...issue, rule_ids: ['faster-rcnn-detection', 'GUIDE-CAR-01'] })).toBe('GUIDE-CAR-01');
  });

  it('compares two annotations for duplicate warnings', () => {
    render(<ReviewIssueAssessment issue={{ ...issue, family: 'E3' }} frame={frame} annotation={annotation}
      comparisonAnnotation={{ ...annotation, id: 'shape:9' }} currentAnnotationClass="car" />);
    expect(screen.getByRole('img', { name: 'Vùng annotation cần đối chiếu' })).toBeInTheDocument();
  });

  it('preserves annotation rotation and reports image failures without a fabricated crop', () => {
    render(<ReviewIssueAssessment issue={issue} frame={frame} annotation={{ ...annotation, rotation: 30 }} currentAnnotationClass="car" />);
    const crop = screen.getByRole('img', { name: 'Vùng annotation hiện tại' });
    expect(crop.querySelector('rect')).toHaveAttribute('transform', 'rotate(30 60 60)');
    fireEvent.error(crop.querySelector('image')!);
    expect(screen.queryByRole('img', { name: 'Vùng annotation hiện tại' })).toBeNull();
    expect(screen.getByText(/Không tải được ảnh đối chiếu/)).toBeInTheDocument();
  });

  it('does not draw boxes with unknown dimensions or invent an image source', () => {
    const { rerender } = render(<ReviewIssueAssessment issue={issue} frame={{ ...frame, width: 0 }} annotation={annotation} />);
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getAllByText(/Chưa có kích thước ảnh đã xác minh/)).toHaveLength(2);
    rerender(<ReviewIssueAssessment issue={issue} frame={{ ...frame, image_url: undefined }} annotation={annotation} />);
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Xem ngữ cảnh toàn ảnh' })).toBeNull();
  });

  it('resolves source namespaces and never treats a detector ID as a CVAT annotation', () => {
    expect(annotationForIssue(issue, [annotation])).toEqual(annotation);
    expect(annotationForIssue({ ...issue, anchor: { ...issue.anchor, objects: [{ namespace: 'detector', id: '8' }] } }, [annotation])).toBeUndefined();
  });

  it('shows only the latest AI assessment and hides a stale suggestion after cancellation', () => {
    render(<ReviewEvidenceTable evidenceList={[]} currentAnnotationClass="car"
      aiEvidence={[ai, { ...ai, evaluation_id: 2, generation: 2, status: 'cancelled' }]} canReEvaluate />);
    expect(screen.getByText('Đã hủy đánh giá')).toBeInTheDocument();
    expect(screen.queryByText('Đề xuất: truck')).toBeNull();
    expect(screen.queryByText('OLD RESULT')).toBeNull();
    expect(screen.getAllByRole('button', { name: 'Đánh giá lại bằng AI' })).toHaveLength(1);
    expect(screen.getByText('Chưa có bằng chứng AI cho lần đánh giá này.')).toBeInTheDocument();
  });

  it('explains percentages including zero, and scopes engine status to the whole image', () => {
    render(<ReviewEvidenceTable evidenceList={[{ engine: 'detector', confidence: 0, iou: 0.96 }]}
      engineStatuses={[{ engine: 'vlm', status: 'not_checked', reason: 'disabled' }]} />);
    expect(screen.getByText('0%')).toBeInTheDocument();
    expect(screen.getByText('96%')).toBeInTheDocument();
    expect(screen.getByText(/không phải xác suất cảnh báo đúng/)).toBeInTheDocument();
    expect(screen.getByText('Chưa có đánh giá AI cho cảnh báo này.')).toBeInTheDocument();
    expect(screen.getByText('Trạng thái phân tích toàn ảnh').closest('details')).not.toHaveAttribute('open');
  });

  it('does not claim an absent classifier suggestion is sufficiently confident', () => {
    render(<ReviewEvidenceTable evidenceList={[]} aiEvidence={[{ ...ai, source: 'classifier', suggestion: null, reason_code: 'unknown' }]} />);
    expect(screen.getByText('Chưa có đề xuất nhãn để đối chiếu.')).toBeInTheDocument();
    expect(screen.queryByText(/đủ tin cậy/)).toBeNull();
  });

  it('dims unrelated boxes and highlights matching prediction evidence even without an issue link', () => {
    const { container } = render(<ReviewCanvas frame={frame} issues={[issue]} selectedIssueId={1} onSelectIssue={vi.fn()}
      reviewMode="issue" showAnnotations showPredictions zoom={1} pan={{ x: 0, y: 0 }} onZoomChange={vi.fn()} onPanChange={vi.fn()}
      snapshotAnnotations={[annotation, { ...annotation, id: 'shape:9', source: { kind: 'shape', id: 9 } }]}
      predictions={[{ id: 'p1', issueId: null, bbox: box, label: 'car', source: 'detector' },
        { id: 'p2', issueId: null, bbox: { ...box, x1: 10 }, label: 'bus', source: 'detector' }]} />);
    expect(container.querySelector('[data-annotation-id="shape:8"]')).toHaveAttribute('opacity', '1');
    expect(container.querySelector('[data-annotation-id="shape:9"]')).toHaveAttribute('opacity', '0.16');
    const predictions = container.querySelectorAll('[data-prediction-source]');
    expect(predictions[0]).toHaveAttribute('opacity', '1');
    expect(predictions[1]).toHaveAttribute('opacity', '0.12');
  });
});
