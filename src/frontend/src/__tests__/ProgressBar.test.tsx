import React from 'react';
import { render, screen } from '@testing-library/react';
import { it, expect } from 'vitest';
import { ProgressBar } from '@/components/execution/ProgressBar';

it('animates a running operation without changing its actual percentage', () => {
  const { rerender } = render(<ProgressBar label="engine" value={25} active />);
  const bar = screen.getByRole('progressbar');
  expect(bar.classList.contains('lx-progress--active')).toBe(true);
  expect(bar.getAttribute('aria-valuenow')).toBe('25');
  rerender(<ProgressBar label="engine" value={25} active paused />);
  expect(bar.classList.contains('lx-progress--active')).toBe(false);
  expect(bar.getAttribute('aria-valuenow')).toBe('25');
  expect(bar.getAttribute('aria-valuetext')).toContain('Chưa cập nhật');
});
it('uses indeterminate animation without claiming a percentage', () => {
  render(<ProgressBar label="engine" active />);
  expect(screen.getByRole('progressbar').hasAttribute('aria-valuenow')).toBe(false);
  expect(screen.getByRole('progressbar').classList.contains('lx-progress--indeterminate')).toBe(true);
});
it('stops motion when the operation has ended', () => {
  render(<ProgressBar label="engine" value={100} warning />);
  expect(screen.getByRole('progressbar').classList.contains('lx-progress--active')).toBe(false);
});
