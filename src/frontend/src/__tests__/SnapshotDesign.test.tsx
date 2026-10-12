import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AnalysisPage from '@/app/analysis/page';
import SnapshotHistoryPage from '@/app/analysis/snapshots/page';
import { SnapshotForm } from '@/components/snapshots/SnapshotForm';
import * as api from '@/lib/snapshots/api';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/analysis',
}));
vi.mock('@/lib/auth/auth-context', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'tester', role: 'qa_lead', fullName: 'QA Lead' },
    session: { user: { id: 1, username: 'tester' }, roles: [{ role: 'qa_lead', dataset_id: 42 }],
      identity_mapping: { status: 'mapped', cvat_user_id: 1, cvat_username: 'tester' } },
    isLoading: false, datasetId: 42, setDatasetId: vi.fn(), logout: vi.fn(), hasPermission: () => true,
  }),
}));
vi.mock('@/lib/snapshots/api', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/snapshots/api')>()),
  getDatasets: vi.fn(), getSnapshot: vi.fn(), getSnapshots: vi.fn(), getTasks: vi.fn(), postSnapshot: vi.fn(),
}));

const client = () => new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
const wrap = (node: React.ReactNode) => render(<QueryClientProvider client={client()}>{node}</QueryClientProvider>);
const dataset = { id: 42, name: 'Urban', cvat_project_id: 31, taxonomy_version: 'v3', guideline_version: 'v1.2' };
const locked = { id: 7, dataset_id: 42, status: 'locked' as const, revision_hash: 'sha256:abc', parent_snapshot_id: null,
  drift_jobs: [], created_by: 3, created_at: '2026-10-09T08:00:00Z', taxonomy_version: 'v3', guideline_version: 'v1.2', locked_at: null,
  jobs: [{ cvat_job_id: 1, cvat_task_id: 1, job_hash: null, assignee_user_id: null, cvat_url: 'https://cvat.example/jobs/1',
    frames: [{ frame_index: 0, file_name: 'a.jpg', width: 1, height: 1, cvat_url: 'https://cvat.example/f' },
      { frame_index: 1, file_name: 'b.jpg', width: 1, height: 1, cvat_url: 'https://cvat.example/f2' }] }] };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getDatasets).mockResolvedValue({ results: [dataset], next: null, previous: null });
  vi.mocked(api.getTasks).mockResolvedValue([]);
  vi.mocked(api.getSnapshots).mockResolvedValue({ results: [locked], next: null, previous: null });
});

