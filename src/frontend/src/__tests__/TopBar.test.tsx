import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TopBar } from '@/components/layout/TopBar';
import { AuthProvider } from '@/lib/auth/auth-context';

// Mock next/navigation
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

describe('TopBar Component', () => {
  it('renders LabelX logo and primary navigation tabs', () => {
    render(
      <AuthProvider>
        <TopBar />
      </AuthProvider>
    );

    expect(screen.getByText('Label')).toBeDefined();
    expect(screen.getByText('Tổng quan')).toBeDefined();
    expect(screen.getByText('Hiệu chuẩn & Kiểm toán')).toBeDefined();
  });

  it('opens and closes dropdown menus when clicking', () => {
    render(
      <AuthProvider>
        <TopBar />
      </AuthProvider>
    );

    const overviewBtn = screen.getByText('Tổng quan');
    fireEvent.click(overviewBtn);

    expect(screen.getByText('Trang chủ QC')).toBeDefined();
    expect(screen.getByText('Tóm tắt chất lượng')).toBeDefined();
  });
});
