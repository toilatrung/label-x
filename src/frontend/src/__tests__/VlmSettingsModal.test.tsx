import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { VlmSettingsModal } from '@/components/configuration/VlmSettingsModal';
import { ModelsGuidelinesCard } from '@/components/configuration/ModelsGuidelinesCard';

const mocks = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), role: 'qc_admin' }));
vi.mock('@/lib/auth/auth-context', () => ({ useAuth: () => ({ hasPermission: (check: (role: string) => boolean) => check(mocks.role) }) }));
vi.mock('@/lib/configuration/vlm-api', () => ({ getVlmSettings: mocks.get, saveVlmSettings: mocks.save }));

const settings = { revision: 7, base_url: 'https://api.shopaikey.com/v1', model: 'qwen3-vl-plus' as const, api_key_configured: true };

beforeEach(() => {
  mocks.role = 'qc_admin'; mocks.get.mockReset().mockResolvedValue(settings); mocks.save.mockReset().mockResolvedValue({ ...settings, revision: 8 });
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new Event('close')); };
});

describe('VLM settings', () => {
  it('keeps VLM in the model table and opens its settings only from edit', async () => {
    render(<ModelsGuidelinesCard />);
    const row = screen.getByRole('row', { name: /Mô hình thị giác – ngôn ngữ/ });
    expect(screen.queryByLabelText('API key')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.get).not.toHaveBeenCalled();
    fireEvent.click(within(row).getByRole('button', { name: 'Chỉnh mô hình' }));
    expect(screen.getByRole('dialog', { name: 'Chỉnh mô hình thị giác – ngôn ngữ' })).toBeInTheDocument();
    expect(await screen.findByLabelText('API key')).toBeInTheDocument();
  });

  it('closes without saving, restores edit focus, and clears unsaved secrets on reopen', async () => {
    render(<ModelsGuidelinesCard />);
    const edit = within(screen.getByRole('row', { name: /Mô hình thị giác – ngôn ngữ/ })).getByRole('button', { name: 'Chỉnh mô hình' });
    edit.focus();
    fireEvent.click(edit);
    fireEvent.change(await screen.findByLabelText('API key'), { target: { value: 'unsaved-secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Đóng' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.save).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(edit);
    fireEvent.click(edit);
    expect((await screen.findByLabelText('API key') as HTMLInputElement).value).toBe('');
  });

  it('disables the VLM edit button for QA Lead', () => {
    mocks.role = 'qa_lead';
    render(<ModelsGuidelinesCard />);
    expect(within(screen.getByRole('row', { name: /Mô hình thị giác – ngôn ngữ/ })).getByRole('button', { name: 'Chỉnh mô hình' })).toBeDisabled();
    expect(mocks.get).not.toHaveBeenCalled();
  });

  it('loads metadata and preserves the key when left blank', async () => {
    render(<VlmSettingsModal onClose={vi.fn()} />);
    const input = await screen.findByLabelText('API key');
    expect((input as HTMLInputElement).value).toBe('');
    expect(input).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByRole('button', { name: 'Lưu cấu hình VLM' }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith({ expected_revision: 7, base_url: settings.base_url, model: settings.model }));
    expect(await screen.findByText(/Đã lưu cấu hình VLM/)).toBeInTheDocument();
  });

  it('submits a replacement key and clears it after save', async () => {
    render(<VlmSettingsModal onClose={vi.fn()} />);
    const input = await screen.findByLabelText('API key');
    fireEvent.change(input, { target: { value: 'replacement-secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu cấu hình VLM' }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ api_key: 'replacement-secret' })));
    await screen.findByText(/Đã lưu cấu hình VLM/);
    expect((input as HTMLInputElement).value).toBe('');
  });

  it('requires a new key when changing the endpoint', async () => {
    render(<VlmSettingsModal onClose={vi.fn()} />);
    const input = await screen.findByLabelText('API key');
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1' } });
    expect(input).toHaveAttribute('required');
  });

  it('shows conflicts without reporting success and clears the key', async () => {
    mocks.save.mockRejectedValue(new Error('Cấu hình đã đổi'));
    render(<VlmSettingsModal onClose={vi.fn()} />);
    const input = await screen.findByLabelText('API key');
    fireEvent.change(input, { target: { value: 'private-secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu cấu hình VLM' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText(/Đã lưu cấu hình VLM/)).toBeNull();
    expect((input as HTMLInputElement).value).toBe('');
  });

  it('allows QA Lead to read but not save', async () => {
    mocks.role = 'qa_lead';
    render(<VlmSettingsModal onClose={vi.fn()} />);
    expect(await screen.findByLabelText('API key')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Lưu cấu hình VLM' })).toBeNull();
  });

  it('recovers from a failed load via reload', async () => {
    mocks.get.mockRejectedValueOnce(new Error('offline'));
    render(<VlmSettingsModal onClose={vi.fn()} />);
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Tải lại' }));
    expect(await screen.findByLabelText('Base URL')).toBeInTheDocument();
  });
});
