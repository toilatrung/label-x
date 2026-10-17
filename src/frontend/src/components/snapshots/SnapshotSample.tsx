'use client';

import React from 'react';
import Link from 'next/link';
import type { UseInfiniteQueryResult, InfiniteData } from '@tanstack/react-query';
import { ApiRequestError, errorMessage } from '@/lib/api/errors';
import { formatDateTime, shortRevision, snapshotCode } from '@/lib/format';
import type { DatasetRevisionPage } from '@/lib/snapshots/api';

const CURRENT = 'current';

/** Lỗi tải API Quality Control Run thật; không thay bằng mock vì endpoint này đã có. */
export function SnapshotInUseExtra({ error }: { error?: string }) {
  return <div className="lx-callout" role="alert">{error || 'Không tải được Quality Control Run của Snapshot.'}</div>;
}

/**
 * Revision lấy từ GET /api/datasets/{id}/revisions/ (DEC-022): Snapshot mới luôn khoá revision hiện tại của CVAT,
 * revision cũ chỉ để mở Snapshot đã khoá. Seed và cấu hình chọn khi tạo Quality Control Run.
 */
export function SnapshotRevisionFields({ dataset, revisions }: {
  dataset: React.ReactNode;
  revisions: UseInfiniteQueryResult<InfiniteData<DatasetRevisionPage>>;
}) {
  const [picked, setPicked] = React.useState(CURRENT);
  const rows = revisions.data?.pages.flatMap(page => page.results) ?? [];
  const selected = rows.find(row => String(row.snapshot_id) === picked);
  return (
    <>
      <div className="lx-grid lx-grid--3">
        {dataset}
        <div className="lx-field">
          <label className="lx-label" htmlFor="snapshot-revision">Annotation revision</label>
          <select id="snapshot-revision" className="lx-select" value={selected ? picked : CURRENT}
            onChange={event => setPicked(event.target.value)}>
            <option value={CURRENT}>Revision hiện tại của CVAT (tính khi tạo snapshot)</option>
            {rows.map(row => <option key={row.snapshot_id} value={row.snapshot_id}>
              {shortRevision(row.revision)} · {snapshotCode(row.snapshot_id)} · {formatDateTime(row.created_at)}</option>)}
          </select>
          {selected
            ? <span className="lx-hint">Revision này đã khoá trong <Link href={`/analysis?snapshotId=${selected.snapshot_id}`}>{snapshotCode(selected.snapshot_id)}</Link>.</span>
            : <span className="lx-hint">Snapshot mới luôn khoá revision hiện tại. Chọn revision cũ để mở snapshot đã khoá.</span>}
        </div>
        <div className="lx-field">
          <span className="lx-label">Seed và cấu hình kiểm tra</span>
          <span className="lx-muted">Chọn khi tạo Quality Control Run</span>
          <span className="lx-hint">Ở bước Cấu hình kiểm tra, sau khi snapshot đã khoá</span>
        </div>
      </div>
      {revisions.isFetching && !revisions.isFetchingNextPage && <p role="status" className="lx-hint">Đang tải revision…</p>}
      {revisions.isError && <div className="lx-callout" role="alert">
        {revisions.error instanceof ApiRequestError && revisions.error.status === 502 ? 'Không đọc được revision từ CVAT. ' : ''}{errorMessage(revisions.error)}
        <button className="lx-btn" type="button" onClick={() => void revisions.refetch()}>Thử lại</button></div>}
      {revisions.hasNextPage && <button className="lx-btn" type="button" disabled={revisions.isFetchingNextPage}
        onClick={() => void revisions.fetchNextPage()}>Tải thêm revision</button>}
    </>
  );
}
