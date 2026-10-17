'use client';

import React, { useEffect, useState } from 'react';
import { ProgressBar } from './ProgressBar';
import type { LedgerEntry, Run } from '@/lib/execution/api';

const NAMES: Record<string, string> = {
  schema: 'Schema', geometry: 'Geometry', duplicate: 'Duplicate', detector: 'Mô hình độc lập',
  metric: 'Metric', vlm: 'VLM',
};
const TERMINAL = new Set(['completed', 'partial', 'failed', 'cancelled']);
const ENGINE_DONE = new Set(['completed', 'checked', 'partial', 'failed', 'not_checked', 'cancelled']);

export function AnalysisProgress({ run, ledger, error, updatedAt }: {
  run: Run; ledger?: LedgerEntry[]; error?: string | null; updatedAt?: number;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!updatedAt || TERMINAL.has(run.status)) return;
    const timer = setInterval(() => setNow(Date.now()), 10_000);
    return () => clearInterval(timer);
  }, [updatedAt, run.status]);
  const updateStale = !!updatedAt && !TERMINAL.has(run.status) && now - updatedAt > 30_000;
  const hasPending = (engine: string) => run.status !== 'cancelled' && (ledger?.find(row => row.engine === engine)?.pending ?? 0) > 0;
  const ended = TERMINAL.has(run.status) && !run.engines.some(engine => hasPending(engine.engine));
  const failed = run.engines.filter(engine => engine.status === 'failed' || engine.status === 'partial' || (engine.failed_units ?? 0) > 0);
  const resolved = run.engines.filter(engine => ENGINE_DONE.has(engine.status) && !hasPending(engine.engine));
  const active = run.engines.filter(engine => !ENGINE_DONE.has(engine.status) || hasPending(engine.engine));
  const progress = run.engines.map(engine => {
    if (ENGINE_DONE.has(engine.status) && !hasPending(engine.engine)) return 1;
    const row = ledger?.find(item => item.engine === engine.engine);
    if (!row || row.total <= 0) return 0;
    return Math.min(1, (row.completed + row.failed + row.not_checked) / row.total);
  });
  const percent = ended ? 100 : Math.min(99, Math.floor(100 * progress.reduce((sum, value) => sum + value, 0) / Math.max(1, progress.length)));
  const stale = updateStale || run.engines.some(engine => engine.progress?.stale);
  const waiting = active.filter(engine => engine.progress?.phase === 'waiting_retry');
  const vlm = active.find(engine => engine.engine === 'vlm');
  const vlmRow = ledger?.find(row => row.engine === 'vlm');
  const preparation = !!vlm && (!vlmRow || vlmRow.total === 0) && active.every(engine => engine.engine === 'vlm');
  const title = ended && run.status === 'cancelled' ? 'Đã dừng phân tích'
    : ended && run.status === 'failed' ? 'Phân tích thất bại'
      : ended && run.status === 'partial' ? 'Đã kết thúc · Kết quả một phần'
        : ended && run.status === 'completed' ? 'Phân tích đã hoàn tất'
          : stale ? 'Quá hạn cập nhật xử lý · Cần kiểm tra worker'
            : waiting.length && !active.some(engine => engine.progress?.phase === 'running') ? 'Đang chờ tài nguyên hoặc thử lại'
          : run.status === 'queued' ? 'Đang chờ worker'
            : preparation ? 'Đang chuẩn bị VLM · Chưa xác nhận gọi model'
              : active.length ? `Đang xử lý: ${active.map(engine => NAMES[engine.engine] ?? engine.engine).join(', ')}`
                : 'Đang chốt kết quả phân tích';

  return <section className="lx-stack lx-stack--2" aria-label="Tiến độ phân tích">
    <div className="lx-row lx-row--between" aria-live="polite"><strong>{title}</strong><span>{resolved.length}/{run.engines.length} engine đã xử lý</span></div>
    <ProgressBar label="Tổng tiến độ engine" value={ledger || ended ? percent : undefined}
      active={!TERMINAL.has(run.status)} paused={!!error || stale} warning={failed.length > 0 || run.status === 'partial' || run.status === 'failed'} />
    <p className="lx-hint">{ledger || ended ? `${percent}% tiến trình` : 'Chưa xác định tổng tiến độ'} · Tính trung bình tiến độ từng engine, không phải tỷ lệ chất lượng hay thời gian còn lại.</p>
    {updatedAt && <p className="lx-hint">Dữ liệu xác nhận lúc {new Date(updatedAt).toLocaleTimeString()}{updateStale ? ' · Chưa nhận được cập nhật mới; kiểm tra kết nối.' : ''}</p>}
    {vlmRow && vlmRow.total > 0 && <p className="lx-hint">VLM: {vlmRow.completed} hoàn tất · {vlmRow.failed} lỗi · {vlmRow.pending} chờ/đang xử lý. Task VLM chưa đồng nghĩa provider đã được gọi.</p>}
    {run.engines.filter(engine => engine.progress).map(engine => {
      const p = engine.progress!;
      const labels: Record<string, string> = { queued: 'Chờ worker', preparing: 'Đang chuẩn bị', running: 'Đang xử lý', waiting_retry: 'Chờ tài nguyên / thử lại', overdue: 'Quá hạn xử lý', finished: 'Đã kết thúc' };
      return <p key={engine.engine} className="lx-hint">{NAMES[engine.engine] ?? engine.engine}: {labels[p.phase] ?? p.phase}
        {p.retry_at && p.phase === 'waiting_retry' && ` · Thử lại lúc ${new Date(p.retry_at).toLocaleTimeString()}`}
        {p.last_activity_at && ` · Hoạt động gần nhất ${new Date(p.last_activity_at).toLocaleTimeString()}`}
        {engine.engine === 'vlm' && ` · ${p.provider_calls} lượt gọi đã ghi nhận · ${p.failed} lỗi · ${p.skipped} chưa xử lý`}
      </p>;
    })}
    {failed.length > 0 && <p role="alert" className="lx-callout lx-callout--warning">Engine gặp lỗi: {failed.map(engine => NAMES[engine.engine] ?? engine.engine).join(', ')}.{!ended && ' Các phần còn lại tiếp tục được xử lý.'}</p>}
    {run.engines.some(engine => engine.status === 'not_checked') && <p className="lx-hint">Engine ghi Not checked chưa được kiểm tra; không được xem là đạt.</p>}
    {error && <p role="alert">Không tải được tiến độ mới nhất: {error}</p>}
  </section>;
}
