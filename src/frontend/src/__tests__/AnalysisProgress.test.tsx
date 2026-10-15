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
