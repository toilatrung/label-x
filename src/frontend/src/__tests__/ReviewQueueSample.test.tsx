import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ReviewQueueSample } from '@/components/review/ReviewQueueSample';

const NOTICE = 'Chức năng vẫn chưa được kết nối với server';

describe('ReviewQueueSample (ReviewQueues.dc.html)', () => {
  it('shows three sample frames with the sample label and the not-connected notice', () => {
    render(<ReviewQueueSample />);
    expect(screen.getByText('Dữ liệu minh họa')).toBeTruthy();
    expect(screen.getAllByRole('status').some((n) => n.textContent === NOTICE)).toBe(true);
    expect(screen.getAllByRole('article')).toHaveLength(3);
    expect(screen.getByText('3 ảnh')).toBeTruthy();
    expect(screen.getByText('1–3 / 3')).toBeTruthy();
  });
  it('filters by search, priority and alert type, and resets from the empty state', () => {
    render(<ReviewQueueSample />);
    fireEvent.change(screen.getByLabelText('Mức ưu tiên'), { target: { value: 'Cao' } });
    expect(screen.getAllByRole('article')).toHaveLength(1);
    fireEvent.change(screen.getByLabelText('Loại cảnh báo'), { target: { value: 'Hộp lệch' } });
    expect(screen.queryAllByRole('article')).toHaveLength(0);
    expect(screen.getByText('Không có ảnh khớp bộ lọc.')).toBeTruthy();
    expect(screen.getByText('0 / 0')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Xóa bộ lọc' }));
    expect(screen.getAllByRole('article')).toHaveLength(3);
    fireEvent.change(screen.getByLabelText('Tìm ảnh hoặc mã công việc'), { target: { value: '5678' } });
    expect(screen.getAllByRole('article')).toHaveLength(1);
  });
  it('blocks Bắt đầu kiểm tra without calling any API', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    render(<ReviewQueueSample />);
    fireEvent.click(screen.getByRole('button', { name: 'Bắt đầu kiểm tra Ảnh 001' }));
    expect(screen.getAllByText(NOTICE)).toHaveLength(1);
    const attention = screen.getByText(NOTICE).closest('[data-attention]') as HTMLElement;
    expect(attention).toBeTruthy();
    expect(document.activeElement).toBe(attention);
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
