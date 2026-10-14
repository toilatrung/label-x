import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReviewVolumeChart, defaultVolumeQuery, fillPeriods, todayInServerTz } from '@/components/overview/ReviewVolumeChart';

const wrap = (node: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{node}</QueryClientProvider>);

describe('review volume helpers', () => {
  it('uses the backend day (Asia/Ho_Chi_Minh) for the default 14-day range', () => {
    // 2026-10-13T18:00Z là 01:00 ngày 14/10 ở Việt Nam.
    expect(todayInServerTz(new Date('2026-10-13T18:00:00Z'))).toBe('2026-10-14');
    expect(defaultVolumeQuery(new Date('2026-10-13T18:00:00Z'))).toEqual({ granularity: 'day', date_from: '2026-10-01', date_to: '2026-10-14' });
  });

  it('fills empty days and weeks with zero so the time axis keeps its length', () => {
    const day = fillPeriods({ run_id: 1, granularity: 'day', points: [{ period_start: '2026-10-02', frames_reviewed: 5, decisions: 6 }] },
      { granularity: 'day', date_from: '2026-10-01', date_to: '2026-10-03' });
    expect(day).toEqual([{ period: '2026-10-01', frames: 0, decisions: 0 }, { period: '2026-10-02', frames: 5, decisions: 6 },
      { period: '2026-10-03', frames: 0, decisions: 0 }]);
    // 2026-10-01 là thứ Tư: tuần đầu bắt đầu thứ Hai 2026-09-28 như TruncWeek.
    const week = fillPeriods({ run_id: 1, granularity: 'week', points: [{ period_start: '2026-10-05', frames_reviewed: 9, decisions: 9 }] },
      { granularity: 'week', date_from: '2026-10-01', date_to: '2026-10-14' });
    expect(week.map(row => row.period)).toEqual(['2026-09-28', '2026-10-05', '2026-10-12']);
    expect(week[1].frames).toBe(9);
  });
});

describe('ReviewVolumeChart (Dashboard.dc.html · Khối lượng review)', () => {
  let queries: URLSearchParams[];
  beforeEach(() => {
    queries = [];
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
      const url = new URL(request.url);
      expect(url.pathname).toBe('/api/runs/107/review-volume/');
      queries.push(url.searchParams);
      const week = url.searchParams.get('granularity') === 'week';
      return Response.json({ run_id: 107, granularity: week ? 'week' : 'day', points: week ? [] : [
        { period_start: url.searchParams.get('date_to'), frames_reviewed: 42, decisions: 48 }] });
    }));
  });

  it('draws one bar per day with labelled values and the range total', async () => {
    wrap(<ReviewVolumeChart runId={107} />);
    const list = await screen.findByRole('list', { name: 'Frame đã review theo ngày' });
    const bars = within(list).getAllByRole('listitem');
    expect(bars).toHaveLength(14);
    expect(bars[13].getAttribute('aria-label')).toMatch(/: 42 frame, 48 quyết định$/);
    expect(bars[0].className).toBe('is-zero');
    expect(screen.getByText('42 frame · 48 quyết định review trong khoảng đã chọn')).toBeDefined();
    expect(queries[0].get('granularity')).toBe('day');
    expect(queries[0].get('date_from')).toBeTruthy();
  });

  it('refetches by week and says when the range has no review', async () => {
    wrap(<ReviewVolumeChart runId={107} />);
    await screen.findByRole('list', { name: 'Frame đã review theo ngày' });
    fireEvent.change(screen.getByLabelText('Chu kỳ'), { target: { value: 'week' } });
    expect(await screen.findByRole('list', { name: 'Frame đã review theo tuần' })).toBeDefined();
    expect(queries.at(-1)?.get('granularity')).toBe('week');
    expect(screen.getByText('Chưa có frame nào được review trong khoảng đã chọn')).toBeDefined();
  });

  it('does not call the API for an inverted range', async () => {
    wrap(<ReviewVolumeChart runId={107} />);
    await screen.findByRole('list');
    const calls = queries.length;
    fireEvent.change(screen.getByLabelText('Từ ngày'), { target: { value: '2099-01-01' } });
    expect(screen.getByRole('alert').textContent).toBe('Ngày bắt đầu phải trước ngày kết thúc.');
    await waitFor(() => expect(queries.length).toBe(calls));
  });

  it('shows the API error with a retry', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ code: 'VALIDATION_ERROR', message: 'x' }, { status: 400 })));
    wrap(<ReviewVolumeChart runId={107} />);
    expect(await screen.findByText(/Dữ liệu không hợp lệ/)).toBeDefined();
    expect(screen.getByRole('button', { name: 'Thử lại' })).toBeDefined();
  });
});
