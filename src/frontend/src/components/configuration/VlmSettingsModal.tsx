'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { errorMessage } from '@/lib/api/errors';
import { getVlmSettings, saveVlmSettings, type VlmSettings } from '@/lib/configuration/vlm-api';

export function VlmSettingsModal({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const { hasPermission } = useAuth();
  const canWrite = hasPermission(role => ['qc_admin', 'super_admin'].includes(role));
  const [settings, setSettings] = useState<VlmSettings | null>(null);
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function accept(value: VlmSettings) {
    setSettings(value); setBaseUrl(value.base_url); setApiKey('');
  }

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!dialog.current?.open) dialog.current?.showModal();
    return () => { opener?.focus(); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    getVlmSettings(controller.signal).then(value => {
      if (!controller.signal.aborted) accept(value);
    }).catch(err => {
      if (!controller.signal.aborted) setError(errorMessage(err));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  async function reload() {
    setLoading(true); setError(null); setSaved(false); setApiKey('');
    try { accept(await getVlmSettings()); }
    catch (err) { setError(errorMessage(err)); }
    finally { setLoading(false); }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!settings || busy || !canWrite) return;
    setBusy(true); setError(null); setSaved(false);
    try {
      accept(await saveVlmSettings({ expected_revision: settings.revision, base_url: baseUrl.trim(), model: settings.model, ...(apiKey ? { api_key: apiKey } : {}) }));
      setSaved(true);
    } catch (err) { setError(errorMessage(err)); }
    finally { setApiKey(''); setBusy(false); }
  }

  const keyRequired = !settings?.api_key_configured || baseUrl.trim().replace(/\/$/, '') !== settings?.base_url;

  return (
    <dialog ref={dialog} className="lx-gap-dialog" aria-labelledby="vlm-settings-title"
      aria-describedby="vlm-settings-description" onClose={onClose}
      onCancel={event => { if (busy) event.preventDefault(); }}
      onClick={event => { if (event.target === dialog.current && !busy) dialog.current?.close(); }}>
      <div className="lx-gap">
        <header className="lx-gap__head">
          <div><h2 id="vlm-settings-title">Chỉnh mô hình thị giác – ngôn ngữ</h2>
            <p id="vlm-settings-description">Cấu hình kết nối VLM dùng để kiểm tra nhãn có chọn lọc.</p></div>
          <button type="button" className="lx-gap__close" aria-label="Đóng hộp thoại" disabled={busy} onClick={() => dialog.current?.close()}>×</button>
        </header>
        <form className="lx-gap__body" onSubmit={submit}>
          <p className="lx-muted">Phiên bản cấu hình QC mới bật VLM sẽ dùng kết nối đã lưu.</p>
          <div className="lx-gap__fields">
          {loading && <p role="status">Đang tải cấu hình VLM…</p>}
          {settings && !loading && <>
            <div className="lx-field"><label className="lx-label" htmlFor="vlm-model">Model</label><input id="vlm-model" className="lx-input" value={settings.model} readOnly /></div>
            <div className="lx-field"><label className="lx-label" htmlFor="vlm-base-url">Base URL</label>
              <input id="vlm-base-url" className="lx-input" type="url" required value={baseUrl} disabled={!canWrite || busy} onChange={event => { setBaseUrl(event.target.value); setSaved(false); }} aria-describedby="vlm-url-help" />
              <p id="vlm-url-help" className="lx-muted">Hỗ trợ https://api.shopaikey.com/v1 hoặc endpoint DashScope /compatible-mode/v1. Crop ảnh sẽ được gửi đến nhà cung cấp đã chọn.</p>
            </div>
            <div className="lx-field"><label className="lx-label" htmlFor="vlm-api-key">API key</label>
              <input id="vlm-api-key" className="lx-input" type="password" autoComplete="new-password" required={keyRequired} value={apiKey} disabled={!canWrite || busy} onChange={event => { setApiKey(event.target.value); setSaved(false); }} aria-describedby="vlm-key-help" placeholder={settings.api_key_configured ? 'Đã lưu API key' : 'Nhập API key'} />
              <p id="vlm-key-help" className="lx-muted">{keyRequired ? 'Nhập API key cho kết nối này.' : 'Để trống để giữ API key đã lưu.'} API key được mã hóa và không hiển thị lại.</p>
            </div>
          </>}
          </div>
          {error && <p role="alert">{error}</p>}
          {saved && <p role="status">Đã lưu cấu hình VLM. Tạo phiên bản cấu hình QC mới và bật VLM để sử dụng.</p>}
          <div className="lx-gap__actions">
            <button className="lx-btn" type="button" disabled={busy} onClick={() => dialog.current?.close()}>Đóng</button>
            <button className="lx-btn" type="button" disabled={busy || loading} onClick={reload}>Tải lại</button>
            {canWrite && <button className="lx-btn lx-btn--primary" type="submit" disabled={!settings || busy || loading}>{busy ? 'Đang lưu…' : 'Lưu cấu hình VLM'}</button>}
          </div>
        </form>
      </div>
    </dialog>
  );
}
