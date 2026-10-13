import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ReviewWorkspaceEmpty } from '@/components/review/ReviewWorkspaceEmpty';

describe('ReviewWorkspaceEmpty (route không có frame_id)', () => {
  it('hướng người dùng về hàng đợi, không dựng frame minh họa giả', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    render(<ReviewWorkspaceEmpty />);
    expect(screen.getByRole('heading', { name: 'Chưa có frame để review' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Về hàng đợi' }).getAttribute('href')).toBe('/review');
    // Không còn dữ liệu minh họa (QC-00128, CASE-021, quyết định giả) hay form ghi.
    expect(screen.queryByText(/QC-00128/)).toBeNull();
    expect(screen.queryByText(/CASE-021/)).toBeNull();
    expect(screen.queryAllByRole('radio')).toHaveLength(0);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