describe('Snapshot (Snapshot.dc.html)', () => {
  it('lays out the design regions around the real data', async () => {
    wrap(<AnalysisPage />);
    expect(await screen.findByRole('heading', { name: 'Snapshot' })).toBeDefined();
    expect(screen.getByRole('link', { name: 'Lịch sử snapshot' }).getAttribute('href')).toBe('/analysis/snapshots');
    expect(screen.getByRole('heading', { name: 'Tạo snapshot mới' })).toBeDefined();
    expect(screen.getByRole('heading', { name: 'Snapshot đang dùng' })).toBeDefined();
    expect(screen.getByLabelText('Annotation revision')).toBeDefined();
    expect(screen.getByLabelText('Mã hạt giống lấy mẫu (seed)')).toBeDefined();
    expect((screen.getByLabelText('Annotation revision') as HTMLSelectElement).disabled).toBe(true);
    const side = within(await screen.findByRole('region', { name: 'Snapshot đang dùng' }));
    expect(await side.findByText('abc')).toBeDefined();
    expect(side.getByText('Đã khoá')).toBeDefined();
    expect(side.getByText('Mô hình độc lập')).toBeDefined();
    expect(side.getAllByText('Dữ liệu minh họa').length).toBe(1);
  });

  it('shows the whole design with sample data and a blocked write when datasets cannot be loaded', async () => {
    vi.mocked(api.getDatasets).mockRejectedValue(new Error('down'));
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    wrap(<AnalysisPage />);
    expect(await screen.findByText('SNP-014')).toBeDefined();
    expect(screen.getByText('T-119 · Urban night')).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: 'Tạo snapshot và cấu hình →' }));
    expect(screen.getByRole('region', { name: 'Tạo snapshot mới' }).textContent).toContain('Thao tác "Tạo snapshot và cấu hình" chưa được thực hiện');
    expect(api.postSnapshot).not.toHaveBeenCalled();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

describe('Snapshot create form scope', () => {
  const tasks = [{ cvat_task_id: 9, name: 'Day', jobs: [
    { cvat_job_id: 17, assignee_cvat_user_id: 3, frame_count: 12, updated_date: '2026-10-09T07:00:00Z' },
    { cvat_job_id: 18, assignee_cvat_user_id: null, frame_count: 8, updated_date: '2026-10-09T07:00:00Z' }] }];
  const show = () => wrap(<SnapshotForm datasetId={42} tasks={tasks} canCreate />);

  it('counts the selected task, job and frame like the design hint', () => {
    show();
    expect(screen.getByText(/Toàn Dataset · 1 task · 2 job · 20 frame\./)).toBeDefined();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Chọn tất cả' }));
    fireEvent.click(screen.getAllByRole('button', { name: /\d+ Job/ })[0]);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Chọn Job 17' }));
    expect(screen.getByText(/Hiện chọn 1 task · 1 job · 12 frame\./)).toBeDefined();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Chọn tất cả' }));
    expect(screen.getByText(/Toàn Dataset · 1 task · 2 job · 20 frame\./)).toBeDefined();
  });

  it('lists only Task rows by default and reveals Job rows on demand with thousands separators', () => {
    show();
    expect(screen.queryByRole('checkbox', { name: 'Chọn Job 17' })).toBeNull();
    expect(screen.getByRole('checkbox', { name: 'Chọn Task 9' })).toBeDefined();
    const toggle = screen.getByRole('button', { name: /2 Job/ });
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(toggle);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByRole('checkbox', { name: 'Chọn Job 17' })).toBeDefined();
  });

  it('shows the stage column placeholder next to the assignee', () => {
    show();
    expect(screen.getByRole('columnheader', { name: 'Người thực hiện · Giai đoạn' })).toBeDefined();
    fireEvent.click(screen.getAllByRole('button', { name: /\d+ Job/ })[0]);
    expect(within(screen.getByRole('checkbox', { name: 'Chọn Job 17' }).closest('tr') as HTMLElement).getByText(/3 · —/)).toBeDefined();
  });

  it('selects the whole dataset by default, sends it, and cancel restores that default', async () => {
    vi.mocked(api.postSnapshot).mockResolvedValue({ id: 5, status: 'locked' } as never);
    show();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Chọn tất cả' }));
    fireEvent.click(screen.getByRole('button', { name: 'Huỷ' }));
    expect((screen.getByRole('checkbox', { name: 'Chọn tất cả' }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Tạo snapshot và cấu hình →' }));
    await waitFor(() => expect(api.postSnapshot).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.postSnapshot).mock.calls[0][0]).toEqual({ dataset_id: 42, scope: { cvat_task_ids: [], cvat_job_ids: [] } });
  });
});

describe('Snapshot history (SnapshotHistory.dc.html)', () => {
  it('uses the design columns with real snapshots and one not-connected notice', async () => {
    wrap(<SnapshotHistoryPage />);
    expect(await screen.findByRole('heading', { name: 'Lịch sử snapshot' })).toBeDefined();
    expect(screen.getByRole('link', { name: 'Về Snapshot' }).getAttribute('href')).toBe('/analysis');
    const headers = (await screen.findAllByRole('columnheader')).map(th => th.textContent);
    expect(headers).toEqual(['Snapshot', 'Dataset', 'Revision', 'Frame', 'Quality Control Run', 'Trạng thái']);
    expect(screen.getByRole('link', { name: 'SNP-007' }).getAttribute('href')).toBe('/analysis?snapshotId=7');
    const row = within(screen.getByRole('link', { name: 'SNP-007' }).closest('tr') as HTMLElement);
    expect(row.getByText('Urban')).toBeDefined();
    expect(row.getByText('abc')).toBeDefined();
    expect(row.getByText('2')).toBeDefined();
    expect(row.getByText('Đã khóa')).toBeDefined();
    expect(screen.getAllByRole('status').filter(node => node.textContent?.includes('chưa được kết nối')).length).toBe(1);
  });

  it('keeps the design table as labelled sample data when the history cannot be loaded', async () => {
    vi.mocked(api.getSnapshots).mockRejectedValue(new Error('down'));
    wrap(<SnapshotHistoryPage />);
    expect(await screen.findByText('SNP-014')).toBeDefined();
    expect(screen.getByText('#QC-091')).toBeDefined();
    expect(screen.getByText('Dữ liệu minh họa')).toBeDefined();
    expect(screen.getByText('4 snapshot')).toBeDefined();
  });
});
