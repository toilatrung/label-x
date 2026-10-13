import React from 'react';
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { BenchmarkBody, BenchmarkHeader } from '@/components/calibration/BenchmarkView';
import { AuditSamplingBody, AuditSamplingHeader } from '@/components/calibration/AuditSamplingView';
import { CalibrationBody, CalibrationHeader } from '@/components/calibration/CalibrationView';

import { canAccessCalibration } from '@/lib/auth/roles';

// Performance Evaluation đã nối API (MBE-01): kiểm thử ở PerformanceEvaluation.test.tsx.

describe('Benchmark', () => {
  it('lists three versions, marks v1.2 as locked and keeps write buttons without API', () => {
    render(<><BenchmarkHeader /><BenchmarkBody /></>);
    expect(screen.getAllByRole('row')).toHaveLength(4);
    expect(screen.getByText('Benchmark đã khoá không thể sửa. Cần thay đổi thì tạo phiên bản mới.')).toBeTruthy();
    expect(screen.queryByRole('status')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Tạo benchmark' }));
    expect(screen.queryByText(/thành công|đã tạo/i)).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
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

describe('Write actions', () => {
  it('does not expose implementation notices', () => {
    const { unmount } = render(<><AuditSamplingHeader /><AuditSamplingBody /></>);
    fireEvent.click(screen.getByRole('button', { name: 'Tạo mẫu mới' }));
    expect(screen.queryByRole('status')).toBeNull();
    unmount();
    render(<><CalibrationHeader /><CalibrationBody /></>);
    fireEvent.click(screen.getByRole('button', { name: 'Giao bài hiệu chỉnh' }));
    expect(screen.queryByRole('status')).toBeNull();
  });
});

describe('canAccessCalibration', () => {
  it('allows only the five roles in the design and blocks Product Owner and Data/Model Owner', () => {
    const allowed = ['annotator', 'reviewer', 'qa_lead', 'qc_admin', 'super_admin'] as const;
    allowed.forEach((r) => expect(canAccessCalibration(r)).toBe(true));
    (['product_owner', 'data_model_owner'] as const).forEach((r) => expect(canAccessCalibration(r)).toBe(false));
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
