'use client';

import React from 'react';
import { errorMessage } from '@/lib/api/errors';
import { formatCount } from '@/lib/format';
import { useReviewVolume, type ReviewVolume, type ReviewVolumeQuery } from '@/lib/overview/api';

/** Backend gom theo ngày ở múi giờ Asia/Ho_Chi_Minh (TIME_ZONE); khoảng mặc định tính cùng múi giờ. */
const SERVER_TZ = 'Asia/Ho_Chi_Minh';
const DEFAULT_DAYS = 14;
const DAY_MS = 86_400_000;

const toDate = (iso: string) => new Date(`${iso}T00:00:00Z`);
const toIso = (date: Date) => date.toISOString().slice(0, 10);
const addDays = (iso: string, days: number) => toIso(new Date(toDate(iso).getTime() + days * DAY_MS));
/** Thứ Hai của tuần chứa ngày, như TruncWeek của backend. */
const mondayOf = (iso: string) => addDays(iso, -((toDate(iso).getUTCDay() + 6) % 7));
const shortDate = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

export function todayInServerTz(now = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: SERVER_TZ }).format(now);
}

export function defaultVolumeQuery(now = new Date()): ReviewVolumeQuery {
  const to = todayInServerTz(now);
  return { granularity: 'day', date_from: addDays(to, -(DEFAULT_DAYS - 1)), date_to: to };
}

/** Backend chỉ trả kỳ có dữ liệu; điền 0 cho kỳ trống để trục thời gian không bị co lại. */
export function fillPeriods(volume: ReviewVolume, query: ReviewVolumeQuery) {
  const step = query.granularity === 'week' ? 7 : 1;
  const first = query.granularity === 'week' ? mondayOf(query.date_from) : query.date_from;
  const byPeriod = new Map(volume.points.map(point => [point.period_start, point]));
  const rows = [];
  for (let period = first; period <= query.date_to && rows.length < 400; period = addDays(period, step)) {
    const point = byPeriod.get(period);
    rows.push({ period, frames: point?.frames_reviewed ?? 0, decisions: point?.decisions ?? 0 });
  }
  return rows;
}

export function ReviewVolumeChart({ runId }: { runId: number | null }) {
  const [query, setQuery] = React.useState<ReviewVolumeQuery>(() => defaultVolumeQuery());
  const invalidRange = query.date_from > query.date_to;
  const volume = useReviewVolume(runId, query);
  const rows = volume.data ? fillPeriods(volume.data, query) : [];
  const max = Math.max(0, ...rows.map(row => row.frames));
  const frames = rows.reduce((sum, row) => sum + row.frames, 0);
  const decisions = rows.reduce((sum, row) => sum + row.decisions, 0);
  const unit = query.granularity === 'week' ? 'tuần' : 'ngày';
  const label = (row: { period: string; frames: number; decisions: number }) =>
    `${query.granularity === 'week' ? 'Tuần từ ' : ''}${shortDate(row.period)}: ${formatCount(row.frames)} frame, ${formatCount(row.decisions)} quyết định`;
  const update = (patch: Partial<ReviewVolumeQuery>) => setQuery(current => ({ ...current, ...patch }));

  return <div className="lx-stack lx-stack--2">
    <div className="lx-row lx-row--between"><span className="lx-muted">Frame đã review</span>
      <select className="lx-select lx-select--auto" aria-label="Chu kỳ" value={query.granularity}
        onChange={event => update({ granularity: event.target.value as ReviewVolumeQuery['granularity'] })}>
        <option value="day">Theo ngày</option><option value="week">Theo tuần</option>
      </select></div>
    <div className="lx-row lx-row--nowrap">
      <input className="lx-input" type="date" aria-label="Từ ngày" value={query.date_from} max={query.date_to}
        onChange={event => event.target.value && update({ date_from: event.target.value })} />
      <input className="lx-input" type="date" aria-label="Đến ngày" value={query.date_to} min={query.date_from}
        onChange={event => event.target.value && update({ date_to: event.target.value })} />
    </div>
    {invalidRange ? <span className="lx-hint" role="alert">Ngày bắt đầu phải trước ngày kết thúc.</span>
      : volume.isPending ? <span className="lx-hint" role="status">Đang tải khối lượng review…</span>
        : volume.isError ? <div className="lx-callout" role="alert">{errorMessage(volume.error)}
          <button className="lx-btn lx-btn--sm" type="button" onClick={() => void volume.refetch()}>Thử lại</button></div>
          : <>
            <div className="lx-vbars" role="list" aria-label={`Frame đã review theo ${unit}`}>
              {rows.map(row => <i key={row.period} role="listitem" tabIndex={0} aria-label={label(row)} title={label(row)}
                className={row.frames ? undefined : 'is-zero'} style={{ height: `${max ? row.frames / max * 100 : 0}%` }} />)}
            </div>
            {rows.length > 0 && <div className="lx-vbars__axis"><span>{shortDate(rows[0].period)}</span><span>{shortDate(rows[rows.length - 1].period)}</span></div>}
            <span className="lx-hint">{frames || decisions
              ? `${formatCount(frames)} frame · ${formatCount(decisions)} quyết định review trong khoảng đã chọn`
              : 'Chưa có frame nào được review trong khoảng đã chọn'}</span>
          </>}
  </div>;
}
