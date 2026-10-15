'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { errorMessage } from '@/lib/api/errors';
import { listDetectorArtifacts, registerDetectorArtifact, type RegisteredDetector } from '@/lib/execution/api';

interface Props {
  onClose: () => void;
  onSelected: (model: RegisteredDetector) => void;
  initialModel?: RegisteredDetector;
  canRegister: boolean;
}

export function DetectorSettingsModal({ onClose, onSelected, initialModel, canRegister }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [artifacts, setArtifacts] = useState<RegisteredDetector[]>([]);
  const [artifactId, setArtifactId] = useState(initialModel ? String(initialModel.id) : '');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (document.activeElement instanceof HTMLElement) opener.current = document.activeElement;
    dialog.current?.showModal();
    const controller = new AbortController();
    listDetectorArtifacts(controller.signal).then(values => {
      if (!controller.signal.aborted) setArtifacts(values);
    }).catch(err => { if (!controller.signal.aborted) setError(errorMessage(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  async function register() {
    if (busy || !canRegister) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const values = await registerDetectorArtifact();
      setArtifacts(values);
      setNotice('Đã xác minh và đăng ký model từ worker. Chọn model trong danh sách để xem thông tin.');
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  const selected = artifacts.find(model => String(model.id) === artifactId);
  return <dialog ref={dialog} className="lx-gap-dialog" aria-labelledby="detector-model-title"
    onClose={() => { onClose(); requestAnimationFrame(() => opener.current?.focus()); }}
    onCancel={event => { if (busy) event.preventDefault(); }}
    onClick={event => { if (event.target === dialog.current && !busy) dialog.current?.close(); }}>
    <div className="lx-gap">
      <header className="lx-gap__head"><div>
        <h2 id="detector-model-title">Chỉnh Detector</h2>
        <p>Chọn và đăng ký model Detector. Thiết lập engine, ngưỡng và phiên bản cấu hình tại <Link href="/analysis/config">Analysis Configuration</Link>.</p>
      </div><button type="button" className="lx-gap__close" aria-label="Đóng hộp thoại" disabled={busy} onClick={() => dialog.current?.close()}>×</button></header>
      <div className="lx-gap__body lx-stack">
        <div className="lx-field"><label className="lx-label" htmlFor="detector-artifact">Model Detector</label>
          <select id="detector-artifact" className="lx-select" value={artifactId} disabled={loading || busy} onChange={event => setArtifactId(event.target.value)}>
            <option value="">{loading ? 'Đang tải model…' : 'Chọn model đã đăng ký'}</option>
            {artifacts.map(model => <option key={model.id} value={model.id}>{model.name} · {model.version}</option>)}
          </select>
          {!loading && artifacts.length === 0 && <p>Chưa có model Detector đã đăng ký.</p>}
          {selected && <p className="lx-hint">Ánh xạ: {selected.class_mapping_version} · Checksum: <span className="lx-mono">{selected.checksum}</span></p>}
          <p className="lx-hint">Lựa chọn dùng để xem model tại màn này. Model chạy phân tích được ghim trong phiên bản cấu hình tại Analysis Configuration.</p>
        </div>
        <button type="button" className="lx-btn" disabled={!canRegister || busy || loading} onClick={register}>{busy ? 'Đang xác minh…' : 'Đăng ký model từ worker'}</button>
        <p className="lx-hint">Đăng ký model từ manifest đã cấu hình trên server sau khi xác minh worker, checksum và ánh xạ lớp.</p>
        {error && <p role="alert">{error}</p>}
        {notice && <p role="status">{notice}</p>}
        <div className="lx-gap__actions">
          <button type="button" className="lx-btn" disabled={busy} onClick={() => dialog.current?.close()}>Đóng</button>
          <button type="button" className="lx-btn lx-btn--primary" disabled={!selected || busy} onClick={() => { if (selected) onSelected(selected); dialog.current?.close(); }}>Chọn model</button>
        </div>
      </div>
    </div>
  </dialog>;
}
