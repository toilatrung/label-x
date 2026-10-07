import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { ContextBar } from '@/components/layout/ContextBar';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

describe('Dataset context', () => {
  it('does not invent dataset 1 for a global admin session', async () => {
    const api = installMockAuthApi();
    await api.signIn('admin');
    render(<AuthProvider><ContextBar /></AuthProvider>);
    await screen.findByText('Super Admin');
    const chip = screen.getByText('Dataset:').closest('div')!;
    expect(within(chip).getByText('Chưa chọn')).toBeDefined();
    expect(screen.queryByText(/Dataset.*#1/)).toBeNull();
    expect(screen.queryByText('Phạm vi:')).toBeNull();
  });

  it('uses an explicit dataset grant from the session', async () => {
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    render(<AuthProvider><ContextBar /></AuthProvider>);
    await screen.findByText('Reviewer');
    const chip = screen.getByText('Dataset:').closest('div')!;
    expect(within(chip).getByText('Dataset mẫu #1')).toBeDefined();
  });
});
