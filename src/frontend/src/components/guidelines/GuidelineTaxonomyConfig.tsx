'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import { DatasetPicker } from '@/lib/execution/DatasetPicker';
import { errorMessage } from '@/lib/api/errors';
import { getDatasetGuideline, importGuideline, listGuidelineVersions, setDatasetGuideline } from '@/lib/guidelines/config-api';
import { cursorFrom } from '@/lib/execution/api';

export function GuidelineTaxonomyConfig() {
  const { session, datasetId } = useAuth();
  const client = useQueryClient();
  const canWrite = session?.roles.some(({ role, dataset_id }) =>
    (role === 'qc_admin' || role === 'super_admin') && (dataset_id === null || dataset_id === datasetId)) ?? false;
  const canImport = session?.roles.some(({ role }) => role === 'qc_admin' || role === 'super_admin') ?? false;
  const [cursor, setCursor] = useState<string | undefined>();
  const [version, setVersion] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const versions = useQuery({ queryKey: ['guideline-versions', session?.user.id, cursor],
    queryFn: ({ signal }) => listGuidelineVersions(cursor, signal), retry: false });
  const binding = useQuery({ queryKey: ['dataset-guideline', session?.user.id, datasetId],
    queryFn: ({ signal }) => getDatasetGuideline(datasetId!, signal), enabled: datasetId !== null, retry: false });
  async function upload() {
    if (busy || !canImport || !content.trim()) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const result = await importGuideline(content);
      setNotice(`${result.skipped ? 'Đã có' : 'Đã import'} Guideline ${result.version}.`);
      setVersion(result.version); setCursor(undefined);
      await client.invalidateQueries({ queryKey: ['guideline-versions'] });
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }
  async function save() {
    if (busy || !canWrite || !datasetId || !version || !binding.data) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const result = await setDatasetGuideline(datasetId, version, binding.data.revision);
      client.setQueryData(['dataset-guideline', session?.user.id, datasetId], result);
      setNotice(`Dataset đã áp dụng Guideline ${result.guideline_version}. Snapshot đã khóa giữ nguyên phiên bản.`);
    } catch (err) {
      setError(errorMessage(err));
      await binding.refetch();
    } finally { setBusy(false); }
  }
  return <section className="lx-card" aria-label="Guideline và taxonomy của Dataset">
    <header className="lx-card__head"><h2 className="lx-h2">Guideline và taxonomy của Dataset</h2></header>
    <div className="lx-card__body lx-stack">
      {canImport && <div className="lx-field">
        <label className="lx-label" htmlFor="guideline-file">Import Guideline và taxonomy (YAML)</label>
        <input id="guideline-file" type="file" accept=".yaml,.yml" disabled={busy} onChange={async event => {
          const file = event.target.files?.[0];
          setError(null); setNotice(null); setContent('');
          if (!file) return;
          if (file.size > 1_000_000) { setError('Tệp Guideline tối đa 1 MB.'); return; }
          try { setContent(await file.text()); } catch { setError('Không đọc được tệp Guideline.'); }
        }} />
        <p className="lx-hint">Tệp phải khai báo taxonomy gồm lớp hợp lệ và thuộc tính bắt buộc. Phiên bản đã import không được ghi đè.</p>
        <button className="lx-btn" type="button" disabled={busy || !content} onClick={upload}>Import Guideline</button>
      </div>}
      <DatasetPicker onChange={() => { setVersion(''); setNotice(null); setError(null); }} />
      {datasetId && binding.isPending && <p role="status">Đang tải Guideline của Dataset…</p>}
      {binding.data && <p>Guideline đang áp dụng: <strong>{binding.data.guideline_version ?? 'Chưa cấu hình'}</strong> · Taxonomy: {binding.data.taxonomy_version ?? 'Chưa có'}</p>}
      <div className="lx-field">
        <label className="lx-label" htmlFor="dataset-guideline-version">Guideline version cho Snapshot mới</label>
        <select id="dataset-guideline-version" className="lx-select" value={version} disabled={!canWrite || busy || versions.isPending} onChange={event => setVersion(event.target.value)}>
          <option value="">Chọn Guideline có taxonomy</option>
          {versions.data?.results.map(item => <option key={item.version} value={item.version} disabled={!item.taxonomy_ready}>{item.version} · {item.taxonomy_version ?? 'Chưa có taxonomy'}</option>)}
        </select>
      </div>
      {versions.data?.next && <button className="lx-btn" type="button" onClick={() => { setCursor(cursorFrom(versions.data?.next) ?? undefined); setVersion(''); }}>Trang Guideline tiếp</button>}
      {canWrite && <button type="button" className="lx-btn lx-btn--primary" disabled={busy || !datasetId || !version || !binding.data} onClick={save}>Áp dụng cho Dataset</button>}
      {(error || versions.isError || binding.isError) && <p role="alert" className="lx-callout">{error ?? errorMessage(versions.error ?? binding.error)}</p>}
      {notice && <p role="status" className="lx-callout">{notice}</p>}
    </div>
  </section>;
}
