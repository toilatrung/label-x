'use client';

import React, { useEffect, useRef, useState } from 'react';
import { errorMessage } from '@/lib/api/errors';
import { createConfig, publishConfig, listDetectorArtifacts, getConfigRules, type RegisteredDetector, type ConfigVersion, type ConfigVersionCreate } from '@/lib/execution/api';
import { ENGINES_META } from '@/components/execution/EngineThresholdsTable';

const ENGINES = ['schema', 'geometry', 'duplicate', 'detector', 'metric', 'vlm'] as const;

interface Props {
  onClose: () => void;
  onPublished: (config: ConfigVersion) => void | Promise<void>;
  initialConfig?: ConfigVersion | null;
}

/** Analysis owns engine settings and immutable QC configuration publishing. */
export function ConfigVersionModal({ onClose, onPublished, initialConfig }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const nameField = useRef<HTMLInputElement>(null);
  const [name, setName] = useState('');
  const baseEngines = (initialConfig?.engines ?? {}) as Record<string, { enabled?: boolean; params?: Record<string, unknown> }>;
  const [enabledEngines, setEnabledEngines] = useState<string[]>(initialConfig
    ? (baseEngines.metric?.enabled ? ['metric'] : ENGINES.filter(engine => baseEngines[engine]?.enabled))
    : ['schema', 'geometry', 'duplicate']);
  const [thresholdsText, setThresholdsText] = useState(JSON.stringify(initialConfig?.thresholds ?? {}, null, 2));
  const [artifacts, setArtifacts] = useState<RegisteredDetector[]>([]);
  const [artifactId, setArtifactId] = useState('');
  const [loadingModels, setLoadingModels] = useState(true);
  const [basePolicy, setBasePolicy] = useState<Awaited<ReturnType<typeof getConfigRules>> | null>(null);
  const [baseReady, setBaseReady] = useState(!initialConfig);
  const [confidence, setConfidence] = useState(String(baseEngines.metric?.params?.score_threshold ?? baseEngines.detector?.params?.score_threshold ?? 0.05));
  const [pending, setPending] = useState<{ body: ConfigVersionCreate; key: string } | null>(null);
  const [draftId, setDraftId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tried, setTried] = useState(false);
  const needsModel = enabledEngines.includes('detector') || enabledEngines.includes('metric');

  function toggleEngine(engine: string, checked: boolean) {
    setEnabledEngines(current => {
      if (!checked) return current.filter(item => item !== engine);
      if (engine === 'metric') return ['metric'];
      return [...current.filter(item => item !== 'metric'), engine];
    });
    reset();
  }

  useEffect(() => {
    if (!opener.current && document.activeElement instanceof HTMLElement) opener.current = document.activeElement;
    dialog.current?.showModal();
    nameField.current?.focus();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([listDetectorArtifacts(controller.signal), initialConfig ? getConfigRules(initialConfig.id, controller.signal) : Promise.resolve(null)]).then(([values, policy]) => {
      if (controller.signal.aborted) return;
      setArtifacts(values);
      setBasePolicy(policy);
      setBaseReady(true);
      const models = initialConfig?.models as Record<string, unknown> | undefined;
      const selected = values.find(value => value.name === models?.name && value.version === models?.version);
      setArtifactId(selected ? String(selected.id) : '');
    }).catch(err => { if (!controller.signal.aborted) setError(errorMessage(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoadingModels(false); });
    return () => controller.abort();
  }, [initialConfig]);

  async function finish(published: ConfigVersion) {
    setDraftId(null);
    setPending(null);
    await onPublished(published);
    dialog.current?.close();
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !baseReady) return;
    setTried(true);
    if (!name.trim()) return nameField.current?.focus();
    if (enabledEngines.length === 0) return;
    let thresholds: Record<string, unknown>;
    const artifact = artifacts.find(value => String(value.id) === artifactId);
    if (needsModel && !artifact) { setError('Chọn model Detector đã đăng ký trước khi tạo cấu hình.'); return; }
    const score = Number(confidence);
    if (needsModel && (!confidence.trim() || !Number.isFinite(score) || score < 0 || score > 1)) {
      setError('Ngưỡng tin cậy Detector phải từ 0 đến 1.'); return;
    }
    try {
      thresholds = JSON.parse(thresholdsText);
      if (!thresholds || typeof thresholds !== 'object' || Array.isArray(thresholds)) throw new Error();
    } catch { setError('Ngưỡng phải là đối tượng JSON hợp lệ.'); return; }
    const models = { ...initialConfig?.models, ...(artifact ? { name: artifact.name, version: artifact.version } : {}) };
    const body: ConfigVersionCreate = { name: name.trim(), ...(basePolicy ? { rules: basePolicy.rules, sampling_policy: basePolicy.sampling_policy, release_thresholds: basePolicy.release_thresholds } : {}), engines: Object.fromEntries(ENGINES.map((engine) => [engine,
      { ...baseEngines[engine], enabled: enabledEngines.includes(engine), ...(['detector', 'metric'].includes(engine) && enabledEngines.includes(engine) ? { params: { ...baseEngines[engine]?.params, score_threshold: score } } : {}) }])), thresholds, models };
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
      onCancel={event => { if (busy) event.preventDefault(); }}
      onClick={(event) => { if (event.target === dialog.current && !busy) dialog.current?.close(); }}>
      <div className="lx-gap">
        <header className="lx-gap__head">
          <div>
            <h2 id="config-version-title">Tạo phiên bản cấu hình</h2>
            <p id="config-version-description">Chọn engine, model và ngưỡng cho phiên bản mới. Run cũ giữ nguyên phiên bản đã dùng.</p>
          </div>
          <button type="button" className="lx-gap__close" aria-label="Đóng hộp thoại" disabled={busy} onClick={() => dialog.current?.close()}>×</button>
        </header>
        <form className="lx-gap__body" noValidate onSubmit={submit}>
          <fieldset className="lx-gap__fields lx-fieldset" disabled={busy || draftId !== null}>
            <div className="lx-field">
              <label className="lx-label" htmlFor="config-name">Tên cấu hình *</label>
              <input ref={nameField} className="lx-input" id="config-name" value={name} maxLength={128} onChange={(e) => { setName(e.target.value); reset(); }} aria-invalid={tried && !name.trim()} aria-describedby={tried && !name.trim() ? 'config-name-error' : undefined} />
              {tried && !name.trim() && <span id="config-name-error" className="lx-gap__error">Nhập tên cấu hình.</span>}
            </div>
            <fieldset className="lx-field lx-fieldset">
              <legend className="lx-label">Engine cần chạy *</legend>
              <div className="lx-card lx-card--inner"><table className="lx-table"><tbody>{ENGINES_META.map((meta) => <tr key={meta.key}>
                <td className="lx-th--check"><label className="lx-switch"><input type="checkbox" aria-label={meta.name} disabled={busy || draftId !== null} checked={enabledEngines.includes(meta.key)} onChange={(e) => toggleEngine(meta.key, e.target.checked)} /><span /></label></td>
                <td><div className="lx-cell__main">{meta.name}</div><div className="lx-cell__sub">{meta.sub}</div></td>
              </tr>)}</tbody></table></div>
              {enabledEngines.length === 0 && <span role="alert" className="lx-gap__error">Cần bật ít nhất một engine.</span>}
            </fieldset>
            <div className="lx-field"><label className="lx-label" htmlFor="config-thresholds">Ngưỡng kiểm tra (JSON)</label><textarea className="lx-textarea" id="config-thresholds" rows={3} value={thresholdsText} onChange={(e) => { setThresholdsText(e.target.value); reset(); }} /></div>
            {needsModel && <><div className="lx-field"><label className="lx-label" htmlFor="detector-artifact">Model Detector</label>
              <select id="detector-artifact" className="lx-select" required value={artifactId} disabled={busy || loadingModels || draftId !== null} onChange={e => { setArtifactId(e.target.value); reset(); }}>
                <option value="">{loadingModels ? 'Đang tải model…' : 'Chọn model đã đăng ký'}</option>
                {artifacts.map(artifact => <option key={artifact.id} value={artifact.id}>{artifact.name} · {artifact.version}</option>)}
              </select>
              {!loadingModels && artifacts.length === 0 && <p role="alert">Chưa có model Detector đã đăng ký. Đăng ký model tại Models & Guidelines trước.</p>}
              {artifacts.filter(artifact => String(artifact.id) === artifactId).map(artifact => <p key={artifact.id} className="lx-hint">Ánh xạ: {artifact.class_mapping_version} · Checksum: <span className="lx-mono">{artifact.checksum}</span></p>)}
            </div>
            <div className="lx-field"><label className="lx-label" htmlFor="detector-confidence">Ngưỡng tin cậy Detector</label>
              <input id="detector-confidence" className="lx-input" type="number" min="0" max="1" step="0.01" required disabled={busy || draftId !== null} value={confidence} onChange={e => { setConfidence(e.target.value); reset(); }} />
            </div></>}
          </fieldset>
          {error && <div className="lx-gap__notice" role="alert"><strong>Không tạo được phiên bản cấu hình.</strong> {error}</div>}
          {draftId && <div className="lx-gap__notice">Phiên bản v{draftId} đã được tạo nhưng chưa xác nhận phát hành. <button type="button" className="lx-btn lx-btn--sm" disabled={busy} onClick={retryPublish}>Thử phát hành lại</button></div>}
          <div className="lx-gap__actions">
            <button type="button" className="lx-btn" disabled={busy} onClick={() => dialog.current?.close()}>Hủy</button>
            <button type="submit" className="lx-btn lx-btn--primary" disabled={busy || !baseReady || (needsModel && (loadingModels || !artifactId)) || enabledEngines.length === 0 || draftId !== null}>{busy ? 'Đang lưu…' : 'Tạo và phát hành'}</button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
