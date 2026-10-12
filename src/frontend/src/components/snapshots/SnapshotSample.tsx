'use client';

import React, { useState } from 'react';
import { SAMPLE_IN_USE, SAMPLE_IN_USE_EXTRA, SAMPLE_SNAPSHOT_FORM } from '@/lib/mock/snapshots';

/** Ba trường của Snapshot đang dùng chưa có API; luôn là dữ liệu minh họa, một cảnh báo cho cả khối. */
export function SnapshotInUseExtra({ error }: { error?: string }) {
  void error;
  return (
    <div className="lx-stack lx-stack--divider">
      <dl className="lx-kv">
        {SAMPLE_IN_USE_EXTRA.map(([label, value, mono]) => (
          <React.Fragment key={label}><dt>{label}</dt><dd className={mono ? 'lx-mono' : undefined}>{value}</dd></React.Fragment>
        ))}
      </dl>
    </div>
  );
}

/** Bản minh họa đủ thiết kế của thẻ "Snapshot đang dùng", dùng khi không tải được Dataset. */
export function SnapshotInUseSample() {
  const s = SAMPLE_IN_USE;
  return (
    <div className="lx-stack">
      <dl className="lx-kv">
        <dt>Mã snapshot</dt><dd className="lx-mono">{s.id}</dd>
        <dt>Annotation revision</dt><dd className="lx-mono">{s.revision}</dd>
        <dt>Taxonomy</dt><dd>{s.taxonomy}</dd>
        <dt>Guideline</dt><dd>{s.guideline}</dd>
        <dt>Mô hình độc lập</dt><dd>{s.models}</dd>
        <dt>Cấu hình kiểm tra</dt><dd>{s.config}</dd>
        <dt>Seed lấy mẫu</dt><dd className="lx-mono">{s.seed}</dd>
        <dt>Tạo bởi</dt><dd>{s.createdBy}</dd>
      </dl>
    </div>
  );
}

/** Dataset, Annotation revision, Seed: hai trường sau chưa có API nên khoá và dùng giá trị minh họa. */
export function SnapshotRevisionFields({ dataset }: { dataset: React.ReactNode }) {
  const f = SAMPLE_SNAPSHOT_FORM;
  return (
    <>
      <div className="lx-grid lx-grid--3">
        {dataset}
        <div className="lx-field">
          <label className="lx-label" htmlFor="snapshot-revision">Annotation revision</label>
          <select id="snapshot-revision" className="lx-select" disabled>{f.revisions.map(item => <option key={item}>{item}</option>)}</select>
        </div>
        <div className="lx-field">
          <label className="lx-label" htmlFor="snapshot-seed">Mã hạt giống lấy mẫu (seed)</label>
          <input id="snapshot-seed" className="lx-input" value={f.seed} readOnly disabled />
          <span className="lx-hint">Giữ nguyên để tái lập mẫu</span>
        </div>
      </div>
    </>
  );
}

/** Bản minh họa đủ thiết kế của thẻ "Tạo snapshot mới", dùng khi không tải được Dataset. Mọi nút ghi bị chặn. */
export function SnapshotCreateSample() {
  const f = SAMPLE_SNAPSHOT_FORM;
  const [, setBlocked] = useState<string | null>(null);
  return (
    <div className="lx-stack">
      <div className="lx-grid lx-grid--3">
        <div className="lx-field"><label className="lx-label" htmlFor="sample-dataset">Dataset</label><input id="sample-dataset" className="lx-input" value={f.dataset} readOnly disabled /></div>
        <div className="lx-field"><label className="lx-label" htmlFor="sample-revision">Annotation revision</label>
          <select id="sample-revision" className="lx-select" disabled>{f.revisions.map(item => <option key={item}>{item}</option>)}</select></div>
        <div className="lx-field"><label className="lx-label" htmlFor="sample-seed">Mã hạt giống lấy mẫu (seed)</label>
          <input id="sample-seed" className="lx-input" value={f.seed} readOnly disabled /><span className="lx-hint">Giữ nguyên để tái lập mẫu</span></div>
      </div>
      <div className="lx-field">
        <span className="lx-label">Phạm vi kiểm tra</span>
        <div className="lx-card lx-card--inner">
          <table className="lx-table">
            <thead><tr><th className="lx-th--check"><input type="checkbox" className="lx-check-accent" checked readOnly disabled aria-label="Chọn tất cả" /></th><th>Task / Job</th><th>Người thực hiện · Giai đoạn</th><th className="r">Frame</th></tr></thead>
            <tbody>
              {f.tasks.map(task => (
                <tr key={task.key}><td><input type="checkbox" className="lx-check-accent" checked readOnly disabled aria-label={task.key} /></td>
                  <td className="lx-cell__main">{task.name}</td><td className="lx-muted">{task.jobs}</td><td className="r">{task.frames}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <span className="lx-hint">Chọn cả Task hoặc từng Job. {f.hint}</span>
      </div>
      <div className="lx-field"><label className="lx-label" htmlFor="sample-note">Ghi chú</label>
        <textarea id="sample-note" className="lx-textarea" placeholder="Ví dụ: Snapshot sau đợt sửa lỗi hình học tuần 40" disabled /></div>
      <div className="lx-actions lx-actions--end">
        {/* TODO(backend): Dataset/Task/Job thật chưa tải được; nút chặn, không gọi API giả */}
        <button type="button" className="lx-btn" onClick={() => setBlocked('Huỷ')}>Huỷ</button>
        <button type="button" className="lx-btn lx-btn--primary" onClick={() => setBlocked('Tạo snapshot và cấu hình')}>Tạo snapshot và cấu hình →</button>
      </div>
    </div>
  );
}
