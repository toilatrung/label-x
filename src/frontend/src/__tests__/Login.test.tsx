import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginPage from '@/app/login/page';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

const { push, replace } = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace }), usePathname: () => '/login',
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
    expect(await screen.findByRole('button', { name: /productowner/ })).toBeDefined();
    expect(screen.getByRole('button', { name: /modelowner/ })).toBeDefined();
    fireEvent.click(screen.getByRole('button', { name: /reviewer/ }));
    expect((screen.getByLabelText('Tên đăng nhập') as HTMLInputElement).value).toBe('reviewer');
    expect((screen.getByLabelText('Mật khẩu') as HTMLInputElement).value).toBe('password123');
  });

  it('loads demo accounts from the dev-only route, not from the client bundle', async () => {
    const api = installMockAuthApi();
    await mountLogin();
    await screen.findByRole('button', { name: /productowner/ });
    const paths = api.fetchSpy.mock.calls.map(([request]) => new URL(request.url).pathname);
    expect(paths).toContain('/api/auth/mock-users/');
  });

  it('hides demo accounts when the mock route is unavailable', async () => {
    const api = installMockAuthApi();
    const passthrough = api.fetchSpy.getMockImplementation()!;
    api.fetchSpy.mockImplementation(async (request: Request) => new URL(request.url).pathname === '/api/auth/mock-users/'
      ? new Response(JSON.stringify({ code: 'NOT_FOUND', message: 'API mẫu chưa được bật.' }), { status: 404 })
      : passthrough(request));
    await mountLogin();
    await waitFor(() => expect(api.fetchSpy.mock.calls.some(([request]) =>
      new URL(request.url).pathname === '/api/auth/mock-users/')).toBe(true));
    expect(screen.queryByText(/Tài khoản mẫu thử nghiệm/)).toBeNull();
    expect(screen.queryByRole('button', { name: /productowner/ })).toBeNull();
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
    fireEvent.click(await screen.findByRole('button', { name: /reviewer/ }));
    fireEvent.click(screen.getByRole('button', { name: /Đăng nhập vào LabelX/ }));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/'));
    expect(push).toHaveBeenCalledOnce();
    const paths = api.fetchSpy.mock.calls.map(([request]) => new URL(request.url).pathname)
      .filter((path) => path !== '/api/auth/mock-users/');
    expect(paths).toEqual(['/api/auth/session/', '/api/auth/csrf/', '/api/auth/login/']);
    expect(api.jar.has('sessionid')).toBe(true);
  });

  it('does not grant a mock admin when the network fails', async () => {
    const api = installMockAuthApi();
    await mountLogin();
    api.fetchSpy.mockRejectedValue(new TypeError('Network unavailable'));
    fireEvent.click(await screen.findByRole('button', { name: /^admin \(/ }));
    fireEvent.click(screen.getByRole('button', { name: /Đăng nhập vào LabelX/ }));
    expect(await screen.findByText('Không kết nối được máy chủ. Vui lòng thử lại.')).toBeDefined();
    expect(push).not.toHaveBeenCalled();
  });

  it('shows the session network error after the guard redirects to login', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Network unavailable')));
    const view = render(<AuthProvider><AuthGuard><div>Nội dung bảo vệ</div></AuthGuard></AuthProvider>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/login'));
    // Route navigation keeps the root AuthProvider and its session error mounted.
    view.rerender(<AuthProvider><LoginPage /></AuthProvider>);
    expect((await screen.findByRole('alert')).textContent)
      .toBe('Không kết nối được máy chủ. Vui lòng thử lại.');
    expect(push).not.toHaveBeenCalled();
  });
}
);
