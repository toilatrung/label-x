import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  ReviewCanvas,
  calculateLetterboxTransform,
} from '@/components/review/ReviewCanvas';
import type { components } from '@/lib/api/contract';

type FrameSummary = components['schemas']['FrameSummary'];
type Issue = components['schemas']['Issue'];

const mockFrame: FrameSummary = {
  id: 428,
  run_id: 1,
  frame_key: { cvat_task_id: 10, frame_number: 428 },
  review_state: 'in_review',
  missing_evidence: false,
  width: 960,
  height: 540,
  image_url: 'https://example.com/frame-428.jpg',
  cvat_deep_link: 'https://cvat.example.com/tasks/10/jobs/1?frame=428',
};

const mockIssue: Issue = {
  id: 128,
  family: 'E2',
  origin: 'engine',
  state: 'pending_review',
  n_i: 1,
  anchor: {
    kind: 'annotation',
    policy_version: 'v1.0',
    objects: [{ namespace: 'cvat_shape', id: 'shape-18' }],
    bbox: { x1: 300, y1: 200, x2: 450, y2: 350 },
  },
  evidence: [
    {
      engine: 'detector',
      prediction_class: 'truck',
      confidence: 0.85,
      iou: 0.72,
      prediction_bbox: { x1: 290, y1: 190, x2: 460, y2: 360 },
    },
  ],
  links: [],
  review_decisions: [],
};

