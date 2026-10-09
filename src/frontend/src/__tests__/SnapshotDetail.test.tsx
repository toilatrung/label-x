import React from 'react';
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SnapshotDetail } from '@/components/snapshots/SnapshotDetail';
import type { Snapshot } from '@/lib/snapshots/api';

const item: Snapshot = { id: 5, dataset_id: 42, status: 'failed', failure_reason: 'drift_detected',
  revision_hash: null, parent_snapshot_id: 4, drift_jobs: [17], out_of_scope_shapes: 7,
  taxonomy_version: 'v3', guideline_version: 'v1', created_by: 1, created_at: '2026-10-09T08:00:00Z',
  jobs: [{ cvat_job_id: 17, cvat_task_id: 9, job_hash: null, assignee_user_id: 3,
    cvat_url: 'https://cvat.example.test/tasks/9/jobs/17', frames: [
      { frame_index: 0, file_name: 'a.jpg', width: 10, height: 10,
        cvat_url: 'https://cvat.example.test/tasks/9/jobs/17?frame=0' },
      { frame_index: 1, file_name: 'b.jpg', width: 10, height: 10,
        cvat_url: 'https://cvat.example.test/tasks/9/jobs/17?frame=1' },
    ] }],
};

describe('Snapshot detail', () => {
  it('shows drift, skipped shapes, parent and CVAT job/frame deep links', () => {
    render(<SnapshotDetail item={item} />);
    expect(screen.getByText('Job có drift: 17')).toBeDefined();
    expect(screen.getByText('7')).toBeDefined();
    expect(screen.getByRole('link', { name: 'SNP-4' }).getAttribute('href')).toBe('/analysis?snapshotId=4');
    expect(screen.getByRole('link', { name: 'Mở Job CVAT' }).getAttribute('href')).toContain('/tasks/9/jobs/17');
    fireEvent.change(screen.getByRole('combobox', { name: 'Frame Job 17' }), { target: { value: '1' } });
    expect(screen.getByRole('link', { name: 'Mở Frame' }).getAttribute('href')).toContain('frame=1');
  });
});
