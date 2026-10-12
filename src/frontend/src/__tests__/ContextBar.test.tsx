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
    const chip = screen.getByText('Dataset').closest('div')!;
    expect(within(chip).getByText('Chưa chọn')).toBeDefined();
    expect(screen.queryByText(/Dataset.*#1/)).toBeNull();
    expect(screen.queryByText('Phạm vi')).toBeNull();
  });

  it('uses an explicit dataset grant from the session', async () => {
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    render(<AuthProvider><ContextBar /></AuthProvider>);
    await screen.findByText('Reviewer');
    const chip = screen.getByText('Dataset').closest('div')!;
    expect(within(chip).getByText('Dataset mẫu #1')).toBeDefined();
  });

  it('shows Phạm vi once a dataset is selected and keeps the Snapshot chip locked', async () => {
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    render(<AuthProvider><ContextBar snapshotName="SNP-011" snapshotRevision="rev f02a6d" /></AuthProvider>);
    await screen.findByText('Reviewer');
    expect(screen.getByText('Phạm vi')).toBeDefined();
    expect(screen.getByText('Toàn dataset')).toBeDefined();
    expect(screen.getByText('rev f02a6d')).toBeDefined();
    expect(screen.getByRole('img', { name: 'Đã khoá' })).toBeDefined();
  });

  it('marks the Quality Control Run state with a labelled dot and shows the read-only tag', async () => {
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    render(<AuthProvider><ContextBar activeRun="#QC-077" runState="partial" isReadOnly /></AuthProvider>);
    await screen.findByText('Reviewer');
    expect(screen.getByRole('img', { name: 'Trạng thái run: Partial' })).toBeDefined();
    expect(screen.getByText('read-only')).toBeDefined();
    expect(screen.getByText('Guideline')).toBeDefined();
    expect(screen.getByText('Taxonomy')).toBeDefined();
  });
});
