import React from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ProfileModal } from '@/components/layout/ProfileModal';
import { TopBar } from '@/components/layout/TopBar';

const mocks = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn(), remove: vi.fn() }));
vi.mock('@/lib/auth/profile-api', () => ({ getProfile: mocks.get, saveProfile: mocks.save, deleteProfileToken: mocks.remove }));
vi.mock('@/lib/auth/auth-context', () => ({ useAuth: () => ({ user: { fullName: 'Người dùng' }, logout: vi.fn(), hasPermission: () => false }) }));
vi.mock('next/navigation', () => ({ usePathname: () => '/' }));

beforeEach(() => {
  mocks.get.mockReset().mockResolvedValue({ cvat_token_configured: false, cvat_token_saved: false });
  mocks.save.mockReset().mockResolvedValue({ cvat_token_configured: true, cvat_token_saved: true });
  mocks.remove.mockReset().mockResolvedValue({ cvat_token_configured: false, cvat_token_saved: false });
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; this.dispatchEvent(new Event('close')); };
});

it('opens profile from the user menu and restores focus when dismissed', async () => {
  render(<TopBar />);
  const user = screen.getByRole('button', { name: /Người dùng/ });
  fireEvent.click(user);
  fireEvent.click(screen.getByRole('menuitem', { name: 'Hồ sơ' }));
  expect(screen.getByRole('dialog', { name: 'Hồ sơ' })).toBeInTheDocument();
  await screen.findByText('Chưa cấu hình token CVAT.');
  fireEvent.click(screen.getByRole('button', { name: 'Đóng' }));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.activeElement).toBe(user);
});

it('submits a masked token and clears it after saving', async () => {
  render(<ProfileModal onClose={vi.fn()} />);
  await screen.findByText('Chưa cấu hình token CVAT.');
  const input = screen.getByLabelText('CVAT_SERVICE_TOKEN');
  expect(input).toHaveAttribute('type', 'password');
  expect(screen.getByRole('button', { name: 'Lưu' })).toBeDisabled();
  fireEvent.change(input, { target: { value: 'personal-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu' }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledWith('personal-secret'));
  expect(await screen.findByText(/Đã lưu token CVAT/)).toBeInTheDocument();
  expect((input as HTMLInputElement).value).toBe('');
});

it('does not report success after a failed save and clears the input', async () => {
  mocks.save.mockRejectedValue(new Error('offline'));
  render(<ProfileModal onClose={vi.fn()} />);
  await screen.findByText('Chưa cấu hình token CVAT.');
  const input = screen.getByLabelText('CVAT_SERVICE_TOKEN');
  fireEvent.change(input, { target: { value: 'personal-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lưu' }));
  expect(await screen.findByRole('alert')).toBeInTheDocument();
  expect(screen.queryByText(/Đã lưu token CVAT/)).toBeNull();
  expect((input as HTMLInputElement).value).toBe('');
});

it('keeps existing credentials hidden and closes without saving an edit', async () => {
  mocks.get.mockResolvedValue({ cvat_token_configured: true, cvat_token_saved: true });
  const onClose = vi.fn();
  render(<ProfileModal onClose={onClose} />);
  await screen.findByText('Đã cấu hình token CVAT.');
  const input = screen.getByLabelText('CVAT_SERVICE_TOKEN');
  expect((input as HTMLInputElement).value).toBe('');
  fireEvent.change(input, { target: { value: 'discard-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Đóng' }));
  expect(onClose).toHaveBeenCalled();
  expect(mocks.save).not.toHaveBeenCalled();
});


it('shows the configured indicator and removes the saved token from the input', async () => {
  mocks.get.mockResolvedValue({ cvat_token_configured: true, cvat_token_saved: true });
  render(<ProfileModal onClose={vi.fn()} />);
  const status = await screen.findByText('Đã cấu hình token CVAT.');
  expect(status.className).toContain('is-configured');
  fireEvent.click(screen.getByRole('button', { name: 'Xóa token CVAT hiện tại' }));
  await waitFor(() => expect(mocks.remove).toHaveBeenCalledOnce());
  expect(await screen.findByText('Chưa cấu hình token CVAT.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Xóa token CVAT hiện tại' })).toBeNull();
});

it('keeps the stored token status after deletion fails', async () => {
  mocks.get.mockResolvedValue({ cvat_token_configured: true, cvat_token_saved: true });
  mocks.remove.mockRejectedValue(new Error('offline'));
  render(<ProfileModal onClose={vi.fn()} />);
  fireEvent.click(await screen.findByRole('button', { name: 'Xóa token CVAT hiện tại' }));
  expect(await screen.findByRole('alert')).toBeInTheDocument();
  expect(screen.getByText('Đã cấu hình token CVAT.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Xóa token CVAT hiện tại' })).not.toBeDisabled();
});

it('does not offer deletion of the deployment fallback', async () => {
  mocks.get.mockResolvedValue({ cvat_token_configured: true, cvat_token_saved: false });
  render(<ProfileModal onClose={vi.fn()} />);
  await screen.findByText('Đã cấu hình token CVAT.');
  expect(screen.queryByRole('button', { name: 'Xóa token CVAT hiện tại' })).toBeNull();
});
