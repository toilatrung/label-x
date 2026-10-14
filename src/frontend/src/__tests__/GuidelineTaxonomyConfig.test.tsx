import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
vi.mock('@/lib/guidelines/config-api', () => ({ getDatasetGuideline: vi.fn(), listGuidelineVersions: vi.fn(), previewGuideline: vi.fn(), importGuideline: vi.fn(), setDatasetGuideline: vi.fn() }));
const binding = { dataset_id: 42, guideline_version: 'v1', guideline_checksum: 'a', taxonomy_version: 't1', taxonomy_ready: true, revision: 3 };
const taxonomy = { version: 't2', labels: [{ name: 'car', required_attributes: [] }] };
const preview = { version: 'v2', name: 'Policy', rules: [{ rule_id: 'A-001', section: '1' }], taxonomy };
const tasks = [{ cvat_task_id: 9, name: 'Test', jobs: [{ cvat_job_id: 17, assignee_cvat_user_id: null, updated_date: '2026-10-14' }] }];
function show(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>{node}</QueryClientProvider>);
}
async function chooseFile(content = 'version: v2') {
  const file = new File([content], 'guideline.yaml', { type: 'application/yaml' });
  Object.defineProperty(file, 'text', { value: async () => content });
  fireEvent.change(screen.getByLabelText('Tệp Guideline (YAML)'), { target: { files: [file] } });
  await waitFor(() => expect(api.previewGuideline).toHaveBeenCalledWith(content));
}
async function openDefaults() {
  fireEvent.click(screen.getByText('Guideline mặc định cho Dataset (tùy chọn)'));
  await waitFor(() => expect(api.getDatasetGuideline).toHaveBeenCalled());
}
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new Event('close')); };
  session.role = 'qc_admin';
  vi.mocked(api.getDatasetGuideline).mockResolvedValue(binding);
  vi.mocked(api.previewGuideline).mockResolvedValue(preview);
  vi.mocked(api.importGuideline).mockResolvedValue({ version: 'v2', checksum: 'b', taxonomy, skipped: false });
  vi.mocked(api.listGuidelineVersions).mockResolvedValue({ next: null, previous: null, results: [
    { version: 'v1', is_current: false, rule_count: 1, taxonomy_version: 't1', taxonomy_ready: true },
    { version: 'v2', is_current: true, rule_count: 1, taxonomy_version: 't2', taxonomy_ready: true },
    { version: 'legacy', is_current: false, rule_count: 1, taxonomy_version: null, taxonomy_ready: false },
  ] });
});
describe('Guideline library and Snapshot selection', () => {
  it('opens a modal and imports embedded taxonomy without applying a Dataset default', async () => {
    show(<GuidelineTaxonomyConfig />);
    expect(screen.queryByLabelText('Tệp Guideline (YAML)')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Thêm Guideline' }));
    expect(screen.getByRole('dialog', { name: 'Thêm Guideline' })).toBeDefined();
    await chooseFile();
    await screen.findByRole('region', { name: 'Taxonomy từ Guideline' });
    fireEvent.click(screen.getByRole('button', { name: 'Import Guideline' }));
    await waitFor(() => expect(api.importGuideline).toHaveBeenCalledWith('version: v2', undefined));
    expect(await screen.findByText('Đã import Guideline v2.')).toBeDefined();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(api.setDatasetGuideline).not.toHaveBeenCalled();
  });
  it('requires manual taxonomy when the file has none, including attribute rule and values', async () => {
    vi.mocked(api.previewGuideline).mockResolvedValue({ ...preview, taxonomy: null });
    show(<GuidelineTaxonomyConfig />);
    fireEvent.click(screen.getByRole('button', { name: 'Thêm Guideline' }));
    await chooseFile();
    await screen.findByLabelText('Phiên bản taxonomy *');
    expect(screen.getByRole('button', { name: 'Import Guideline' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Phiên bản taxonomy *'), { target: { value: 'manual-v1' } });
    fireEvent.change(screen.getByLabelText('Tên lớp 1 *'), { target: { value: 'car' } });
    fireEvent.click(screen.getByRole('button', { name: 'Thêm thuộc tính bắt buộc cho lớp 1' }));
    expect(screen.getByRole('button', { name: 'Import Guideline' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Thuộc tính bắt buộc 1.1 *'), { target: { value: 'state' } });
    fireEvent.change(screen.getByLabelText('Rule cho thuộc tính 1.1 *'), { target: { value: 'A-001' } });
    fireEvent.change(screen.getByLabelText('Giá trị cho phép 1.1'), { target: { value: 'moving\nparked' } });
    fireEvent.click(screen.getByRole('button', { name: 'Import Guideline' }));
    await waitFor(() => expect(api.importGuideline).toHaveBeenCalledWith('version: v2', {
      version: 'manual-v1', labels: [{ name: 'car', required_attributes: [{ name: 'state', rule_id: 'A-001', allowed_values: ['moving', 'parked'] }] }],
    }));
    expect(api.setDatasetGuideline).not.toHaveBeenCalled();
  });
  it('can cancel the modal without importing and restores focus to the add button', async () => {
    show(<GuidelineTaxonomyConfig />);
    const button = screen.getByRole('button', { name: 'Thêm Guideline' });
    button.focus(); fireEvent.click(button);
    fireEvent.click(screen.getByRole('button', { name: 'Hủy' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(button);
    expect(api.importGuideline).not.toHaveBeenCalled();
  });
  it('keeps an import failure inside the modal without reporting success', async () => {
    vi.mocked(api.importGuideline).mockRejectedValue(new Error('rejected'));
    show(<GuidelineTaxonomyConfig />);
    fireEvent.click(screen.getByRole('button', { name: 'Thêm Guideline' }));
    await chooseFile();
    await screen.findByRole('region', { name: 'Taxonomy từ Guideline' });
    fireEvent.click(screen.getByRole('button', { name: 'Import Guideline' }));
    const modal = screen.getByRole('dialog');
    expect(await within(modal).findByRole('alert')).toBeDefined();
    expect(screen.queryByText('Đã import Guideline v2.')).toBeNull();
  });
  it('saves an optional Dataset default with its API revision', async () => {
    vi.mocked(api.setDatasetGuideline).mockResolvedValue({ ...binding, guideline_version: 'v2', revision: 4 });
    show(<GuidelineTaxonomyConfig />);
    await openDefaults();
    await screen.findByRole('option', { name: 'v2 · t2' });
    fireEvent.change(screen.getByLabelText('Guideline mặc định cho Dataset'), { target: { value: 'v2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu mặc định cho Dataset' }));
    await waitFor(() => expect(api.setDatasetGuideline).toHaveBeenCalledWith(42, 'v2', 3));
    expect(await screen.findByText(/Đã lưu Guideline v2 làm mặc định/)).toBeDefined();
  });
  it('keeps import and default mutations unavailable to QA Lead', async () => {
    session.role = 'qa_lead';
    show(<GuidelineTaxonomyConfig />);
    expect(await screen.findByText('legacy')).toBeDefined();
    expect(screen.queryByRole('button', { name: 'Thêm Guideline' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Lưu mặc định cho Dataset' })).toBeNull();
  });
  it('can choose a Guideline for a Snapshot even when its Dataset has no default', async () => {
    vi.mocked(api.getDatasetGuideline).mockResolvedValue({ ...binding, guideline_version: null, taxonomy_version: null, taxonomy_ready: false });
    postSnapshot.mockResolvedValue({ id: 99, status: 'locked' });
    show(<SnapshotForm datasetId={42} canCreate tasks={tasks} />);
    await screen.findByRole('option', { name: 'v2 · t2' });
    expect(screen.getByRole('button', { name: 'Tạo snapshot và cấu hình →' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Guideline cho Snapshot này'), { target: { value: 'v2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo snapshot và cấu hình →' }));
    await waitFor(() => expect(postSnapshot).toHaveBeenCalledTimes(1));
    expect(postSnapshot.mock.calls[0][0]).toEqual({ dataset_id: 42, guideline_version: 'v2', scope: { cvat_task_ids: [], cvat_job_ids: [] } });
    expect(api.setDatasetGuideline).not.toHaveBeenCalled();
    expect(screen.queryByRole('option', { name: /legacy/ })).toBeNull();
  });
  it('uses the Dataset default only when no specific Snapshot Guideline is chosen', async () => {
    postSnapshot.mockResolvedValue({ id: 99, status: 'locked' });
    show(<SnapshotForm datasetId={42} canCreate tasks={tasks} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Tạo snapshot và cấu hình →' })).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', { name: 'Tạo snapshot và cấu hình →' }));
    await waitFor(() => expect(postSnapshot).toHaveBeenCalledTimes(1));
    expect(postSnapshot.mock.calls[0][0]).toEqual({ dataset_id: 42, expected_guideline_version: 'v1', scope: { cvat_task_ids: [], cvat_job_ids: [] } });
  });
});
