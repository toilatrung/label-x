import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { VlmSettingsModal } from '@/components/configuration/VlmSettingsModal';
import { ModelsGuidelinesCard } from '@/components/configuration/ModelsGuidelinesCard';

const mocks = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), role: 'qc_admin' }));
vi.mock('@/lib/auth/auth-context', () => ({ useAuth: () => ({ hasPermission: (check: (role: string) => boolean) => check(mocks.role) }) }));
vi.mock('@/lib/configuration/vlm-api', () => ({ getVlmSettings: mocks.get, saveVlmSettings: mocks.save }));

const settings = { revision: 7, base_url: 'https://api.shopaikey.com/v1', model: 'qwen3-vl-plus' as const, api_key_configured: true, confidence_threshold: 0.85 };

beforeEach(() => {
  mocks.role = 'qc_admin'; mocks.get.mockReset().mockResolvedValue(settings); mocks.save.mockReset().mockResolvedValue({ ...settings, revision: 8 });
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new Event('close')); };
});

describe('VLM settings', () => {
  it('saves the routing confidence threshold and updates the model row', async () => {
    mocks.save.mockResolvedValue({ ...settings, revision: 8, confidence_threshold: 0.60 });
    render(<ModelsGuidelinesCard />);
    const row = screen.getByRole('row', { name: /Mô hình thị giác – ngôn ngữ/ });
    expect(await within(row).findByText('0.85')).toBeInTheDocument();
    fireEvent.click(within(row).getByRole('button', { name: 'Chỉnh mô hình' }));
    fireEvent.change(await screen.findByLabelText('Ngưỡng tin cậy gọi VLM'), { target: { value: '0.60' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu cấu hình VLM' }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ confidence_threshold: 0.60 })));
    expect(await within(row).findByText('0.60')).toBeInTheDocument();
  });

  it('reload restores the saved threshold and discards unsaved key and endpoint', async () => {
    render(<VlmSettingsModal onClose={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText('Ngưỡng tin cậy gọi VLM'), { target: { value: '0.50' } });
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1' } });
    fireEvent.change(screen.getByLabelText('API key'), { target: { value: 'discard-secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tải lại' }));
    expect((await screen.findByLabelText('Ngưỡng tin cậy gọi VLM') as HTMLInputElement).value).toBe('0.85');
    expect((screen.getByLabelText('Base URL') as HTMLInputElement).value).toBe(settings.base_url);
    expect((screen.getByLabelText('API key') as HTMLInputElement).value).toBe('');
    expect(mocks.save).not.toHaveBeenCalled();
  });

  it('keeps VLM in the model table and opens its settings only from edit', async () => {
    render(<ModelsGuidelinesCard />);
    const row = screen.getByRole('row', { name: /Mô hình thị giác – ngôn ngữ/ });
    expect(screen.queryByLabelText('API key')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.get).toHaveBeenCalledTimes(1);
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
    expect(mocks.get).toHaveBeenCalledTimes(1);
  });

  it('loads metadata and preserves the key when left blank', async () => {
    render(<VlmSettingsModal onClose={vi.fn()} />);
    const input = await screen.findByLabelText('API key');
    expect((input as HTMLInputElement).value).toBe('');
    expect(input).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByRole('button', { name: 'Lưu cấu hình VLM' }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith({ expected_revision: 7, base_url: settings.base_url, model: settings.model, confidence_threshold: 0.85 }));
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
