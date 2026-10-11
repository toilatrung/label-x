import React from 'react';
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { PerformanceBody, PerformanceHeader } from '@/components/calibration/PerformanceView';
import { BenchmarkBody, BenchmarkHeader } from '@/components/calibration/BenchmarkView';
import { AuditSamplingBody, AuditSamplingHeader } from '@/components/calibration/AuditSamplingView';
import { CalibrationBody, CalibrationHeader } from '@/components/calibration/CalibrationView';

const NOTICE = 'Chức năng vẫn chưa được kết nối với server';

describe('Performance Evaluation', () => {
  it('shows standard figures, sample label and notice', () => {
    render(<><PerformanceHeader /><PerformanceBody /></>);
    expect(screen.getByText('94.1%')).toBeTruthy();
    expect(screen.getByText('Dữ liệu minh họa')).toBeTruthy();
    expect(screen.getByRole('status').textContent).toBe(NOTICE);
    expect(screen.getAllByRole('row')).toHaveLength(4);
    expect(screen.getByRole('img', { name: '76%' })).toBeTruthy();
  });
});

describe('Benchmark', () => {
  it('lists three versions, marks v1.2 as locked and keeps write buttons without API', () => {
    render(<><BenchmarkHeader /><BenchmarkBody /></>);
    expect(screen.getAllByRole('row')).toHaveLength(4);
    expect(screen.getByText('Benchmark đã khoá không thể sửa. Cần thay đổi thì tạo phiên bản mới.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Tạo benchmark' }));
    expect(screen.queryByText(/thành công|đã tạo/i)).toBeNull();
  });
});

describe('Audit Sampling', () => {
  it('switches between random and risk streams', () => {
    render(<><AuditSamplingHeader /><AuditSamplingBody /></>);
    expect(screen.getByText('20261004')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Lấy mẫu theo rủi ro' }));
    expect(screen.getByText(/không dùng để ước lượng chất lượng chung/)).toBeTruthy();
    expect(screen.getByText('42.5%')).toBeTruthy();
  });
});

describe('Calibration', () => {
  it('keeps reviewer and model tabs separate; unevaluated class shows dashes and warning', () => {
    render(<><CalibrationHeader /><CalibrationBody /></>);
    expect(screen.getByText('Bình Hồ')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Hiệu chỉnh mô hình' }));
    const row = screen.getByText('motorbike').closest('tr')!;
    expect(within(row).getAllByText('—')).toHaveLength(2);
    expect(within(row).getByText('Không đủ mẫu để đánh giá')).toBeTruthy();
    expect(screen.queryByText('Bình Hồ')).toBeNull();
  });
});
