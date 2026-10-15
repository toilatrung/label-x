'use client';

import React, { useRef, useState } from 'react';
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import { hasDatasetPermission } from '@/lib/auth/roles';
import { ApiRequestError, errorMessage } from '@/lib/api/errors';
import { cursorFrom, getSnapshot, getSnapshots, safeCvatUrl } from '@/lib/snapshots/api';
import { newIdempotencyKey } from '@/lib/reports/api';
import { createBenchmark, listBenchmarks, type Benchmark } from '@/lib/calibration/benchmark-api';
import { formatDateTime } from '@/lib/format';

const STATUS: Record<Benchmark['status'], string> = { pending: 'Đang chờ', ready: 'Sẵn sàng', failed: 'Thất bại' };

function creationError(error: unknown) {
  // Keep actionable validation messages; server failures use the shared generic message.
  if (error instanceof ApiRequestError && [400, 409, 422].includes(error.status) && error.detail?.message) {
    return error.detail.message;
  }
  return errorMessage(error);
}

function BenchmarkCreateDialog({ datasetId, onClose }: { datasetId: number; onClose: () => void }) {
  const { session } = useAuth();
  const client = useQueryClient();
  const dialog = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState('');
  const [snapshotId, setSnapshotId] = useState<number | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const replay = useRef<{ body: string; key: string } | null>(null);
  const snapshots = useInfiniteQuery({
    queryKey: ['benchmark-snapshots', session?.user.id, datasetId],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getSnapshots(datasetId, pageParam, signal),
    getNextPageParam: page => cursorFrom(page.next), retry: false,
  });
  const snapshot = useQuery({
    queryKey: ['benchmark-snapshot', session?.user.id, datasetId, snapshotId],
    queryFn: ({ signal }) => getSnapshot(snapshotId!, signal), enabled: snapshotId !== null, retry: false,
  });
  const frames = snapshot.data?.jobs.flatMap(job => job.frames.map(frame => ({ ...frame,
    task: job.cvat_task_id, job: job.cvat_job_id }))) ?? [];
  const available = frames.flatMap(frame => frame.id === undefined ? [] : [frame.id]);
  const validSnapshot = snapshot.data?.dataset_id === datasetId && snapshot.data.status === 'locked';
  const canSubmit = !!name.trim() && validSnapshot && selected.length > 0 && !busy && !snapshot.isFetching;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit || snapshotId === null) return;
    const body = { name: name.trim(), dataset_id: datasetId, snapshot_id: snapshotId, frame_ids: [...selected].sort((a, b) => a - b) };
    const serialized = JSON.stringify(body);
    if (replay.current?.body !== serialized) replay.current = { body: serialized, key: newIdempotencyKey() };
    setBusy(true); setError(null);
    try {
      await createBenchmark(body, replay.current!.key);
      await client.invalidateQueries({ queryKey: ['benchmarks'] });
      onClose();
    } catch (err) { setError(creationError(err)); }
    finally { setBusy(false); }
  }

  return <dialog ref={node => { dialog.current = node; if (node && !node.open) node.showModal(); }}
    className="lx-gap-dialog" aria-labelledby="benchmark-create-title" onClose={onClose}
    onCancel={event => { if (busy) event.preventDefault(); }}>
    <form className="lx-gap" onSubmit={submit}>
      <header className="lx-gap__head"><h2 id="benchmark-create-title">Tạo benchmark từ Snapshot</h2>
        <button type="button" className="lx-btn" disabled={busy} onClick={onClose}>Đóng</button></header>
      <div className="lx-gap__body lx-stack">
        <p>Dataset #{datasetId}. Chọn các frame chuẩn để đưa vào benchmark.</p>
        <fieldset disabled={busy} className="lx-field lx-fieldset">
          <label className="lx-label" htmlFor="benchmark-name">Tên benchmark</label>
          <input id="benchmark-name" className="lx-input" value={name} maxLength={255} required onChange={event => setName(event.target.value)} />
          <label className="lx-label" htmlFor="benchmark-snapshot">Snapshot đã khóa</label>
          <select id="benchmark-snapshot" className="lx-select" value={snapshotId ?? ''} onChange={event => {
            setSnapshotId(event.target.value ? Number(event.target.value) : null); setSelected([]); setError(null);
          }}>
            <option value="">Chọn Snapshot</option>
            {snapshots.data?.pages.flatMap(page => page.results).filter(item => item.status === 'locked').map(item =>
              <option key={item.id} value={item.id}>Snapshot #{item.id} · {formatDateTime(item.created_at)}</option>)}
          </select>
          {snapshots.isPending && <p role="status">Đang tải Snapshot…</p>}
          {snapshots.isError && <p role="alert">{errorMessage(snapshots.error)} <button type="button" onClick={() => void snapshots.refetch()}>Thử lại</button></p>}
          {snapshots.hasNextPage && <button type="button" className="lx-btn" disabled={snapshots.isFetchingNextPage} onClick={() => void snapshots.fetchNextPage()}>Tải thêm Snapshot</button>}
          {snapshots.isSuccess && !snapshots.data.pages.some(page => page.results.some(item => item.status === 'locked')) && <p>Chưa có Snapshot đã khóa. Tạo Snapshot trong Dataset trước, hoặc tải thêm Snapshot.</p>}
          {snapshotId !== null && snapshot.isPending && <p role="status">Đang tải frame…</p>}
          {snapshot.isError && <p role="alert">{errorMessage(snapshot.error)} <button type="button" onClick={() => void snapshot.refetch()}>Thử lại</button></p>}
          {snapshot.isSuccess && validSnapshot && <>
            <p>Đã chọn {selected.length} / {available.length} frame.</p>
            <button type="button" className="lx-btn" onClick={() => setSelected(selected.length === available.length ? [] : available)}>
              {selected.length && selected.length === available.length ? 'Bỏ chọn tất cả' : 'Chọn tất cả frame'}</button>
            {!frames.length && <p>Snapshot này chưa có frame.</p>}
            {frames.some(frame => frame.id === undefined) && <p role="alert">Không đọc được ID frame. Vui lòng cập nhật máy chủ và tải lại Snapshot.</p>}
            <div className="lx-scroll" style={{ maxHeight: 320 }}>
              {frames.map(frame => <label className="lx-field" key={`${frame.job}:${frame.frame_index}`}>
                <span><input type="checkbox" disabled={frame.id === undefined} checked={frame.id !== undefined && selected.includes(frame.id)} onChange={event => {
                  const id = frame.id;
                  if (id !== undefined) setSelected(current => event.target.checked ? [...current, id] : current.filter(value => value !== id));
                }} /> Task {frame.task} · Job {frame.job} · Frame {frame.frame_index} · {frame.file_name}</span>
                {safeCvatUrl(frame.cvat_url) && <a href={safeCvatUrl(frame.cvat_url)!} target="_blank" rel="noreferrer">Xem trên CVAT</a>}
              </label>)}
            </div>
          </>}
          {snapshot.isSuccess && !validSnapshot && <p role="alert">Snapshot không thuộc Dataset hoặc chưa được khóa.</p>}
        </fieldset>
        {error && <p role="alert">{error}</p>}
        <div className="lx-gap__actions"><button type="button" className="lx-btn" disabled={busy} onClick={onClose}>Hủy</button>
          <button className="lx-btn lx-btn--primary" type="submit" disabled={!canSubmit}>{busy ? 'Đang tạo…' : 'Lưu benchmark'}</button></div>
      </div>
    </form>
  </dialog>;
}

export function BenchmarkHeader() {
  const { session, datasetId } = useAuth();
  const [open, setOpen] = useState(false);
  const canCreate = hasDatasetPermission(session, datasetId, role => ['qc_admin', 'super_admin', 'data_model_owner'].includes(role));
  return <>
    <div className="lx-head">
      <div className="lx-head__text"><h1 className="lx-h1">Ground Truth Benchmark</h1>
        <p className="lx-lead">Tập frame chuẩn dùng để hiệu chỉnh và đánh giá. Chọn Dataset để quản lý benchmark.</p></div>
      <div className="lx-actions"><button type="button" className="lx-btn lx-btn--primary" disabled={!canCreate || datasetId === null} onClick={() => setOpen(true)}>Tạo benchmark</button></div>
    </div>
    {open && datasetId !== null && canCreate && <BenchmarkCreateDialog key={datasetId} datasetId={datasetId} onClose={() => setOpen(false)} />}
  </>;
}

export function BenchmarkBody() {
  const { session, datasetId } = useAuth();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const canRead = hasDatasetPermission(session, datasetId, role => ['qa_lead', 'qc_admin', 'super_admin', 'product_owner', 'data_model_owner'].includes(role));
  const query = useInfiniteQuery({
    queryKey: ['benchmarks', session?.user.id, datasetId], initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => listBenchmarks(datasetId!, pageParam, signal),
    getNextPageParam: page => cursorFrom(page.next), enabled: datasetId !== null && canRead, retry: false,
    refetchInterval: q => q.state.data?.pages.some(page => page.results.some(row => row.status === 'pending')) ? 5000 : false,
  });
  if (datasetId === null) return <p role="status">Chọn Dataset trên thanh điều hướng để xem và tạo benchmark.</p>;
  if (!canRead) return <p role="status">Bạn không có quyền quản lý benchmark trong Dataset này.</p>;
  if (query.isPending) return <p role="status">Đang tải benchmark…</p>;
  if (query.isError) return <p role="alert">{errorMessage(query.error)} <button className="lx-btn" onClick={() => void query.refetch()}>Thử lại</button></p>;
  const rows = query.data.pages.flatMap(page => page.results);
  const selected = rows.find(row => row.id === selectedId) ?? rows[0];
  return <div className="lx-cols">
    <section className="lx-card lx-main" aria-label="Các phiên bản benchmark">
      <div className="lx-card__head"><h2 className="lx-h2">Các phiên bản benchmark</h2></div>
      {!rows.length ? <p className="lx-card__body">Chưa có benchmark trong Dataset này.</p> : <div className="lx-scroll">
        <table className="lx-table lx-table--min-640"><thead><tr><th>Tên benchmark</th><th>Phạm vi</th><th className="r">Frame</th><th>Trạng thái</th><th /></tr></thead>
          <tbody>{rows.map(row => <tr key={row.id} aria-selected={selected?.id === row.id}>
            <td>{row.name}</td><td>Dataset #{row.dataset_id}{row.snapshot_id ? ` · Snapshot #${row.snapshot_id}` : ''}</td>
            <td className="r">{row.frame_count}</td><td>{STATUS[row.status]}</td>
            <td><button type="button" className="lx-btn" onClick={() => setSelectedId(row.id)} aria-label={`Xem ${row.name}`}>Chi tiết</button></td>
          </tr>)}</tbody></table>
      </div>}
      {query.hasNextPage && <button className="lx-btn" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>Tải thêm benchmark</button>}
    </section>
    {selected && <section className="lx-card lx-side" aria-label="Chi tiết benchmark">
      <div className="lx-card__head"><h2 className="lx-h2">{selected.name}</h2><span className="lx-badge">{STATUS[selected.status]}</span></div>
      <dl className="lx-card__body lx-kv"><dt>Mã benchmark</dt><dd>#{selected.id}</dd><dt>Frame chuẩn</dt><dd>{selected.frame_count}</dd>
        <dt>Nguồn</dt><dd>{selected.source === 'manual' ? 'Snapshot' : 'CVAT'}</dd><dt>Người tạo</dt><dd>#{selected.created_by}</dd>
        <dt>Tạo lúc</dt><dd>{formatDateTime(selected.created_at)}</dd></dl>
    </section>}
  </div>;
}
