import React from 'react';
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ReviewQueueSample } from '@/components/review/ReviewQueueSample';

describe('ReviewQueueSample (ReviewQueues.dc.html)', () => {
  it('shows the three design frames without implementation notices', () => {
    render(<ReviewQueueSample />);
    expect(screen.queryByText(/kết nối với server/)).toBeNull();
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
  it('links the design action to its workspace route', () => {
    render(<ReviewQueueSample />);
    const action = screen.getByRole('link', { name: 'Bắt đầu kiểm tra Ảnh 001' });
    expect(action.getAttribute('href')).toBe('/review/workspace?frame_id=001234');
  });
});
