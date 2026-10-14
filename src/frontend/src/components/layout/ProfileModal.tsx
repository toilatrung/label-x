'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { errorMessage } from '@/lib/api/errors';
import { deleteProfileToken, getProfile, saveProfile, type Profile } from '@/lib/auth/profile-api';

export function ProfileModal({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const { user } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const changed = useRef(false);

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal();
    const controller = new AbortController();
    getProfile(controller.signal).then(value => {
      if (!controller.signal.aborted) setProfile(value);
    }).catch(err => {
      if (!controller.signal.aborted) setError(errorMessage(err));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!profile || busy || !token) return;
    setBusy(true); setError(null); setSaved(false); setDeleted(false);
    try {
      setProfile(await saveProfile(token));
      changed.current = true; setSaved(true);
    } catch (err) { setError(errorMessage(err)); }
    finally { setToken(''); setBusy(false); }
  }

  async function removeToken() {
    if (!profile?.cvat_token_saved || busy) return;
    setBusy(true); setError(null); setSaved(false); setDeleted(false);
    try {
      setProfile(await deleteProfileToken());
      setToken(''); changed.current = true; setDeleted(true);
    } catch (err) { setError(errorMessage(err)); }
    finally { setBusy(false); }
  }

  function close() {
    // Reload the current screen after saving so Dataset selectors use the new credential.
    if (changed.current) window.location.reload();
    else dialog.current?.close();
  }

  return <dialog ref={dialog} className="lx-gap-dialog" aria-labelledby="profile-title"
    aria-describedby="profile-description" onClose={onClose}
    onCancel={event => { event.preventDefault(); if (!busy) close(); }}
    onClick={event => { if (event.target === dialog.current && !busy) close(); }}>
    <div className="lx-gap">
      <header className="lx-gap__head">
        <div><h2 id="profile-title">Hồ sơ</h2><p id="profile-description">{user?.fullName}</p></div>
        <button type="button" className="lx-gap__close" aria-label="Đóng hộp thoại" disabled={busy} onClick={close}>×</button>
      </header>
      <form className="lx-gap__body" onSubmit={submit}>
        <p className="lx-muted">Lưu token CVAT cho tài khoản Label-X của bạn để đọc Dataset, Task và Job.</p>
        {loading && <p role="status">Đang tải hồ sơ…</p>}
        <div className="lx-gap__fields">
          <div className="lx-field"><label className="lx-label" htmlFor="profile-cvat-token">CVAT_SERVICE_TOKEN</label>
            <div className="lx-profile-token">
            <input id="profile-cvat-token" className="lx-input" type="password" autoComplete="new-password"
              required maxLength={4096} value={token} disabled={loading || busy || !profile}
              onChange={event => { setToken(event.target.value); setSaved(false); setDeleted(false); }}
              aria-describedby="profile-token-help" placeholder={profile?.cvat_token_configured ? 'Nhập token mới để thay thế' : 'Nhập token CVAT'} />
            {profile?.cvat_token_saved && <button className="lx-profile-token__delete" type="button" disabled={busy || loading}
              aria-label="Xóa token CVAT hiện tại" title="Xóa token CVAT đã lưu" onClick={() => { void removeToken(); }}>Xóa token</button>}
            </div>
            <p id="profile-token-help" className="lx-muted">Dùng token CVAT có quyền đọc. Token được mã hóa và không hiển thị lại.</p>
          </div>
          {profile && <p className={`lx-profile-status${profile.cvat_token_configured ? ' is-configured' : ''}`} role="status">
            <span className="lx-profile-status__light" aria-hidden="true" />{profile.cvat_token_configured ? 'Đã cấu hình token CVAT.' : 'Chưa cấu hình token CVAT.'}</p>}
        </div>
        {error && <p className="lx-gap__error" role="alert">{error}</p>}
        {deleted && <p role="status">Đã xóa token CVAT trong Hồ sơ.{profile?.cvat_token_configured ? ' Đang dùng token mặc định của máy chủ.' : ''} Đóng Hồ sơ để tải lại dữ liệu.</p>}
        {saved && <p role="status">Đã lưu token CVAT. Đóng Hồ sơ để tải lại dữ liệu.</p>}
        <div className="lx-gap__actions">
          <button className="lx-btn" type="button" disabled={busy} onClick={close}>Đóng</button>
          <button className="lx-btn lx-btn--primary" type="submit" disabled={!profile || loading || busy || !token}>{busy ? 'Đang lưu…' : 'Lưu'}</button>
        </div>
      </form>
    </div>
  </dialog>;
}
