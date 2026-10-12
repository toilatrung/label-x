import React from 'react';
import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { SampleDataBadge } from '@/components/ui/SampleDataBadge';

describe('NotConnectedNotice', () => {
  it('does not render an implementation notice', () => {
    const { container } = render(<NotConnectedNotice />);
    expect(container.innerHTML).toBe('');
  });
  it('does not expose implementation detail', () => {
    const { container } = render(<NotConnectedNotice detail="Chờ endpoint /api/reports" />);
    expect(container.innerHTML).toBe('');
  });
  it('does not label contract data as sample data', () => {
    const { container } = render(<SampleDataBadge />);
    expect(container.innerHTML).toBe('');
  });
});
