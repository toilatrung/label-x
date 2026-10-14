'use client';

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import { DatasetPicker } from '@/lib/execution/DatasetPicker';
import { errorMessage } from '@/lib/api/errors';
import { getDatasetGuideline, listGuidelineVersions, setDatasetGuideline } from '@/lib/guidelines/config-api';
import { GuidelineImportModal } from './GuidelineImportModal';
import { cursorFrom } from '@/lib/execution/api';

export function GuidelineTaxonomyConfig() {
  const { session, datasetId } = useAuth();
  const client = useQueryClient();
  const canWrite = session?.roles.some(({ role, dataset_id }) =>
    (role === 'qc_admin' || role === 'super_admin') && (dataset_id === null || dataset_id === datasetId)) ?? false;
  const canImport = session?.roles.some(({ role }) => role === 'qc_admin' || role === 'super_admin') ?? false;
  const [cursor, setCursor] = useState<string | undefined>();
  const [version, setVersion] = useState('');
  const [importOpen, setImportOpen] = useState(false);
  const [defaultsOpen, setDefaultsOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const versions = useQuery({ queryKey: ['guideline-versions', session?.user.id, cursor],
    queryFn: ({ signal }) => listGuidelineVersions(cursor, signal), retry: false });
  const binding = useQuery({ queryKey: ['dataset-guideline', session?.user.id, datasetId],
    queryFn: ({ signal }) => getDatasetGuideline(datasetId!, signal), enabled: defaultsOpen && datasetId !== null, retry: false });
  async function save() {
    if (busy || !canWrite || !datasetId || !version || !binding.data) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const result = await setDatasetGuideline(datasetId, version, binding.data.revision);
      client.setQueryData(['dataset-guideline', session?.user.id, datasetId], result);
      setNotice(`Đã lưu Guideline ${result.guideline_version} làm mặc định cho Dataset. Khi tạo Snapshot mới có thể chọn phiên bản khác.`);
    } catch (err) {
      setError(errorMessage(err));
      await binding.refetch();
    } finally { setBusy(false); }
  }
  return <section className="lx-card" aria-label="Thư viện Guideline">
    <header className="lx-card__head"><h2 className="lx-h2">Thư viện Guideline</h2>{canImport && <button className="lx-btn lx-btn--primary" type="button" onClick={() => setImportOpen(true)}>Thêm Guideline</button>}</header>
    <div className="lx-card__body lx-stack">
      <p className="lx-hint">Guideline được chọn riêng khi tạo mỗi Snapshot của Dataset. Thêm phiên bản vào thư viện không tự áp dụng cho dữ liệu.</p>
      {versions.isPending && <p role="status">Đang tải thư viện Guideline…</p>}
      {versions.data && <div className="lx-scroll"><table className="lx-table">
        <thead><tr><th>Guideline</th><th>Taxonomy</th><th>Rule</th><th>Ngày import</th><th>Trạng thái</th></tr></thead>
        <tbody>{versions.data.results.map(item => <tr key={item.version}>
          <td className="lx-mono">{item.version}</td><td>{item.taxonomy_version ?? 'Chưa có'}</td>
          <td>{item.rule_count}</td><td>{item.effective_from ? new Date(item.effective_from).toLocaleDateString('vi-VN') : '—'}</td>
          <td>{item.taxonomy_ready ? 'Có taxonomy' : 'Cần bổ sung taxonomy'}</td>
        </tr>)}{versions.data.results.length === 0 && <tr><td colSpan={5}>Chưa có phiên bản Guideline.</td></tr>}</tbody>
      </table></div>}
      {versions.data?.next && <button className="lx-btn" type="button" onClick={() => { setCursor(cursorFrom(versions.data?.next) ?? undefined); setVersion(''); }}>Trang Guideline tiếp</button>}
      <details onToggle={event => setDefaultsOpen(event.currentTarget.open)}>
        <summary>Guideline mặc định cho Dataset (tùy chọn)</summary>
        <div className="lx-stack">
      <p className="lx-hint">Mặc định này dùng cho Snapshot mới khi không chọn Guideline riêng. Snapshot đã khóa giữ nguyên phiên bản đã lưu.</p>
      <DatasetPicker onChange={() => { setVersion(''); setNotice(null); setError(null); }} />
      {datasetId && binding.isPending && <p role="status">Đang tải Guideline của Dataset…</p>}
      {binding.data && <p>Guideline mặc định của Dataset: <strong>{binding.data.guideline_version ?? 'Chưa cấu hình'}</strong> · Taxonomy: {binding.data.taxonomy_version ?? 'Chưa có'}</p>}
      <div className="lx-field">
        <label className="lx-label" htmlFor="dataset-guideline-version">Guideline mặc định cho Dataset</label>
        <select id="dataset-guideline-version" className="lx-select" value={version} disabled={!canWrite || busy || versions.isPending} onChange={event => setVersion(event.target.value)}>
          <option value="">Chọn Guideline có taxonomy</option>
          {versions.data?.results.map(item => <option key={item.version} value={item.version} disabled={!item.taxonomy_ready}>{item.version} · {item.taxonomy_version ?? 'Chưa có taxonomy'}</option>)}
        </select>
      </div>
      {canWrite && <button type="button" className="lx-btn lx-btn--primary" disabled={busy || !datasetId || !version || !binding.data} onClick={save}>Lưu mặc định cho Dataset</button>}
        </div>
      </details>
      {(error || versions.isError || binding.isError) && <p role="alert" className="lx-callout">{error ?? errorMessage(versions.error ?? binding.error)}</p>}
      {notice && <p role="status" className="lx-callout">{notice}</p>}
    </div>
    {importOpen && <GuidelineImportModal onClose={() => setImportOpen(false)} onImported={result => {
      setNotice(`${result.skipped ? 'Đã có' : 'Đã import'} Guideline ${result.version}.`);
      setVersion(result.version); setCursor(undefined);
      void client.invalidateQueries({ queryKey: ['guideline-versions'] });
      void client.invalidateQueries({ queryKey: ['guideline-rules'] });
      void client.invalidateQueries({ queryKey: ['snapshot-guideline-versions'] });
    }} />}
  </section>;
}
