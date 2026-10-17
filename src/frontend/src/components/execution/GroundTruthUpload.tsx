'use client';

import React, { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { currentGroundTruth, lockGroundTruth, previewGroundTruth, uploadGroundTruth } from '@/lib/execution/api';
import { ApiRequestError, errorMessage } from '@/lib/api/errors';
import { formatCount } from '@/lib/format';

function groundTruthErrorMessage(error: unknown): string {
  // Validation messages describe how to correct the uploaded file. Keep server
  // failures and authentication errors on the shared, sanitized error path.
  if (error instanceof ApiRequestError && error.status === 400 &&
      error.detail?.code === 'VALIDATION_ERROR' && error.detail.message?.trim()) {
    return error.detail.message;
  }
  return errorMessage(error);
}

export function GroundTruthUpload({ datasetId, snapshotId, userId, enabled, busy, isSuperAdmin = false, onImportPendingChange }: {
  datasetId: number | null; snapshotId: number | null; userId: number;
  enabled: boolean; busy: boolean;
  isSuperAdmin?: boolean;
  onImportPendingChange?: (pending: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState('bdd100k-det-10-v1');
  const [key, setKey] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ reference_id: number; frames: Record<string, unknown>[] } | null>(null);
  const query = useQuery({ queryKey: ['ground-truth', userId, datasetId],
    queryFn: ({ signal }) => currentGroundTruth(datasetId!, signal),
    enabled: datasetId !== null, retry: false, refetchInterval: 5000 });
  const current = query.data;
  useEffect(() => {
    onImportPendingChange?.(file !== null || working);
  }, [file, working, onImportPendingChange]);
  async function showPreview() {
    if (!current || working) return;
    setWorking(true); setError(null);
    try { setPreview(await previewGroundTruth(current.reference.id)); }
    catch (err) { setError(errorMessage(err)); }
    finally { setWorking(false); }
  }
  async function act(upload: boolean) {
    if (working || busy) return;
    setWorking(true); setError(null);
    try {
      if (upload) {
        if (!snapshotId || !file) return;
        const requestKey = key ?? crypto.randomUUID();
        setKey(requestKey);
        await uploadGroundTruth(snapshotId, file, mapping, requestKey);
        setFile(null); setKey(null);
      } else if (current) {
        await lockGroundTruth(current.reference.id);
      }
      await queryClient.invalidateQueries({ queryKey: ['ground-truth', userId, datasetId] });
    } catch (err) { setError(groundTruthErrorMessage(err)); }
    finally { setWorking(false); }
  }
  return <section className="lx-stack" aria-label="Ground Truth lưu tạm">
    <div className="lx-field"><label className="lx-label" htmlFor="ground-truth-file">Upload Ground Truth</label>
      <input id="ground-truth-file" className="lx-input" type="file" accept=".json,application/json"
        disabled={!enabled || working || busy || !snapshotId}
        onChange={(e) => { setFile(e.target.files?.[0] ?? null); setKey(null); setError(null); }} />
      <span className="lx-hint">JSON labelx.metric.gt.v1, tối đa 20 MiB. Bounding box dùng tọa độ pixel của Snapshot đã chọn.</span>
      <span className="lx-hint">{snapshotId
        ? `Đang upload cho Snapshot #${snapshotId}. Ground Truth được kiểm tra theo task, frame, class và kích thước ảnh.`
        : 'Chọn Dataset và Snapshot đã khoá trước khi upload Ground Truth.'}</span>
    </div>
    <div className="lx-field"><label className="lx-label" htmlFor="ground-truth-mapping">Mapping class của Ground Truth</label>
      <input id="ground-truth-mapping" className="lx-input" value={mapping} disabled={!enabled || working || busy}
        onChange={(e) => { setMapping(e.target.value); setKey(null); }} /></div>
    <button type="button" className="lx-btn lx-btn--sm" disabled={!enabled || !snapshotId || !file || !mapping.trim() || working || busy}
      onClick={() => void act(true)}>{working ? 'Đang xử lý…' : 'Upload Ground Truth'}</button>
    {query.isPending && datasetId !== null && <p className="lx-hint">Đang tải Ground Truth…</p>}
    {query.isError && <p role="alert" className="lx-callout">{errorMessage(query.error)}</p>}
    {current ? <div className="lx-stack">
      <span className="lx-hint">{current.filename} · {formatCount(current.frame_count)} frame · {formatCount(current.box_count)} bbox</span>
      {!current.deleted_at && <button type="button" className="lx-btn lx-btn--sm" disabled={working || busy}
        onClick={() => void showPreview()}>Xem Ground Truth</button>}
      {preview?.reference_id === current.reference.id && <details className="lx-stack" open>
        <summary>Annotation Ground Truth theo frame</summary><pre className="lx-code">{JSON.stringify(preview.frames, null, 2)}</pre>
      </details>}
      <span className="lx-hint">{current.deleted_at ? 'File đã xóa sau khi chạy thành công. Chạy lại cần upload lại.'
        : current.reference.status === 'locked' ? 'Ground Truth đã duyệt, sẵn sàng chạy.'
        : isSuperAdmin ? 'Super Admin có thể xem và duyệt Ground Truth này, kể cả do chính mình upload.'
        : 'Chờ QA Lead khác người upload duyệt Ground Truth.'}</span>
      {!current.deleted_at && current.reference.status === 'draft'
        && (isSuperAdmin || current.reference.created_by !== userId) && <button type="button" className="lx-btn lx-btn--sm"
          disabled={!enabled || working || busy || preview?.reference_id !== current.reference.id} onClick={() => void act(false)}>Duyệt Ground Truth</button>}
    </div> : !query.isPending && !query.isError && <p className="lx-hint">Chưa upload Ground Truth cho Dataset này.</p>}
    <p className="lx-hint">File được lưu tạm và tự xóa sau khi các run dùng nó hoàn tất, Metric đã tính thành công. Giữ bản gốc trên máy để upload lại.</p>
    {error && <p role="alert" className="lx-callout">{error}</p>}
  </section>;
}
