import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { components } from '@/lib/api/contract';
import { ReviewCanvas, type SnapshotAnnotation } from '@/components/review/ReviewCanvas';
import { ReviewIssueAssessment, annotationForIssue } from '@/components/review/ReviewIssueAssessment';
import { resolveIssueFocus } from '@/lib/review/issue-focus';

type Issue = components['schemas']['Issue'];
const annotations: SnapshotAnnotation[] = [9090, 9142, 9091, 9143].map((id, index) => ({
  id: `shape:${id}`, source: { kind: 'shape', id }, label: 'car',
  bbox: { x1: 10 + index * 50, y1: 20, x2: 40 + index * 50, y2: 80 },
}));
const issue = (id: number, ids: number[]): Issue => ({ id, family: 'E3', origin: 'engine', state: 'pending_review', n_i: 1,
  anchor: { kind: 'annotation_cluster', policy_version: '1.0.0', objects: ids.map(id => ({ namespace: 'cvat_shape', id: `shape:${id}` })) },
  evidence: [{ engine: 'duplicate', iou: 0.883964 }], links: [], review_decisions: [] });
const issues = [issue(57, [9090, 9142]), issue(58, [9091, 9143])];
const frame: components['schemas']['FrameSummary'] = { id: 4, run_id: 6, frame_key: { cvat_task_id: 13, frame_number: 4 },
  width: 1280, height: 720, image_url: '/snapshot.jpg', review_state: 'in_review', missing_evidence: true };
const props = { frame, issues, snapshotAnnotations: annotations, predictions: [], selectedIssueId: 57, onSelectIssue: vi.fn(),
  reviewMode: 'issue' as const, showAnnotations: true, showPredictions: false,
  zoom: 1, pan: { x: 0, y: 0 }, onZoomChange: vi.fn(), onPanChange: vi.fn() };

describe('Issue Review snapshot focus', () => {
  it('resolves both typed and canonical E3 references with detector disabled', () => {
    expect(resolveIssueFocus(issues[0], annotations).regions).toHaveLength(2);
    const canonical = { ...issues[0], anchor: { ...issues[0].anchor, objects: [{ namespace: 'cvat_shape' as const, id: '9090' }, { namespace: 'cvat_shape' as const, id: '9142' }] } };
    expect(resolveIssueFocus(canonical, annotations).annotations.map(a => a.id)).toEqual(['shape:9090', 'shape:9142']);
    const { container } = render(<ReviewCanvas {...props} />);
    expect(screen.getByTestId('issue-focus-image')).toBeInTheDocument();
    expect(container.querySelectorAll('clipPath[id$="-focus"] rect')).toHaveLength(2);
    expect(container.querySelector('[data-annotation-id="shape:9090"] rect')).toHaveAttribute('stroke', '#f2c14e');
    expect(container.querySelector('[data-annotation-id="shape:9142"] rect')).toHaveAttribute('stroke', '#f2c14e');
    render(<ReviewIssueAssessment issue={issues[0]} frame={frame} annotation={annotationForIssue(issues[0], annotations)}
      comparisonAnnotation={annotations[1]} currentAnnotationClass="car" />);
    expect(screen.getByRole('img', { name: 'Vùng annotation cần đối chiếu' })).toBeInTheDocument();
    expect(screen.queryByText('Đề xuất detector')).not.toBeInTheDocument();
  });

  it('replaces both focus windows on issue change and clears them on a different frame', () => {
    const { container, rerender } = render(<ReviewCanvas {...props} />);
    rerender(<ReviewCanvas {...props} selectedIssueId={58} />);
    expect(container.querySelector('clipPath[id$="-focus"] rect')).toHaveAttribute('x', '110');
    expect(container.querySelector('[data-annotation-id="shape:9090"]')).toHaveAttribute('opacity', '0.16');
    rerender(<ReviewCanvas {...props} frame={{ ...frame, id: 5 }} issues={[]} snapshotAnnotations={[]} />);
    expect(screen.queryByTestId('issue-focus-image')).not.toBeInTheDocument();
    expect(container.querySelector('image')).not.toHaveAttribute('filter');
  });

  it('shows the whole image and all annotations in Frame Review, restores selected focus in Issue Review', () => {
    const { container, rerender } = render(<ReviewCanvas {...props} />);
    rerender(<ReviewCanvas {...props} reviewMode="frame" />);
    expect(screen.queryByTestId('issue-focus-image')).not.toBeInTheDocument();
    expect(container.querySelector('image')).toHaveAttribute('opacity', '1');
    expect(container.querySelector('[data-annotation-id="shape:9091"]')).toHaveAttribute('opacity', '1');
    rerender(<ReviewCanvas {...props} />);
    expect(screen.getByTestId('issue-focus-image')).toBeInTheDocument();
  });

  it('does not fall back to a previous/first issue for invalid selection', () => {
    render(<ReviewCanvas {...props} selectedIssueId={999} />);
    expect(screen.queryByTestId('issue-focus-image')).not.toBeInTheDocument();
  });

  it('explains missing, unmapped, invalid and incomplete anchors', () => {
    expect(resolveIssueFocus({ ...issues[0], anchor: undefined } as unknown as Issue).reasons.join()).toContain('thiếu anchor');
    expect(resolveIssueFocus(issue(1, [999, 9090]), annotations).reasons.join()).toContain('cvat_shape:shape:999');
    expect(resolveIssueFocus(issue(1, [9090]), annotations).reasons.join()).toContain('ít nhất hai');
    expect(resolveIssueFocus(issue(1, [9090, 9090]), annotations).reasons.join()).toContain('khác nhau');
    const invalid = annotations.map(a => ({ ...a, bbox: { x1: 1, y1: 1, x2: 0, y2: 0 } }));
    expect(resolveIssueFocus(issues[0], invalid).regions).toHaveLength(0);
    expect(resolveIssueFocus(issues[0], invalid).reasons.join()).toContain('tọa độ không hợp lệ');
  });

  it('does not confuse shape and track IDs', () => {
    const track = { ...annotations[0], id: 'track:9090', source: { kind: 'track', id: 9090 } };
    expect(resolveIssueFocus(issues[0], [track]).annotations).toHaveLength(0);
    expect(resolveIssueFocus(issue(1, [9090]), [track]).regions).toHaveLength(0);
  });

  it('retains rotation and rejects invalid rotation and regions outside the snapshot', () => {
    const rotated = annotations.map(a => ({ ...a, rotation: 25 }));
    expect(resolveIssueFocus(issues[0], rotated, frame).regions[0].rotation).toBe(25);
    const outside = annotations.map(a => ({ ...a, bbox: { x1: 2000, y1: 20, x2: 2200, y2: 80 } }));
    expect(resolveIssueFocus(issues[0], outside, frame).regions).toHaveLength(0);
    expect(resolveIssueFocus(issues[0], outside, frame).reasons.join()).toContain('nằm ngoài frame');
    expect(resolveIssueFocus(issues[0], annotations.map(a => ({ ...a, rotation: NaN }))).regions).toHaveLength(0);
  });

  it('uses an explicit prediction region without requiring a snapshot annotation', () => {
    const predictionIssue = { ...issues[0], family: 'E1' as const,
      anchor: { kind: 'prediction_region' as const, policy_version: '1.0.0',
        objects: [{ namespace: 'detector' as const, id: '6:0' }], bbox: annotations[0].bbox } };
    expect(resolveIssueFocus(predictionIssue, []).regions).toHaveLength(1);
    expect(resolveIssueFocus(predictionIssue, []).reasons).toHaveLength(0);
  });
});
