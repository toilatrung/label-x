import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ReviewWorkspaceSample } from '@/components/review/ReviewWorkspaceSample';

describe('ReviewWorkspaceSample (thiết kế ReviewWorkspace.dc.html)', () => {
  it('shows sample badge, not-connected notice and all five decisions', () => {
    render(<ReviewWorkspaceSample />);
    expect(screen.getByText('Dữ liệu minh họa')).toBeTruthy();
    expect(screen.getByRole('status').textContent).toContain('Chức năng vẫn chưa được kết nối với server');
    const labels = screen.getAllByRole('radio').map((r) => r.parentElement?.textContent);
    expect(labels).toEqual(['Xác nhận lỗi', 'Bác bỏ', 'Chưa chắc chắn', 'Yêu cầu sửa', 'Chuyển cấp trên']);
    expect(screen.getByLabelText('Loại lỗi đã xác nhận')).toBeTruthy();
    expect(screen.getByLabelText('Mức độ')).toBeTruthy();
    expect(screen.getByLabelText('Lý do')).toBeTruthy();
    expect(screen.getByText('Case tương tự đã phân xử (3)')).toBeTruthy();
  });

  it('switches Issue Review / Frame Review hints', () => {
    render(<ReviewWorkspaceSample />);
    expect(screen.getByText(/Đường liền: annotation hiện tại/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Frame Review' }));
    expect(screen.getByText('Nhấn vào một object để tạo issue mới.')).toBeTruthy();
  });

  it('blocks save without calling any API', () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    render(<ReviewWorkspaceSample />);
    fireEvent.click(screen.getByRole('button', { name: /Lưu và chuyển issue tiếp/ }));
    expect(screen.getByRole('status').textContent).toContain('chưa được lưu');
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it('gives each blocked button its own message', () => {
    render(<ReviewWorkspaceSample />);
    const status = () => screen.getByRole('status').textContent;
    fireEvent.click(screen.getByRole('button', { name: 'Mở trong CVAT' }));
    expect(status()).toContain('chưa mở được CVAT');
    expect(status()).not.toContain('Quyết định');
    fireEvent.click(screen.getByRole('button', { name: /Frame sau/ }));
    expect(status()).toContain('Chưa chuyển frame');
    fireEvent.click(screen.getByRole('button', { name: /Issue trước/ }));
    expect(status()).toContain('Chưa chuyển issue');
    expect(status()).not.toContain('Quyết định');
  });
});
