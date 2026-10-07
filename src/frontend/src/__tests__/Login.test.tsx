import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginPage from '@/app/login/page';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }), usePathname: () => '/login',
}));

async function mountLogin() {
  render(<AuthProvider><LoginPage /></AuthProvider>);
  await waitFor(() => expect((screen.getByRole('button', { name: /Đăng nhập vào LabelX/ }) as HTMLButtonElement).disabled).toBe(false));
}

describe('Login page', () => {
  it('offers all seven mock roles and fills a selected account', async () => {
    installMockAuthApi();
    await mountLogin();
    expect(screen.getByLabelText('Tên đăng nhập')).toBeDefined();
    expect(screen.getByRole('button', { name: /productowner/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /modelowner/ })).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /reviewer/ }));
    expect((screen.getByLabelText('Tên đăng nhập') as HTMLInputElement).value).toBe('reviewer');
    expect((screen.getByLabelText('Mật khẩu') as HTMLInputElement).value).toBe('password123');
  });

  it('shows the contract INVALID_CREDENTIALS message', async () => {
    installMockAuthApi();
    await mountLogin();
    fireEvent.change(screen.getByLabelText('Tên đăng nhập'), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'wrong_password' } });
    fireEvent.click(screen.getByRole('button', { name: /Đăng nhập vào LabelX/ }));
    expect(await screen.findByRole('alert')).toBeDefined();
    expect(screen.getByText('Tên đăng nhập hoặc mật khẩu không chính xác')).toBeDefined();
    expect(push).not.toHaveBeenCalled();
  });

  it('logs in through csrf then login and navigates to the shell', async () => {
    const api = installMockAuthApi();
    await mountLogin();
    fireEvent.click(screen.getByRole('button', { name: /reviewer/ }));
    fireEvent.click(screen.getByRole('button', { name: /Đăng nhập vào LabelX/ }));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/'));
    const paths = api.fetchSpy.mock.calls.map(([request]) => new URL(request.url).pathname);
    expect(paths).toEqual(['/api/auth/session/', '/api/auth/csrf/', '/api/auth/login/']);
    expect(api.jar.has('sessionid')).toBe(true);
  });

  it('does not grant a mock admin when the network fails', async () => {
    const api = installMockAuthApi();
    await mountLogin();
    api.fetchSpy.mockRejectedValue(new TypeError('Network unavailable'));
    fireEvent.click(screen.getByRole('button', { name: /^admin \(/ }));
    fireEvent.click(screen.getByRole('button', { name: /Đăng nhập vào LabelX/ }));
    expect(await screen.findByText('Không kết nối được máy chủ. Vui lòng thử lại.')).toBeDefined();
    expect(push).not.toHaveBeenCalled();
  });
}
);
