'use client';

import React from 'react';
import type { LedgerEntry, Run } from '@/lib/execution/api';

const NAMES: Record<string, string> = {
  schema: 'Schema', geometry: 'Geometry', duplicate: 'Duplicate', detector: 'Mô hình độc lập',
  metric: 'Metric', vlm: 'VLM',
};
const TERMINAL = new Set(['completed', 'partial', 'failed', 'cancelled']);
const ENGINE_DONE = new Set(['completed', 'checked', 'partial', 'failed', 'not_checked', 'cancelled']);

export function AnalysisProgress({ run, ledger, error }: {
  run: Run; ledger?: LedgerEntry[]; error?: string | null;
}) {
  const ended = TERMINAL.has(run.status);
  const failed = run.engines.filter(engine => engine.status === 'failed' || engine.status === 'partial' || (engine.failed_units ?? 0) > 0);
  const resolved = run.engines.filter(engine => ENGINE_DONE.has(engine.status));
  const active = run.engines.filter(engine => !ENGINE_DONE.has(engine.status));
  const progress = run.engines.map(engine => {
    if (ENGINE_DONE.has(engine.status)) return 1;
    const row = ledger?.find(item => item.engine === engine.engine);
    if (!row || row.total <= 0) return 0;
    return Math.min(1, (row.completed + row.failed + row.not_checked) / row.total);
  });
  const percent = ended ? 100 : Math.min(99, Math.floor(100 * progress.reduce((sum, value) => sum + value, 0) / Math.max(1, progress.length)));
  const vlm = active.find(engine => engine.engine === 'vlm');
  const vlmRow = ledger?.find(row => row.engine === 'vlm');
  const preparation = !!vlm && (!vlmRow || vlmRow.total === 0) && active.every(engine => engine.engine === 'vlm');
  const title = run.status === 'cancelled' ? 'Đã dừng phân tích'
    : run.status === 'failed' ? 'Phân tích thất bại'
      : run.status === 'partial' ? 'Đã kết thúc · Kết quả một phần'
        : run.status === 'completed' ? 'Phân tích đã hoàn tất'
          : run.status === 'queued' ? 'Đang chờ worker'
            : preparation ? 'Đang chuẩn bị VLM · Chưa xác nhận gọi model'
              : active.length ? `Đang xử lý: ${active.map(engine => NAMES[engine.engine] ?? engine.engine).join(', ')}`
                : 'Đang chốt kết quả phân tích';

  return <section className="lx-stack lx-stack--2" aria-label="Tiến độ phân tích">
    <div className="lx-row lx-row--between" aria-live="polite"><strong>{title}</strong><span>{resolved.length}/{run.engines.length} engine đã xử lý</span></div>
    <div className={`lx-progress${failed.length || run.status === 'partial' || run.status === 'failed' ? ' lx-progress--warn' : ''}`}
      role="progressbar" aria-label="Tổng tiến độ engine" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={ledger || ended ? percent : undefined}
      aria-valuetext={error ? 'Không tải được tiến độ mới nhất' : `${percent}% · ${title}`}>
      <i style={{ width: `${percent}%` }} />
    </div>
    <p className="lx-hint">{percent}% tiến trình · Tính trung bình tiến độ từng engine, không phải tỷ lệ chất lượng hay thời gian còn lại.</p>
    {vlmRow && vlmRow.total > 0 && <p className="lx-hint">VLM: {vlmRow.completed} hoàn tất · {vlmRow.failed} lỗi · {vlmRow.pending} chờ/đang xử lý. Task VLM chưa đồng nghĩa provider đã được gọi.</p>}
    {failed.length > 0 && <p role="alert" className="lx-callout lx-callout--warning">Engine gặp lỗi: {failed.map(engine => NAMES[engine.engine] ?? engine.engine).join(', ')}.{!ended && ' Các phần còn lại tiếp tục được xử lý.'}</p>}
    {run.engines.some(engine => engine.status === 'not_checked') && <p className="lx-hint">Engine ghi Not checked chưa được kiểm tra; không được xem là đạt.</p>}
    {error && <p role="alert">Không tải được tiến độ mới nhất: {error}</p>}
  </section>;
}
