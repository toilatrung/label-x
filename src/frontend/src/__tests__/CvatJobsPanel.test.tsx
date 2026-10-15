import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { CvatJobsPanel } from '@/components/review/CvatJobsPanel';

const { refetch } = vi.hoisted(() => ({ refetch: vi.fn() }));
vi.mock('@/lib/auth/auth-context', () => ({ useAuth: () => ({
  datasetId: 42, session: { user: { id: 1 }, roles: [{ role: 'super_admin', dataset_id: null }] },
}) }));
vi.mock('@/lib/snapshots/queries', () => ({ useTasks: () => ({
  isSuccess: true, refetch, data: [{ cvat_task_id: 9, name: 'Urban', jobs: [{
    cvat_job_id: 17, assignee_name: 'alice', stage: 'annotation', state: 'in_progress',
    cvat_url: 'https://cvat.test/tasks/9/jobs/17',
  }] }],
}) }));

describe('CVAT jobs in LabelX', () => {
  it('shows jobs before a QC run exists and lets the user prepare that exact job', () => {
    render(<CvatJobsPanel />);
    expect(screen.getByText('Job #17')).toBeDefined();
    expect(screen.getByText('alice')).toBeDefined();
    expect(screen.getByText('Đang thực hiện')).toBeDefined();
    expect(screen.getByRole('link', { name: 'Tạo snapshot cho Job' }).getAttribute('href')).toBe('/analysis?jobId=17');
    expect(screen.getByRole('link', { name: 'Mở CVAT ↗' }).getAttribute('href')).toBe('https://cvat.test/tasks/9/jobs/17');
    fireEvent.click(screen.getByRole('button', { name: 'Làm mới từ CVAT' }));
    expect(refetch).toHaveBeenCalledOnce();
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'missing' } });
    expect(screen.queryByText('Job #17')).toBeNull();
  });
});
