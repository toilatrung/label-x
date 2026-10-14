'use client';

import React, { useEffect, useRef, useState } from 'react';
import { errorMessage } from '@/lib/api/errors';
import { importGuideline, previewGuideline, type TaxonomyDefinition } from '@/lib/guidelines/config-api';

type ImportResult = Awaited<ReturnType<typeof importGuideline>>;
type Preview = Awaited<ReturnType<typeof previewGuideline>>;
type ManualAttribute = { name: string; rule_id: string; values: string };
type ManualLabel = { name: string; attributes: ManualAttribute[] };

export function GuidelineImportModal({ onClose, onImported }: {
  onClose: () => void;
  onImported: (result: ImportResult) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const readId = useRef(0);
  const [content, setContent] = useState('');
  const [fileName, setFileName] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [taxonomyVersion, setTaxonomyVersion] = useState('');
  const [labels, setLabels] = useState<ManualLabel[]>([{ name: '', attributes: [] }]);
  const [reading, setReading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!dialog.current?.open) dialog.current?.showModal();
    fileInput.current?.focus();
    return () => { readId.current += 1; opener?.focus(); };
  }, []);

  async function chooseFile(file: File | undefined) {
    const id = ++readId.current;
    setFileName(file?.name ?? '');
    setContent(''); setPreview(null); setError(null); setReading(false);
    setTaxonomyVersion(''); setLabels([{ name: '', attributes: [] }]);
    if (!file) return;
    if (file.size > 1_000_000) { setError('Tệp Guideline tối đa 1 MB.'); return; }
    setReading(true);
    try {
      const text = await file.text();
      const result = await previewGuideline(text);
      if (id === readId.current) { setContent(text); setPreview(result); }
    } catch (err) {
      if (id === readId.current) setError(errorMessage(err));
    } finally { if (id === readId.current) setReading(false); }
  }

  function updateLabel(index: number, change: Partial<ManualLabel>) {
    setLabels(current => current.map((label, i) => i === index ? { ...label, ...change } : label));
  }
  function updateAttribute(labelIndex: number, attrIndex: number, change: Partial<ManualAttribute>) {
    setLabels(current => current.map((label, i) => i === labelIndex ? { ...label,
      attributes: label.attributes.map((attr, j) => j === attrIndex ? { ...attr, ...change } : attr) } : label));
  }
  const manualReady = !!taxonomyVersion.trim() && labels.length > 0 && labels.every(label =>
    !!label.name.trim() && label.attributes.every(attr => !!attr.name.trim() && !!attr.rule_id));
  const canImport = !!preview && (!!preview.taxonomy || manualReady) && !busy && !reading;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canImport || !preview) return;
    const manual: TaxonomyDefinition | undefined = preview.taxonomy ? undefined : {
      version: taxonomyVersion.trim(), labels: labels.map(label => ({ name: label.name.trim(),
        required_attributes: label.attributes.map(attr => ({ name: attr.name.trim(), rule_id: attr.rule_id,
          allowed_values: attr.values.split('\n').map(value => value.trim()).filter(Boolean) })) })),
    };
    setBusy(true); setError(null);
    try {
      const result = await importGuideline(content, manual);
      onImported(result); onClose();
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  return <dialog ref={dialog} className="lx-gap-dialog" aria-labelledby="guideline-import-title"
    aria-describedby="guideline-import-description" onClose={onClose}
    onCancel={event => { if (busy) event.preventDefault(); }}
    onClick={event => { if (event.target === dialog.current && !busy) dialog.current?.close(); }}>
    <div className="lx-gap">
      <header className="lx-gap__head">
        <div><h2 id="guideline-import-title">Thêm Guideline</h2>
          <p id="guideline-import-description">Thêm phiên bản vào thư viện. Chọn Guideline áp dụng cho Dataset khi tạo từng Snapshot.</p></div>
        <button type="button" className="lx-gap__close" aria-label="Đóng hộp thoại" disabled={busy} onClick={() => dialog.current?.close()}>×</button>
      </header>
      <form className="lx-gap__body" onSubmit={submit}>
        <div className="lx-gap__fields">
          <div className="lx-field">
            <label className="lx-label" htmlFor="guideline-import-file">Tệp Guideline (YAML)</label>
            <div className="lx-file-picker" data-disabled={busy}>
              <input ref={fileInput} className="lx-file-picker__input" id="guideline-import-file" type="file" accept=".yaml,.yml" disabled={busy}
                aria-describedby="guideline-file-name guideline-file-hint" onChange={event => void chooseFile(event.target.files?.[0])} />
              <span className="lx-file-picker__button" aria-hidden="true">Chọn tệp</span>
              <span className="lx-file-picker__name" id="guideline-file-name" title={fileName || 'Chưa chọn tệp'}>{fileName || 'Chưa chọn tệp'}</span>
            </div>
            <p className="lx-hint" id="guideline-file-hint">Tệp tối đa 1 MB. Taxonomy có sẵn được import cùng Guideline; nếu chưa có, nhập bên dưới. Phiên bản đã import không được ghi đè.</p>
          </div>
          {reading && <p role="status">Đang kiểm tra Guideline…</p>}
          {preview && <p>{preview.name} · {preview.version} · {preview.rules.length} rule</p>}
          {preview?.taxonomy && <section className="lx-card lx-card__body" aria-label="Taxonomy từ Guideline">
            <h3 className="lx-h3">Đã nhận diện taxonomy {preview.taxonomy.version}</h3>
            <p>{preview.taxonomy.labels.map(label => label.name).join(', ')}</p>
            <p className="lx-hint">Taxonomy này sẽ được import cùng Guideline.</p>
          </section>}
          {preview && !preview.taxonomy && <fieldset className="lx-field lx-fieldset" disabled={busy}>
            <legend className="lx-label">Nhập taxonomy cho Guideline</legend>
            <p className="lx-hint">Guideline chưa có taxonomy. Nhập phiên bản và đầy đủ các lớp hợp lệ để tiếp tục.</p>
            <div className="lx-field"><label className="lx-label" htmlFor="manual-taxonomy-version">Phiên bản taxonomy *</label>
              <input className="lx-input" id="manual-taxonomy-version" value={taxonomyVersion} onChange={event => setTaxonomyVersion(event.target.value)} /></div>
            {labels.map((label, i) => <div className="lx-card lx-card__body lx-stack" key={i}>
              <div className="lx-field"><label className="lx-label" htmlFor={`manual-label-${i}`}>Tên lớp {i + 1} *</label>
                <input className="lx-input" id={`manual-label-${i}`} value={label.name} onChange={event => updateLabel(i, { name: event.target.value })} /></div>
              {label.attributes.map((attr, j) => <div className="lx-stack" key={j}>
                <div className="lx-field"><label className="lx-label" htmlFor={`manual-attr-${i}-${j}`}>Thuộc tính bắt buộc {i + 1}.{j + 1} *</label>
                  <input className="lx-input" id={`manual-attr-${i}-${j}`} value={attr.name} onChange={event => updateAttribute(i, j, { name: event.target.value })} /></div>
                <div className="lx-field"><label className="lx-label" htmlFor={`manual-rule-${i}-${j}`}>Rule cho thuộc tính {i + 1}.{j + 1} *</label>
                  <select className="lx-select" id={`manual-rule-${i}-${j}`} value={attr.rule_id} onChange={event => updateAttribute(i, j, { rule_id: event.target.value })}>
                    <option value="">Chọn rule</option>{preview.rules.map(rule => <option key={rule.rule_id} value={rule.rule_id}>{rule.rule_id} · {rule.section}</option>)}
                  </select></div>
                <div className="lx-field"><label className="lx-label" htmlFor={`manual-values-${i}-${j}`}>Giá trị cho phép {i + 1}.{j + 1}</label>
                  <textarea className="lx-textarea" id={`manual-values-${i}-${j}`} rows={2} value={attr.values} onChange={event => updateAttribute(i, j, { values: event.target.value })} />
                  <span className="lx-hint">Mỗi dòng một giá trị. Để trống nếu chỉ cần kiểm tra có giá trị.</span></div>
                <button type="button" className="lx-btn lx-btn--sm" onClick={() => updateLabel(i, { attributes: label.attributes.filter((_, k) => k !== j) })}>Xóa thuộc tính {i + 1}.{j + 1}</button>
              </div>)}
              <div className="lx-row"><button type="button" className="lx-btn lx-btn--sm" onClick={() => updateLabel(i, { attributes: [...label.attributes, { name: '', rule_id: '', values: '' }] })}>Thêm thuộc tính bắt buộc cho lớp {i + 1}</button>
                <button type="button" className="lx-btn lx-btn--sm" disabled={labels.length === 1} onClick={() => setLabels(current => current.filter((_, k) => k !== i))}>Xóa lớp {i + 1}</button></div>
            </div>)}
            <button type="button" className="lx-btn" onClick={() => setLabels(current => [...current, { name: '', attributes: [] }])}>Thêm lớp</button>
          </fieldset>}
        </div>
        {error && <div role="alert" className="lx-gap__notice">{error}</div>}
        <div className="lx-gap__actions">
          <button type="button" className="lx-btn" disabled={busy} onClick={() => dialog.current?.close()}>Hủy</button>
          <button type="submit" className="lx-btn lx-btn--primary" disabled={!canImport}>{busy ? 'Đang import…' : 'Import Guideline'}</button>
        </div>
      </form>
    </div>
  </dialog>;
}
