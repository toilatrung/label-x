import React from 'react';
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QualityReportBody, QualityReportHeader } from '@/components/reports/QualityReportView';
import { QualityGateBody } from '@/components/reports/QualityGateView';
import { ReleaseHistoryBody } from '@/components/reports/ReleaseHistoryView';

const NOTICE = 'Chức năng vẫn chưa được kết nối với server';

describe('Quality Report', () => {
  it('renders the standard metrics with sample-data label and notice', () => {
    render(<><QualityReportHeader /><QualityReportBody /></>);
    expect(screen.getByText('12,500')).toBeTruthy();
    expect(screen.getByText('92.4%')).toBeTruthy();
    expect(screen.getByText('Dữ liệu minh họa')).toBeTruthy();
    expect(screen.getByRole('status').textContent).toBe(NOTICE);
  });
  it('switches tabs and keeps Polyline as not evaluated', () => {
    render(<QualityReportBody />);
    fireEvent.click(screen.getByRole('tab', { name: 'Theo lớp và loại hình' }));
    const row = screen.getByText('lane marking').closest('tr')!;
    expect(within(row).getAllByText('—').length).toBe(3);
    fireEvent.click(screen.getByRole('tab', { name: 'Nguyên nhân gốc' }));
    expect(screen.getByText('Phê duyệt GAP-012')).toBeTruthy();
  });
  it('opens the export menu without reporting success', () => {
    render(<QualityReportHeader />);
    fireEvent.click(screen.getByRole('button', { name: /Xuất báo cáo/ }));
    expect(screen.getAllByRole('menuitem').map((i) => i.textContent)).toHaveLength(3);
    expect(screen.queryByText(/thành công/i)).toBeNull();
  });
  it('emphasizes the existing notice when an export format is chosen, without adding a second one', () => {
    render(<><QualityReportHeader /><QualityReportBody /></>);
    expect(screen.getAllByText(NOTICE)).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: /Xuất báo cáo/ }));
    fireEvent.click(screen.getByRole('menuitem', { name: /PDF/ }));
    expect(screen.getAllByText(NOTICE)).toHaveLength(1);
    const wrapper = screen.getByText(NOTICE).closest('[data-attention]') as HTMLElement;
    expect(wrapper).toBeTruthy();
    expect(document.activeElement).toBe(wrapper);
    expect(screen.queryByRole('menu')).toBeNull();
  });
  it('closes the export menu on Escape and on an outside click', () => {
    render(<><QualityReportHeader /><p>Bên ngoài</p></>);
    const trigger = screen.getByRole('button', { name: /Xuất báo cáo/ });
    fireEvent.click(trigger);
    expect(screen.getByRole('menu')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    fireEvent.click(trigger);
    fireEvent.mouseDown(screen.getByText('Bên ngoài'));
    expect(screen.queryByRole('menu')).toBeNull();
  });
});

describe('Quality Gate', () => {
  it('lists six conditions and keeps approval disabled', () => {
    render(<QualityGateBody />);
    expect(screen.getAllByRole('row')).toHaveLength(7);
    expect(screen.getByText('2 đạt · 3 chưa đạt · 1 chờ phê duyệt')).toBeTruthy();
    expect((screen.getByRole('button', { name: 'Phê duyệt phát hành' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByRole('status').length).toBe(2);
  });
  it('does not claim the waiver was sent', () => {
    render(<QualityGateBody />);
    fireEvent.change(screen.getByLabelText('Lý do (bắt buộc)'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi xin waiver' }));
    expect(screen.queryByText(/đã gửi|thành công/i)).toBeNull();
    expect(screen.getAllByText(NOTICE)).toHaveLength(2);
    expect(screen.getAllByText(NOTICE).map((n) => n.closest('[data-attention]')).filter(Boolean)).toHaveLength(1);
  });
});

describe('Release History', () => {
  it('shows four releases and the v1.3 manifest, blocked row without approver', () => {
    render(<ReleaseHistoryBody />);
    expect(screen.getByText('Road Vision Urban v1.4').closest('tr')!.textContent).toContain('Blocked');
    expect(screen.getByText('Manifest · v1.3')).toBeTruthy();
    expect(screen.getByText('SNP-011')).toBeTruthy();
    expect(screen.getAllByRole('status').length).toBe(2);
    fireEvent.click(screen.getByRole('button', { name: 'Tải manifest (JSON)' }));
    expect(screen.getAllByRole('status').length).toBe(2);
    expect(document.querySelectorAll('[data-attention]')).toHaveLength(1);
  });
});
