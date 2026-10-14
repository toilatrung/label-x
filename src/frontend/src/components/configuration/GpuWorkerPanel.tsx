'use client';

import React, { useEffect, useState } from 'react';
import { apiClient, ApiRequestError } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import type { components } from '@/lib/api/contract';

type Config = components['schemas']['WorkerConfig'];
type Envelope = components['schemas']['WorkerEnvelope'];
type Probe = components['schemas']['WorkerProbe'];
const EMPTY: Config = { revision: 0, name: '', url: '', credential_ref: '', enabled: true, timeout_seconds: 120 };
const STATES = { ready: 'Sẵn sàng', unavailable: 'Không sẵn sàng', disabled: 'Đã tắt' };

export function GpuWorkerPanel() {
  const [saved, setSaved] = useState<Envelope | null>(null);
  const [form, setForm] = useState<Config>(EMPTY);
  const [result, setResult] = useState<Probe | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const dirty = !saved?.config || JSON.stringify(saved.config) !== JSON.stringify(form);

  useEffect(() => {
    const controller = new AbortController();
    apiClient.GET('/api/gpu-worker/config/', { signal: controller.signal, cache: 'no-store' })
      .then(({ data, error, response }) => {
        if (controller.signal.aborted) return;
        if (error || !data) throw new ApiRequestError(response.status, error, response.headers);
        setSaved(data); setForm(data.config ?? EMPTY);
      }).catch((e: unknown) => { if (!controller.signal.aborted) setError(errorMessage(e)); })
      .finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => controller.abort();
  }, []);

  function change<K extends keyof Config>(key: K, value: Config[K]) {
    setForm(old => ({ ...old, [key]: value }));
    setResult(null); setNotice(null);
  }

  async function act(action: 'save' | 'probe' | 'reload') {
    setBusy(true); setError(null); setNotice(null); setResult(null);
    try {
      if (action === 'probe') {
        const reply = await apiClient.POST('/api/gpu-worker/probe/', { body: { revision: form.revision } });
        if (reply.error || !reply.data) throw new ApiRequestError(reply.response.status, reply.error, reply.response.headers);
        setResult(reply.data); // 200 is NOT success: only state=ready means ready.
      } else {
        const reply = action === 'save'
          ? await apiClient.PUT('/api/gpu-worker/config/', { body: form })
          : await apiClient.GET('/api/gpu-worker/config/', { cache: 'no-store' });
        if (reply.error || !reply.data) throw new ApiRequestError(reply.response.status, reply.error, reply.response.headers);
        setSaved(reply.data); setForm(reply.data.config ?? EMPTY);
        if (action === 'save') setNotice('Đã lưu cấu hình. Chỉ áp dụng cho run mới; hãy kiểm tra kết nối.');
      }
    } catch (e: unknown) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  }

  return <div className="lx-card__body lx-stack" aria-busy={busy}>
    <p className="lx-muted">Kết nối máy GPU qua HTTPS trong Tailscale. Cấu hình mới chỉ áp dụng cho run mới.</p>
    {busy && <p role="status">Đang xử lý…</p>}
    {error && <div className="lx-notice lx-notice--warning" role="alert">{error}</div>}
    {notice && <p role="status">{notice}</p>}
    {saved && <>
      {!saved.credential_refs.length && <p className="lx-notice lx-notice--warning">Quản trị server cần khai báo credential trước khi lưu.</p>}
      <form className="lx-stack" aria-label="Cấu hình GPU Worker" onSubmit={e => { e.preventDefault(); void act('save'); }}>
        <fieldset disabled={busy} className="lx-fieldset lx-stack">
          <div className="lx-scroll"><table className="lx-table"><thead><tr><th>Thông số</th><th>Giá trị</th></tr></thead><tbody>
            <tr><td><label htmlFor="worker-name">Tên worker</label></td><td><input id="worker-name" className="lx-input" value={form.name} maxLength={128} required onChange={e => change('name', e.target.value)} /></td></tr>
            <tr><td><label htmlFor="worker-url">Địa chỉ HTTPS Tailscale</label></td><td><input id="worker-url" className="lx-input" type="url" value={form.url} maxLength={255} placeholder="https://gpu-worker.tailnet.ts.net" required onChange={e => change('url', e.target.value)} /><small className="lx-hint">Chỉ chấp nhận hostname được quản trị server cho phép: {saved.allowed_hosts.join(', ') || 'chưa khai báo'}.</small></td></tr>
            <tr><td><label htmlFor="worker-credential">Credential trên server</label></td><td><select id="worker-credential" className="lx-select" value={form.credential_ref} required onChange={e => change('credential_ref', e.target.value)}><option value="">Chọn credential</option>{saved.credential_refs.map(ref => <option key={ref} value={ref}>{ref}</option>)}</select><small className="lx-hint">Không nhập hoặc hiển thị token trên giao diện.</small></td></tr>
            <tr><td><label htmlFor="worker-timeout">Thời gian chờ inference (giây)</label></td><td><input id="worker-timeout" className="lx-input" type="number" min={10} max={1800} value={form.timeout_seconds} required onChange={e => change('timeout_seconds', Number(e.target.value))} /></td></tr>
            <tr><td><label htmlFor="worker-enabled">Sử dụng cho run mới</label></td><td><input id="worker-enabled" type="checkbox" checked={form.enabled} onChange={e => change('enabled', e.target.checked)} /></td></tr>
          </tbody></table></div>
          <div className="lx-actions"><button className="lx-btn lx-btn--primary" type="submit" disabled={!dirty || !saved.credential_refs.length}>Lưu cấu hình</button><button className="lx-btn" type="button" disabled={dirty || !form.revision} onClick={() => void act('probe')}>Kiểm tra kết nối</button><button className="lx-btn" type="button" onClick={() => void act('reload')}>Tải lại</button></div>
        </fieldset>
      </form>
      <p className="lx-hint">Lưu trước khi kiểm tra kết nối. Chưa kiểm tra không đồng nghĩa worker sẵn sàng.</p>
      <div className="lx-scroll"><table className="lx-table" aria-label="Trạng thái GPU Worker"><thead><tr><th>Trạng thái</th><th>Thiết bị</th><th>Model</th><th>Checksum</th><th>Kiểm tra lúc</th></tr></thead><tbody><tr>
        <td><span className={`lx-badge${result?.state === 'ready' ? ' lx-badge--success' : result?.state === 'unavailable' ? ' lx-badge--warning' : ''}`}>{result ? STATES[result.state] : 'Chưa kiểm tra'}</span></td>
        <td>{result?.device ?? '—'}</td><td>{result?.model?.version ?? '—'}</td><td className="lx-mono">{result?.model?.sha256 ?? '—'}</td><td>{result ? new Date(result.checked_at).toLocaleString('vi-VN') : '—'}</td>
      </tr></tbody></table></div>
      {result && <p role="status">{result.message}</p>}
    </>}
    {!saved && !busy && <button type="button" className="lx-btn" onClick={() => void act('reload')}>Thử lại</button>}
  </div>;
}
