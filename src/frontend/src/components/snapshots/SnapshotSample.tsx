'use client';

import React from 'react';
import { SAMPLE_SNAPSHOT_FORM } from '@/lib/mock/snapshots';

/** Lỗi tải API Quality Control Run thật; không thay bằng mock vì endpoint này đã có. */
export function SnapshotInUseExtra({ error }: { error?: string }) {
  return <div className="lx-callout" role="alert">{error || 'Không tải được Quality Control Run của Snapshot.'}</div>;
}

/** Revision và seed chưa có API, dùng dữ liệu sketchup và giữ read-only. */
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
