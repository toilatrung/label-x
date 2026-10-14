import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GuidelineTaxonomyConfig } from '@/components/guidelines/GuidelineTaxonomyConfig';
import { SnapshotForm } from '@/components/snapshots/SnapshotForm';
import * as api from '@/lib/guidelines/config-api';

const { postSnapshot, session } = vi.hoisted(() => ({ postSnapshot: vi.fn(), session: { role: 'qc_admin' } }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('@/lib/auth/auth-context', () => ({ useAuth: () => ({ datasetId: 42,
  session: { user: { id: 1 }, roles: [{ role: session.role, dataset_id: null }] } }) }));
vi.mock('@/lib/execution/DatasetPicker', () => ({ DatasetPicker: () => <p>Dataset #42</p> }));
vi.mock('@/lib/snapshots/api', () => ({ postSnapshot }));
vi.mock('@/lib/guidelines/config-api', () => ({ getDatasetGuideline: vi.fn(), listGuidelineVersions: vi.fn(), importGuideline: vi.fn(), setDatasetGuideline: vi.fn() }));
const binding = { dataset_id: 42, guideline_version: 'v1', guideline_checksum: 'a', taxonomy_version: 't1', taxonomy_ready: true, revision: 3 };
function show(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>{node}</QueryClientProvider>);
}
beforeEach(() => {
  session.role = 'qc_admin';
  vi.mocked(api.getDatasetGuideline).mockResolvedValue(binding);
  vi.mocked(api.listGuidelineVersions).mockResolvedValue({ next: null, previous: null, results: [
    { version: 'v1', is_current: false, rule_count: 1, taxonomy_version: 't1', taxonomy_ready: true },
    { version: 'v2', is_current: true, rule_count: 1, taxonomy_version: 't2', taxonomy_ready: true },
    { version: 'legacy', is_current: false, rule_count: 1, taxonomy_version: null, taxonomy_ready: false },
  ] });
});
describe('Dataset guideline policy', () => {
  it('imports the selected YAML file through the API', async () => {
    vi.mocked(api.importGuideline).mockResolvedValue({ version: 'v2', checksum: 'b', taxonomy: {}, skipped: false });
    show(<GuidelineTaxonomyConfig />);
    const file = new File(['version: v2'], 'guideline.yaml', { type: 'application/yaml' });
    Object.defineProperty(file, 'text', { value: async () => 'version: v2' });
    fireEvent.change(screen.getByLabelText('Import Guideline và taxonomy (YAML)'), { target: { files: [file] } });
    await waitFor(() => expect((screen.getByRole('button', { name: 'Import Guideline' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'Import Guideline' }));
    await waitFor(() => expect(api.importGuideline).toHaveBeenCalledWith('version: v2'));
    expect(await screen.findByText('Đã import Guideline v2.')).toBeDefined();
  });
  it('saves the selected version with the revision from the API', async () => {
    vi.mocked(api.setDatasetGuideline).mockResolvedValue({ ...binding, guideline_version: 'v2', revision: 4 });
    show(<GuidelineTaxonomyConfig />);
    await screen.findByRole('option', { name: 'v2 · t2' });
    expect((screen.getByRole('option', { name: 'legacy · Chưa có taxonomy' }) as HTMLOptionElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Guideline version cho Snapshot mới'), { target: { value: 'v2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Áp dụng cho Dataset' }));
    await waitFor(() => expect(api.setDatasetGuideline).toHaveBeenCalledWith(42, 'v2', 3));
    expect(await screen.findByText(/Dataset đã áp dụng Guideline v2/)).toBeDefined();
  });
  it('keeps mutations unavailable to QA Lead', async () => {
    session.role = 'qa_lead';
    show(<GuidelineTaxonomyConfig />);
    await screen.findByRole('option', { name: 'v1 · t1' });
    expect(screen.queryByRole('button', { name: 'Import Guideline' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Áp dụng cho Dataset' })).toBeNull();
  });
  it('blocks Snapshot creation when Dataset has no taxonomy policy', async () => {
    vi.mocked(api.getDatasetGuideline).mockResolvedValue({ ...binding, guideline_version: null, taxonomy_version: null, taxonomy_ready: false });
    show(<SnapshotForm datasetId={42} canCreate tasks={[{ cvat_task_id: 9, name: 'Test', jobs: [{ cvat_job_id: 17, assignee_cvat_user_id: null, updated_date: '2026-10-14' }] }]} />);
    await screen.findByText(/Dataset chưa có Guideline với taxonomy/);
    const button = screen.getByRole('button', { name: 'Tạo snapshot và cấu hình →' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(postSnapshot).not.toHaveBeenCalled();
  });
  it('shows an API write failure without reporting success', async () => {
    vi.mocked(api.setDatasetGuideline).mockRejectedValue(new Error('conflict'));
    show(<GuidelineTaxonomyConfig />);
    await screen.findByRole('option', { name: 'v2 · t2' });
    fireEvent.change(screen.getByLabelText('Guideline version cho Snapshot mới'), { target: { value: 'v2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Áp dụng cho Dataset' }));
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(screen.queryByText(/Dataset đã áp dụng Guideline/)).toBeNull();
  });
});
