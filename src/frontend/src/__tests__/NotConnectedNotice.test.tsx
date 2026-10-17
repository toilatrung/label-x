import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { NotConnectedNotice, NOT_CONNECTED_MESSAGE } from '@/components/ui/NotConnectedNotice';
import { SampleDataBadge } from '@/components/ui/SampleDataBadge';

describe('NotConnectedNotice', () => {
  it('shows the exact message as a status region', () => {
    render(<NotConnectedNotice />);
    expect(screen.getByRole('status').textContent).toBe('Chức năng vẫn chưa được kết nối với server');
    expect(NOT_CONNECTED_MESSAGE).toBe('Chức năng vẫn chưa được kết nối với server');
  });
  it('appends optional detail', () => {
    render(<NotConnectedNotice detail="Chờ endpoint /api/reports" />);
    expect(screen.getByRole('status').textContent).toContain('Chờ endpoint /api/reports');
  });
  it('renders the sample data badge', () => {
    render(<SampleDataBadge />);
    expect(screen.getByText('Dữ liệu minh họa')).toBeTruthy();
  });
});
