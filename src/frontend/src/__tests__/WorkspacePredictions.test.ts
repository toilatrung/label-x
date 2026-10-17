import { describe, expect, it } from 'vitest';
import { reviewBBox, workspacePredictions, type FrameWorkspace } from '@/lib/review/workspace-api';

describe('workspace model overlays', () => {
  it('accepts actual detector xyxy output and rejects invalid geometry', () => {
    expect(reviewBBox([1, 2, 10, 20])).toEqual({ x1: 1, y1: 2, x2: 10, y2: 20 });
    expect(reviewBBox([10, 20, 1, 2])).toBeNull();
    expect(reviewBBox([1, 2, Infinity, 20])).toBeNull();
  });

  it.each(['qwen', 'gemini'])('shows detector and completed %s suggestions while keeping CVAT annotations untouched', source => {
    const data = {
      predictions: [{ candidate_id: 3, engine: 'detector', evidence: {
        prediction_bbox: [1, 2, 10, 20], prediction_class: 'truck', confidence: 0.8,
      } }],
      issues: [{ id: 9, anchor: { bbox: { x1: 1, y1: 2, x2: 10, y2: 20 } }, evidence: [] }],
      annotations: [{ id: 'shape:7', label_id: 1, label: 'car' }],
      ai_evidence: [{ issue_id: 9, candidate_id: 3, evaluation_id: 5, source,
        status: 'completed', suggestion: { status: 'checked', class_name: 'bus' } }],
    } as unknown as FrameWorkspace;
    const original = JSON.stringify(data);
    const predictions = workspacePredictions(data);
    expect(predictions.map(item => item.label)).toEqual(['truck', 'bus']);
    expect(predictions[1].issueId).toBe(9);
    expect(predictions[1].source).toBe(`${source === 'gemini' ? 'Gemini' : 'Qwen'} · mô hình 2`);
    expect(JSON.stringify(data)).toBe(original);
    data.ai_evidence![0].status = 'running';
    expect(workspacePredictions(data).map(item => item.label)).toEqual(['truck']);
    data.ai_evidence![0].status = 'completed';
    data.ai_evidence![0].suggestion!.status = 'uncertain';
    expect(workspacePredictions(data).map(item => item.label)).toEqual(['truck']);
  });
});
