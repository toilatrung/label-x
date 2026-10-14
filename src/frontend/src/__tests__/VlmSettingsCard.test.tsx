import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { VlmSettingsCard } from '@/components/configuration/VlmSettingsCard';

const mocks = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), role: 'qc_admin' }));
vi.mock('@/lib/auth/auth-context', () => ({ useAuth: () => ({ hasPermission: (check: (role: string) => boolean) => check(mocks.role) }) }));
vi.mock('@/lib/configuration/vlm-api', () => ({ getVlmSettings: mocks.get, saveVlmSettings: mocks.save }));

const settings = { revision: 7, base_url: 'https://api.shopaikey.com/v1', model: 'qwen3-vl-plus' as const, api_key_configured: true };

beforeEach(() => { mocks.role = 'qc_admin'; mocks.get.mockResolvedValue(settings); mocks.save.mockResolvedValue({ ...settings, revision: 8 }); });

describe('VLM settings', () => {
  it('loads metadata and preserves the key when left blank', async () => {
    render(<VlmSettingsCard />);
    const input = await screen.findByLabelText('API key');
    expect((input as HTMLInputElement).value).toBe('');
    expect(input).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByRole('button', { name: 'Lưu cấu hình VLM' }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith({ expected_revision: 7, base_url: settings.base_url, model: settings.model }));
    expect(await screen.findByText(/Đã lưu cấu hình VLM/)).toBeInTheDocument();
  });

  it('submits a replacement key and clears it after save', async () => {
    render(<VlmSettingsCard />);
    const input = await screen.findByLabelText('API key');
    fireEvent.change(input, { target: { value: 'replacement-secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu cấu hình VLM' }));
    await waitFor(() => expect(mocks.save).toHaveBeenCalledWith(expect.objectContaining({ api_key: 'replacement-secret' })));
    await screen.findByText(/Đã lưu cấu hình VLM/);
    expect((input as HTMLInputElement).value).toBe('');
  });

  it('requires a new key when changing the endpoint', async () => {
    render(<VlmSettingsCard />);
    const input = await screen.findByLabelText('API key');
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1' } });
    expect(input).toHaveAttribute('required');
  });

  it('shows conflicts without reporting success and clears the key', async () => {
    mocks.save.mockRejectedValue(new Error('Cấu hình đã đổi'));
    render(<VlmSettingsCard />);
    const input = await screen.findByLabelText('API key');
    fireEvent.change(input, { target: { value: 'private-secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu cấu hình VLM' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText(/Đã lưu cấu hình VLM/)).toBeNull();
    expect((input as HTMLInputElement).value).toBe('');
  });

  it('allows QA Lead to read but not save', async () => {
    mocks.role = 'qa_lead';
    render(<VlmSettingsCard />);
    expect(await screen.findByLabelText('API key')).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Lưu cấu hình VLM' })).toBeNull();
  });

  it('recovers from a failed load via reload', async () => {
    mocks.get.mockRejectedValueOnce(new Error('offline'));
    render(<VlmSettingsCard />);
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Tải lại' }));
    expect(await screen.findByLabelText('Base URL')).toBeInTheDocument();
  });
});
