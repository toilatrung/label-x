import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginPage from '@/app/login/page';
import { AuthProvider } from '@/lib/auth/auth-context';

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => '/login',
}));

describe('LoginPage Component', () => {
  it('renders login form and mock user quick-pick buttons', () => {
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    expect(screen.getByLabelText('Tên đăng nhập')).toBeDefined();
    expect(screen.getByLabelText('Mật khẩu')).toBeDefined();
    expect(screen.getByRole('button', { name: /Đăng nhập vào LabelX/i })).toBeDefined();
    expect(screen.getByText(/Tài khoản mẫu thử nghiệm/i)).toBeDefined();
  });

  it('fills inputs when clicking quick pick button', () => {
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    const reviewerPick = screen.getByRole('button', { name: /reviewer/i });
    fireEvent.click(reviewerPick);

    const usernameInput = screen.getByLabelText('Tên đăng nhập') as HTMLInputElement;
    const passwordInput = screen.getByLabelText('Mật khẩu') as HTMLInputElement;

    expect(usernameInput.value).toBe('reviewer');
    expect(passwordInput.value).toBe('password123');
  });

  it('displays error message on incorrect password', async () => {
    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    );

    const usernameInput = screen.getByLabelText('Tên đăng nhập');
    const passwordInput = screen.getByLabelText('Mật khẩu');
    const submitBtn = screen.getByRole('button', { name: /Đăng nhập vào LabelX/i });

    fireEvent.change(usernameInput, { target: { value: 'admin' } });
    fireEvent.change(passwordInput, { target: { value: 'wrong_password' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Tên đăng nhập hoặc mật khẩu không chính xác/i)).toBeDefined();
    });
  });
});
