import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { CandidateEvidenceList } from '@/components/execution/CandidateEvidenceList';
import type { Candidate } from '@/components/execution/CandidateEvidenceList';

describe('CandidateEvidenceList component (T-029)', () => {
  const sampleCandidates: Candidate[] = [
    {
      engine: 'duplicate',
      engine_version: '1.0.0',
      family: 'E3',
      severity: 'medium',
      frame: { cvat_task_id: 12, frame_number: 104 },
      anchor: {
        kind: 'annotation_cluster',
        policy_version: '1.0.0',
        rule_id: 'D-002',
        objects: [
          { namespace: 'cvat_shape', id: 'shape-1' },
          { namespace: 'cvat_shape', id: 'shape-2' },
        ],
      },
      evidence: {
        engine: 'duplicate',
        rule_id: 'D-002',
        iou: 0.9125,
        expected: 'Không trùng lặp annotation',
        actual: 'IoU 0.9125 vượt ngưỡng 0.85',
      },
    },
    {
      engine: 'geometry',
      engine_version: '1.0.0',
      family: 'E1',
      severity: 'critical',
      frame: { cvat_task_id: 12, frame_number: 105 },
      anchor: {
        kind: 'annotation',
        policy_version: '1.0.0',
        rule_id: 'G-014',
        objects: [{ namespace: 'cvat_shape', id: 'shape-3' }],
      },
      evidence: {
        engine: 'geometry',
        rule_id: 'G-014',
        actual: 'Diện tích 16 px² nhỏ hơn ngưỡng tối thiểu 24 px²',
      },
    },
  ];

  it('renders candidates table with evidence details and summary callout when counts are explicitly provided', () => {
    render(
      <CandidateEvidenceList
        candidates={sampleCandidates}
        rawCount={512}
        dedupCount={384}
      />
    );

    // Callout displays factual counts without unverified claim of being in Review Center
    expect(
      screen.getByText('Candidate: 512 bản ghi thô → 384 sau khi gộp trùng.')
    ).toBeDefined();
    expect(screen.queryByText(/đã đưa vào Review Center/)).toBeNull();

    // Table rows
    expect(screen.getByText('duplicate')).toBeDefined();
    expect(screen.getAllByText('v1.0.0').length).toBe(2);
    expect(screen.getAllByText('Task #12').length).toBe(2);
    expect(screen.getByText('Frame #104')).toBeDefined();
    expect(screen.getByText('E3')).toBeDefined();
    expect(screen.getByText('annotation_cluster')).toBeDefined();
    expect(screen.getByText('D-002')).toBeDefined();
    expect(screen.getByText('0.9125')).toBeDefined();
    expect(screen.getByText('Không trùng lặp annotation')).toBeDefined();
    expect(screen.getByText('IoU 0.9125 vượt ngưỡng 0.85')).toBeDefined();

    expect(screen.getByText('geometry')).toBeDefined();
    expect(screen.getByText('Frame #105')).toBeDefined();
    expect(screen.getByText('E1')).toBeDefined();
    expect(screen.getByText('G-014')).toBeDefined();
  });

  it('renders every object reference in an annotation cluster', () => {
    render(<CandidateEvidenceList candidates={[sampleCandidates[0]]} />);

    const row = screen.getByText('annotation_cluster').closest('tr')!;
    expect(within(row).getByText('cvat_shape:shape-1')).toBeDefined();
    expect(within(row).getByText('cvat_shape:shape-2')).toBeDefined();
  });

  it('distinguishes candidates with the same frame and rule but different annotation anchors', () => {
    const first = sampleCandidates[1];
    const second: Candidate = {
      ...first,
      anchor: {
        ...first.anchor,
        objects: [{ namespace: 'cvat_shape', id: 'shape-4' }],
      },
    };
    render(<CandidateEvidenceList candidates={[first, second]} />);

    const firstRow = screen.getByText('cvat_shape:shape-3').closest('tr')!;
    const secondRow = screen.getByText('cvat_shape:shape-4').closest('tr')!;
    expect(firstRow).not.toBe(secondRow);
    expect(firstRow.textContent).not.toBe(secondRow.textContent);
    expect(within(firstRow).queryByText('cvat_shape:shape-4')).toBeNull();
    expect(within(secondRow).queryByText('cvat_shape:shape-3')).toBeNull();
  });

  it('does not render count callout when rawCount or dedupCount are omitted, and does not infer counts from candidates.length', () => {
    render(<CandidateEvidenceList candidates={sampleCandidates} />);

    // Must not infer 2 raw -> 2 dedup from candidates.length
    expect(screen.queryByText(/bản ghi thô/)).toBeNull();
    expect(screen.queryByText(/sau khi gộp trùng/)).toBeNull();

    // Candidate table is still rendered
    expect(screen.getByText('duplicate')).toBeDefined();
    expect(screen.getByText('geometry')).toBeDefined();
  });

  it('renders unconnected or no-data state when candidates prop is not provided or undefined', () => {
    render(<CandidateEvidenceList />);

    // Should indicate API is not connected or no candidate data received
    expect(screen.getByText('Chưa có dữ liệu candidate')).toBeDefined();
    expect(
      screen.getByText(/Chưa có dữ liệu candidate từ backend cho lần chạy này/)
    ).toBeDefined();

    // Must NOT show "Chưa có candidate nghi vấn" which is reserved for empty list []
    expect(screen.queryByText('Chưa có candidate nghi vấn')).toBeNull();
    expect(screen.queryByText(/bản ghi thô/)).toBeNull();
  });

  it('renders empty candidate list state ("Chưa có candidate nghi vấn") only when candidates is [] after successful fetch', () => {
    render(<CandidateEvidenceList candidates={[]} />);

    expect(screen.getByText('Chưa có candidate nghi vấn')).toBeDefined();
    expect(
      screen.getByText(/Chưa có candidate nghi vấn nào cho lần chạy này \(không tự động xem là đạt kết quả\)\./)
    ).toBeDefined();

    // Must NOT show unconnected/no-data notice
    expect(screen.queryByText('Chưa có dữ liệu candidate')).toBeNull();
    expect(screen.queryByText(/bản ghi thô/)).toBeNull();
  });

  it('renders loading indicator when isLoading is true', () => {
    render(<CandidateEvidenceList isLoading={true} />);
    expect(screen.getByText('Đang tải candidate và evidence…')).toBeDefined();
    expect(screen.queryByText('Chưa có dữ liệu candidate')).toBeNull();
    expect(screen.queryByText('Chưa có candidate nghi vấn')).toBeNull();
  });

  it('renders error message when error is provided and does not show false empty or success states', () => {
    render(<CandidateEvidenceList error="Lỗi truy vấn candidate" />);
    expect(screen.getByText('Không tải được danh sách candidate')).toBeDefined();
    expect(screen.getByText('Lỗi truy vấn candidate')).toBeDefined();

    // Must NOT show empty state or table
    expect(screen.queryByText('Chưa có candidate nghi vấn')).toBeNull();
    expect(screen.queryByText('Chưa có dữ liệu candidate')).toBeNull();
  });

  it('renders prediction_class and prediction_bbox when detector evidence provides them (F-3)', () => {
    const detectorCandidate: Candidate = {
      engine: 'detector',
      engine_version: '2.4.0',
      family: 'E2',
      severity: 'critical',
      frame: { cvat_task_id: 15, frame_number: 42 },
      anchor: {
        kind: 'prediction_region',
        policy_version: '1.0.0',
        objects: [{ namespace: 'detector', id: '15:42' }],
      },
      evidence: {
        engine: 'detector',
        prediction_class: 'truck',
        prediction_bbox: { x1: 10, y1: 20, x2: 30, y2: 40 },
        confidence: 0.88,
      },
    };

    render(<CandidateEvidenceList candidates={[detectorCandidate]} />);

    expect(screen.getByText('truck')).toBeDefined();
    expect(screen.getByText('Lớp dự đoán:')).toBeDefined();
    expect(screen.getByText('[10, 20, 30, 40]')).toBeDefined();
    expect(screen.getByText('BBox dự đoán:')).toBeDefined();
    expect(screen.getByText('0.88')).toBeDefined();
  });

  it('renders dedupCount callout when rawCount is null without displaying 0 raw count (CR-108 Option 2)', () => {
    render(
      <CandidateEvidenceList
        candidates={sampleCandidates}
        rawCount={null}
        dedupCount={384}
      />
    );
    expect(screen.getByText('Candidate: 384 sau khi gộp trùng.')).toBeDefined();
    expect(screen.queryByText(/0 bản ghi thô/)).toBeNull();
  });
});
