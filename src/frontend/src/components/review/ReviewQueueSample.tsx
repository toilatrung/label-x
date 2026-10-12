'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { Icon } from '@/components/ui/Icon';
import { ALERT_OPTIONS, ALL, PRIORITY_OPTIONS, SAMPLE_QUEUE_FRAMES } from '@/lib/review/sample-queue';

/** Hàng đợi minh họa theo ReviewQueues.dc.html, hiện khi chưa có Run để tải dữ liệu thật. Không gọi API. */
export function ReviewQueueSample() {
  const [search, setSearch] = useState('');
  const [priority, setPriority] = useState<string>(ALL);
  const [alert, setAlert] = useState<string>(ALL);
  const rows = SAMPLE_QUEUE_FRAMES.filter((f) =>
    `${f.name} ${f.id} ${f.frame}`.toLowerCase().includes(search.toLowerCase()) &&
    (priority === ALL || f.priority === priority) && (alert === ALL || f.alert === alert));
  const reset = () => { setSearch(''); setPriority(ALL); setAlert(ALL); };
  return (
    <section className="lx-stack" aria-label="Hàng đợi minh họa">
      <div className="lx-review-filters">
        <label className="lx-field">Tìm kiếm
          <span className="lx-search">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></svg>
            <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tìm ảnh hoặc mã công việc" aria-label="Tìm ảnh hoặc mã công việc" />
          </span>
        </label>
        <label className="lx-field">Mức ưu tiên
          <select className="lx-select" value={priority} onChange={(e) => setPriority(e.target.value)}>{PRIORITY_OPTIONS.map((o) => <option key={o}>{o}</option>)}</select>
        </label>
        <label className="lx-field">Loại cảnh báo
          <select className="lx-select" value={alert} onChange={(e) => setAlert(e.target.value)}>{ALERT_OPTIONS.map((o) => <option key={o}>{o}</option>)}</select>
        </label>
      </div>
      <section className="lx-review-queue" aria-label="Danh sách ảnh cần kiểm tra">
        <div className="lx-card__head"><strong>Ảnh cần kiểm tra</strong><span className="lx-hint" role="status">{rows.length} ảnh</span></div>
        {rows.map((f, i) => (
          <article key={f.id} className="lx-review-row">
            <span className="lx-review-rank">{i + 1}</span>
            {/* Ảnh mẫu tĩnh theo thiết kế, không cần tối ưu bằng next/image */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <span className="lx-review-thumb"><img src={f.image} alt={`${f.name}: ${f.scene}, cảnh báo ${f.alert}`} width={203} height={92} /></span>
            <div className="lx-review-info">
              <div className="lx-review-title">
                <h2 className="lx-h2">{f.name}</h2>
                <span className="lx-review-badge"><Icon name="alert" className="lx-review-icon" />{f.alert}</span>
                <span className={`lx-review-badge${f.priority === 'Cao' ? ' lx-review-badge--danger' : ''}`}><Icon name={f.priority === 'Cao' ? 'up' : 'equal'} className="lx-review-icon" />{f.priority}</span>
              </div>
              <div className="lx-mono lx-subtle">{f.id}</div>
              <div className="lx-review-meta">
                <span><Icon name="frame" className="lx-review-icon" />Frame {f.frame}</span>
                <span><Icon name="scene" className="lx-review-icon" />{f.scene}</span>
                <time><Icon name="clock" className="lx-review-icon" />{f.time}</time>
              </div>
            </div>
            <Link className="lx-btn lx-btn--primary lx-review-start" aria-label={`Bắt đầu kiểm tra ${f.name}`} href={`/review/workspace?frame_id=${f.frame}`}>Bắt đầu kiểm tra</Link>
          </article>
        ))}
        {rows.length === 0 && <div className="lx-review-empty"><p>Không có ảnh khớp bộ lọc.</p><button type="button" className="lx-btn" onClick={reset}>Xóa bộ lọc</button></div>}
        <div className="lx-card__foot"><span>Ưu tiên cao được hiển thị trước</span><span>{rows.length ? `1–${rows.length} / ${rows.length}` : '0 / 0'}</span></div>
      </section>
    </section>
  );
}
