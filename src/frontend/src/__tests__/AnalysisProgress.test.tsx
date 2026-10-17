import React from 'react';
import { expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AnalysisProgress } from '@/components/execution/AnalysisProgress';
import type { Run, LedgerEntry } from '@/lib/execution/api';

const base = { id: 5, status: 'running', engines: [
  { engine: 'detector', status: 'checked', failed_units: 0 },
  { engine: 'vlm', status: 'running', failed_units: 0 },
] } as Run;

it('shows preparation without claiming a VLM provider call or 100% completion', () => {
  render(<AnalysisProgress run={base} ledger={[]} />);
  expect(screen.getByText(/Đang chuẩn bị VLM/)).toBeDefined();
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('50');
});
it('weights engine progress separately rather than mixing frame and candidate units', () => {
  render(<AnalysisProgress run={base} ledger={[{ engine: 'vlm', total: 100, completed: 20, failed: 10, pending: 70, not_checked: 0 } as LedgerEntry]} />);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('65');
  expect(screen.getByText(/20 hoàn tất · 10 lỗi · 70/)).toBeDefined();
});
it('keeps active runs below 100% until the server closes them', () => {
  render(<AnalysisProgress run={{ ...base, engines: base.engines.map(engine => ({ ...engine, status: 'checked' })) }} ledger={[]} />);
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('99');
  expect(screen.getByText('Đang chốt kết quả phân tích')).toBeDefined();
});
it('labels partial completion as an error outcome rather than a successful analysis', () => {
  render(<AnalysisProgress run={{ ...base, status: 'partial', engines: [base.engines[0], { engine: 'vlm', status: 'failed', failed_units: 10 }] }} ledger={[]} />);
  expect(screen.getByText('Đã kết thúc · Kết quả một phần')).toBeDefined();
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('100');
  expect(screen.getByRole('alert').textContent).toContain('VLM');
});
it('shows a cancelled run separately and makes progress-fetch errors visible', () => {
  render(<AnalysisProgress run={{ ...base, status: 'cancelled' }} error="Không kết nối" />);
  expect(screen.getByText('Đã dừng phân tích')).toBeDefined();
  expect(screen.getByRole('alert').textContent).toContain('Không kết nối');
});

it('does not show all engines finished while the VLM ledger still has a pending unit', () => {
  const run = { ...base, status: 'partial', engines: base.engines.map(engine => ({ ...engine, status: 'checked' })) } as Run;
  const { rerender } = render(<AnalysisProgress run={run} ledger={[{ engine: 'vlm', total: 5, completed: 4, failed: 0, pending: 1, not_checked: 0 } as LedgerEntry]} />);
  expect(screen.getByText('1/2 engine đã xử lý')).toBeDefined();
  expect(screen.getByText('Đang xử lý: VLM')).toBeDefined();
  expect(Number(screen.getByRole('progressbar').getAttribute('aria-valuenow'))).toBeLessThan(100);
  rerender(<AnalysisProgress run={run} ledger={[{ engine: 'vlm', total: 5, completed: 5, failed: 0, pending: 0, not_checked: 0 } as LedgerEntry]} />);
  expect(screen.getByText('2/2 engine đã xử lý')).toBeDefined();
  expect(screen.getByText(/5 hoàn tất · 0 lỗi · 0/)).toBeDefined();
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('100');
});

it('shows durable retry status and keeps an outage visible', () => {
  render(<AnalysisProgress run={{ ...base, engines: [base.engines[0], {
    ...base.engines[1], progress: { phase: 'waiting_retry', pending: 5, skipped: 0, failed: 1,
      provider_calls: 4, stale: false, retry_at: '2026-10-15T13:00:00Z' },
  }] }} ledger={[]} error="offline" />);
  expect(screen.getByText(/Thử lại lúc/)).toBeDefined();
  expect(screen.getByRole('progressbar').classList.contains('lx-progress--active')).toBe(false);
  expect(screen.getByText(/4 lượt gọi đã ghi nhận/)).toBeDefined();
});

it('pauses activity when the last successful poll is stale', () => {
  render(<AnalysisProgress run={base} ledger={[]} updatedAt={Date.now() - 60_000} />);
  expect(screen.getByText(/Chưa nhận được cập nhật mới/)).toBeDefined();
  expect(screen.getByRole('progressbar').classList.contains('lx-progress--active')).toBe(false);
});