describe('ReviewCanvas (T-037 Canvas & Coordinate Transformation)', () => {
  describe('calculateLetterboxTransform', () => {
    it('accurately computes inverse coordinates with matching aspect ratio at 1x zoom and 0 pan', () => {
      // 960x540 viewBox inside 960x540 viewport (16:9 in 16:9)
      const rect = { width: 960, height: 540, left: 0, top: 0 };
      const pt = calculateLetterboxTransform(rect, 960, 540, 480, 270, 1, { x: 0, y: 0 });
      expect(pt.x).toBe(480);
      expect(pt.y).toBe(270);
    });

    it('handles pillarbox (wider viewport than SVG viewBox aspect ratio)', () => {
      // 960x540 viewBox (16:9 = 1.777) in 1920x540 viewport (32:9 = 3.555)
      // Viewport has scale = 540/540 = 1. Width consumed by SVG is 960.
      // Horizontal offset is (1920 - 960) / 2 = 480.
      const rect = { width: 1920, height: 540, left: 100, top: 50 };
      // Clicking at horizontal center: left + 480 + (960/2) = 100 + 480 + 480 = 1060
      const ptCenter = calculateLetterboxTransform(rect, 960, 540, 1060, 320, 1, { x: 0, y: 0 });
      expect(ptCenter.x).toBe(480);
      expect(ptCenter.y).toBe(270);
    });

    it('handles letterbox (taller viewport than SVG viewBox aspect ratio)', () => {
      // 960x540 viewBox (1.777) in 960x1080 viewport (0.888)
      // Viewport has scale = 960/960 = 1. Height consumed by SVG is 540.
      // Vertical offset is (1080 - 540) / 2 = 270.
      const rect = { width: 960, height: 1080, left: 0, top: 0 };
      // Clicking at vertical center: 270 + 270 = 540
      const ptCenter = calculateLetterboxTransform(rect, 960, 540, 480, 540, 1, { x: 0, y: 0 });
      expect(ptCenter.x).toBe(480);
      expect(ptCenter.y).toBe(270);
    });

    it('inverts pan and zoom accurately in viewBox coordinates', () => {
      const rect = { width: 960, height: 540, left: 0, top: 0 };
      // Zoom 2x, pan offset +100x +50y
      // svgX = (clickX - panX) / zoom = (300 - 100) / 2 = 100
      // svgY = (clickY - panY) / zoom = (250 - 50) / 2 = 100
      const pt = calculateLetterboxTransform(rect, 960, 540, 300, 250, 2, { x: 100, y: 50 });
      expect(pt.x).toBe(100);
      expect(pt.y).toBe(100);
    });

    it('clamps coordinates to [0, vbWidth] and [0, vbHeight] bounds', () => {
      const rect = { width: 960, height: 540, left: 0, top: 0 };
      const ptOutOfBoundsNegative = calculateLetterboxTransform(rect, 960, 540, -100, -50, 1, { x: 0, y: 0 });
      expect(ptOutOfBoundsNegative.x).toBe(0);
      expect(ptOutOfBoundsNegative.y).toBe(0);

      const ptOutOfBoundsOver = calculateLetterboxTransform(rect, 960, 540, 2000, 1500, 1, { x: 0, y: 0 });
      expect(ptOutOfBoundsOver.x).toBe(960);
      expect(ptOutOfBoundsOver.y).toBe(540);
    });
  });

  describe('Component Rendering & Behavior', () => {
    it('renders image when image_url is provided and does not render fake scenery', () => {
      render(
        <ReviewCanvas
          frame={mockFrame}
          issues={[mockIssue]}
          selectedIssueId={128}
          onSelectIssue={vi.fn()}
          reviewMode="issue"
          showAnnotations={true}
          showPredictions={true}
          zoom={1}
          pan={{ x: 0, y: 0 }}
          onZoomChange={vi.fn()}
          onPanChange={vi.fn()}
        />
      );

      const img = screen.getByRole('img');
      expect(img).toBeDefined();
      expect(screen.queryByText(/Không có image_url/)).toBeNull();
      // Verifies label includes anchor identifier
      expect(screen.getByText(/shape-18 · anchor/)).toBeDefined();
      // Verifies prediction label
      expect(screen.getByText(/đề xuất: truck · 0.85/)).toBeDefined();
    });

    it('displays explicit media unavailable message when image_url is absent without fake scenery', () => {
      const frameNoImage: FrameSummary = {
        ...mockFrame,
        image_url: undefined,
      };

      render(
        <ReviewCanvas
          frame={frameNoImage}
          issues={[mockIssue]}
          selectedIssueId={128}
          onSelectIssue={vi.fn()}
          reviewMode="issue"
          showAnnotations={true}
          showPredictions={true}
          zoom={1}
          pan={{ x: 0, y: 0 }}
          onZoomChange={vi.fn()}
          onPanChange={vi.fn()}
        />
      );

      expect(screen.getByText('Nguồn ảnh hiện không khả dụng')).toBeDefined();
    });

    it('toggles visibility of issue anchor layer and prediction layer', () => {
      const { rerender } = render(
        <ReviewCanvas
          frame={mockFrame}
          issues={[mockIssue]}
          selectedIssueId={128}
          onSelectIssue={vi.fn()}
          reviewMode="issue"
          showAnnotations={false}
          showPredictions={true}
          zoom={1}
          pan={{ x: 0, y: 0 }}
          onZoomChange={vi.fn()}
          onPanChange={vi.fn()}
        />
      );

      // Anchor layer hidden
      expect(screen.queryByText(/shape-18/)).toBeNull();
      // Prediction layer still visible
      expect(screen.getByText(/đề xuất: truck/)).toBeDefined();

      // Now toggle predictions off and annotations on
      rerender(
        <ReviewCanvas
          frame={mockFrame}
          issues={[mockIssue]}
          selectedIssueId={128}
          onSelectIssue={vi.fn()}
          reviewMode="issue"
          showAnnotations={true}
          showPredictions={false}
          zoom={1}
          pan={{ x: 0, y: 0 }}
          onZoomChange={vi.fn()}
          onPanChange={vi.fn()}
        />
      );

      expect(screen.getByText(/shape-18/)).toBeDefined();
      expect(screen.queryByText(/đề xuất: truck/)).toBeNull();
    });
  });
});
