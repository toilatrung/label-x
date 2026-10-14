'use client';

import React, { useEffect, useRef, useState } from 'react';
import { errorMessage } from '@/lib/api/errors';
import { createConfig, publishConfig, type ConfigVersion, type ConfigVersionCreate } from '@/lib/execution/api';
import { ENGINES_META } from '@/components/execution/EngineThresholdsTable';

const ENGINES = ['schema', 'geometry', 'duplicate', 'detector', 'metric', 'vlm'] as const;

interface Props {
  onClose: () => void;
  onPublished: (config: ConfigVersion) => void | Promise<void>;
}

/** Hộp thoại tạo và phát hành phiên bản cấu hình; cùng khung với Tạo Guideline Gap. */
export function ConfigVersionModal({ onClose, onPublished }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const nameField = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const [enabledEngines, setEnabledEngines] = useState<string[]>(['schema', 'geometry', 'duplicate']);
  const [thresholdsText, setThresholdsText] = useState('{}');
  const [modelsText, setModelsText] = useState('{}');
  const [pending, setPending] = useState<{ body: ConfigVersionCreate; key: string } | null>(null);
  const [draftId, setDraftId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tried, setTried] = useState(false);

  useEffect(() => {
    if (!opener.current && document.activeElement instanceof HTMLElement) opener.current = document.activeElement;
    dialog.current?.showModal();
    nameField.current?.focus();
  }, []);

  async function finish(published: ConfigVersion) {
    setDraftId(null);
    setPending(null);
    await onPublished(published);
    dialog.current?.close();
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setTried(true);
    if (!name.trim()) return nameField.current?.focus();
    if (enabledEngines.length === 0) return;
    let thresholds: Record<string, unknown>;
    let models: Record<string, unknown>;
    try {
      thresholds = JSON.parse(thresholdsText);
      models = JSON.parse(modelsText);
      if (!thresholds || typeof thresholds !== 'object' || Array.isArray(thresholds) || !models || typeof models !== 'object' || Array.isArray(models)) throw new Error();
    } catch { setError('Ngưỡng và model phải là đối tượng JSON hợp lệ.'); return; }
    const body: ConfigVersionCreate = { name: name.trim(), engines: Object.fromEntries(ENGINES.map((engine) => [engine, { enabled: enabledEngines.includes(engine) }])), thresholds, models };
    // Gửi lại cùng nội dung dùng lại key để backend trả về bản đã tạo, không tạo trùng.
    const request = pending && JSON.stringify(pending.body) === JSON.stringify(body) ? pending : { body, key: crypto.randomUUID() };
    setPending(request);
    setBusy(true); setError(null);
    try {
      const draft = await createConfig(request.body, request.key);
      setDraftId(draft.id);
      await finish(draft.status === 'published' ? draft : await publishConfig(draft.id));
    } catch (err) {
      setError(errorMessage(err));
    } finally { setBusy(false); }
  }

  async function retryPublish() {
    if (!draftId || busy) return;
    setBusy(true); setError(null);
    try {
      const replay = pending ? await createConfig(pending.body, pending.key) : null;
      await finish(replay?.status === 'published' ? replay : await publishConfig(draftId));
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  const reset = () => setPending(null);

  return (
    <dialog ref={dialog} className="lx-gap-dialog" aria-labelledby="config-version-title"
      aria-describedby="config-version-description" onClose={() => { onClose(); requestAnimationFrame(() => opener.current?.focus()); }}
      onClick={(event) => { if (event.target === dialog.current && !busy) dialog.current?.close(); }}>
      <div className="lx-gap">
        <header className="lx-gap__head">
          <div>
            <h2 id="config-version-title">Tạo phiên bản cấu hình</h2>
            <p id="config-version-description">Phiên bản mới được phát hành để Quality Assurance Lead chọn khi chạy phân tích. Phiên bản đã phát hành không chỉnh sửa trực tiếp.</p>
          </div>
          <button type="button" className="lx-gap__close" aria-label="Đóng hộp thoại" disabled={busy} onClick={() => dialog.current?.close()}>×</button>
        </header>
        <form className="lx-gap__body" noValidate onSubmit={submit}>
          <div className="lx-gap__fields">
            <div className="lx-field">
              <label className="lx-label" htmlFor="config-name">Tên cấu hình *</label>
              <input ref={nameField} className="lx-input" id="config-name" value={name} maxLength={128} onChange={(e) => { setName(e.target.value); reset(); }} aria-invalid={tried && !name.trim()} aria-describedby={tried && !name.trim() ? 'config-name-error' : undefined} />
              {tried && !name.trim() && <span id="config-name-error" className="lx-gap__error">Nhập tên cấu hình.</span>}
            </div>
            <fieldset className="lx-field lx-fieldset">
              <legend className="lx-label">Engine cần chạy *</legend>
              <div className="lx-card lx-card--inner"><table className="lx-table"><tbody>{ENGINES_META.map((meta) => <tr key={meta.key}>
                <td className="lx-th--check"><label className="lx-switch"><input type="checkbox" aria-label={meta.name} checked={enabledEngines.includes(meta.key)} onChange={(e) => { setEnabledEngines((current) => e.target.checked ? [...current, meta.key] : current.filter((item) => item !== meta.key)); reset(); }} /><span /></label></td>
                <td><div className="lx-cell__main">{meta.name}</div><div className="lx-cell__sub">{meta.sub}</div></td>
              </tr>)}</tbody></table></div>
              {enabledEngines.length === 0 && <span role="alert" className="lx-gap__error">Cần bật ít nhất một engine.</span>}
            </fieldset>
            <div className="lx-field"><label className="lx-label" htmlFor="config-thresholds">Ngưỡng kiểm tra (JSON)</label><textarea className="lx-textarea" id="config-thresholds" rows={3} value={thresholdsText} onChange={(e) => { setThresholdsText(e.target.value); reset(); }} /></div>
            <div className="lx-field"><label className="lx-label" htmlFor="config-models">Mô hình tham chiếu (JSON)</label><textarea className="lx-textarea" id="config-models" rows={3} value={modelsText} onChange={(e) => { setModelsText(e.target.value); reset(); }} /></div>
          </div>
          {error && <div className="lx-gap__notice" role="alert"><strong>Không tạo được phiên bản cấu hình.</strong> {error}</div>}
          {draftId && <div className="lx-gap__notice">Phiên bản v{draftId} đã được tạo nhưng chưa xác nhận phát hành. <button type="button" className="lx-btn lx-btn--sm" disabled={busy} onClick={retryPublish}>Thử phát hành lại</button></div>}
          <div className="lx-gap__actions">
            <button type="button" className="lx-btn" disabled={busy} onClick={() => dialog.current?.close()}>Hủy</button>
            <button type="submit" className="lx-btn lx-btn--primary" disabled={busy || enabledEngines.length === 0}>{busy ? 'Đang lưu…' : 'Tạo và phát hành'}</button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
