'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, hasDatasetPermission } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import { ApiRequestError } from '@/lib/api/client';
import { DatasetPicker } from '@/lib/execution/DatasetPicker';
import { createConfig, createRun, cursorFrom, listConfigs, listSnapshots, publishConfig, type ConfigVersion, type ConfigVersionCreate, type RunCreate } from '@/lib/execution/api';
import { EngineThresholdsTable } from '@/components/execution/EngineThresholdsTable';

const ENGINES = ['schema', 'geometry', 'duplicate', 'detector', 'metric', 'vlm'] as const;

function ConfigContent() {
  const { session, datasetId } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const canCreate = hasDatasetPermission(session, datasetId, (role) => role === 'qa_lead' || role === 'super_admin');
  const canConfigure = session?.roles.some(({ role }) => role === 'qc_admin' || role === 'super_admin') ?? false;
  const [snapshotCursor, setSnapshotCursor] = useState<string | null>(null);
  const [configCursor, setConfigCursor] = useState<string | null>(null);
  const [snapshotId, setSnapshotId] = useState<number | null>(null);
  const [configId, setConfigId] = useState<number | null>(null);
  const [selectedConfigRecord, setSelectedConfigRecord] = useState<ConfigVersion | null>(null);
  const [seed, setSeed] = useState(42);
  const [pending, setPending] = useState<{ body: RunCreate; key: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [configName, setConfigName] = useState('');
  const [enabledEngines, setEnabledEngines] = useState<string[]>(['schema', 'geometry', 'duplicate']);
  const [thresholdsText, setThresholdsText] = useState('{}');
  const [modelsText, setModelsText] = useState('{}');
  const [configPending, setConfigPending] = useState<{ body: ConfigVersionCreate; key: string } | null>(null);
  const [draftId, setDraftId] = useState<number | null>(null);
  const [configBusy, setConfigBusy] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);
  const snapshots = useQuery({ queryKey: ['analysis-snapshots', session?.user.id, datasetId, snapshotCursor], queryFn: ({ signal }) => listSnapshots(datasetId!, snapshotCursor, signal), enabled: datasetId !== null, retry: false });
  const configs = useQuery({ queryKey: ['analysis-configs', session?.user.id, configCursor], queryFn: ({ signal }) => listConfigs(configCursor, signal), enabled: !!session, retry: false });
  const locked = snapshots.data?.results.filter((s) => s.status === 'locked') ?? [];
  const activeConfig = selectedConfigRecord?.id === configId
    ? selectedConfigRecord
    : (configs.data?.results.find((c) => c.id === configId) ?? null);
  const selectedConfig = activeConfig;
  const selectedSnapshot = locked.find((s) => s.id === snapshotId);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canCreate || !snapshotId || !configId || submitting) return;
    const body = { snapshot_id: snapshotId, config_version_id: configId, seed };
    const request = pending && JSON.stringify(pending.body) === JSON.stringify(body) ? pending : { body, key: crypto.randomUUID() };
    setPending(request);
    setSubmitError(null);
    setSubmitting(true);
    try {
      const run = await createRun(request.body, request.key);
      setPending(null);
      router.push(`/analysis/history?run=${run.id}`);
    } catch (err) {
      setSubmitError(errorMessage(err));
      // Keep the idempotency key if the server may have accepted the request.
      if (err instanceof ApiRequestError && err.status < 500 && err.status !== 0) setPending(null);
    } finally { setSubmitting(false); }
  }

  async function saveConfig(event: React.FormEvent) {
    event.preventDefault();
    if (!canConfigure || configBusy || !configName.trim() || enabledEngines.length === 0) return;
    let thresholds: Record<string, unknown>;
    let models: Record<string, unknown>;
    try {
      thresholds = JSON.parse(thresholdsText);
      models = JSON.parse(modelsText);
      if (!thresholds || typeof thresholds !== 'object' || Array.isArray(thresholds) || !models || typeof models !== 'object' || Array.isArray(models)) throw new Error();
    } catch { setConfigError('Ngưỡng và model phải là đối tượng JSON hợp lệ.'); return; }
    const body: ConfigVersionCreate = { name: configName.trim(), engines: Object.fromEntries(ENGINES.map((engine) => [engine, { enabled: enabledEngines.includes(engine) }])), thresholds, models };
    const request = configPending && JSON.stringify(configPending.body) === JSON.stringify(body) ? configPending : { body, key: crypto.randomUUID() };
    setConfigPending(request);
    setConfigBusy(true); setConfigError(null);
    try {
      const draft = await createConfig(request.body, request.key);
      setDraftId(draft.id);
      const published = draft.status === 'published' ? draft : await publishConfig(draft.id);
      setDraftId(null);
      setConfigPending(null);
      setConfigCursor(null);
      await queryClient.invalidateQueries({ queryKey: ['analysis-configs', session?.user.id] });
      setConfigId(published.id);
      setSelectedConfigRecord(published);
    } catch (err) {
      setConfigError(errorMessage(err));
    } finally { setConfigBusy(false); }
  }

  async function retryPublish() {
    if (!draftId || configBusy) return;
    setConfigBusy(true); setConfigError(null);
    try {
      const replay = configPending ? await createConfig(configPending.body, configPending.key) : null;
      const published = replay?.status === 'published' ? replay : await publishConfig(draftId);
      setDraftId(null); setConfigPending(null); setConfigCursor(null);
      await queryClient.invalidateQueries({ queryKey: ['analysis-configs', session?.user.id] });
      setConfigId(published.id);
      setSelectedConfigRecord(published);
    } catch (err) { setConfigError(errorMessage(err)); }
    finally { setConfigBusy(false); }
  }

  return <AppShell activeKey="analysis" flowStep={2} pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Cấu hình phân tích</h1><p className="lx-lead">Chọn snapshot đã khóa và phiên bản cấu hình đã phát hành để tạo QC run.</p></div></div>}>
    <div className="lx-execution-nav"><Link href="/analysis/history" className="lx-btn">Lịch sử thực thi</Link></div>
    <section className="lx-card lx-card__body lx-stack" aria-label="Tạo QC run">
      <form onSubmit={submit} className="lx-stack">
        <DatasetPicker onChange={() => { setSnapshotCursor(null); setSnapshotId(null); setPending(null); }} />
        <div className="lx-field"><label htmlFor="analysis-snapshot">Snapshot đã khóa</label><select id="analysis-snapshot" value={snapshotId ?? ''} onChange={(e) => { setSnapshotId(e.target.value ? Number(e.target.value) : null); setPending(null); }} disabled={!datasetId || snapshots.isPending}>
          <option value="">Chọn snapshot</option>{locked.map((s) => <option key={s.id} value={s.id}>SNP-{s.id} · {s.revision_hash?.slice(0, 12) ?? 'Chưa có hash'}</option>)}
        </select></div>
        {snapshots.isError && <p role="alert">{errorMessage(snapshots.error)}</p>}
        {datasetId && snapshots.data && locked.length === 0 && <p className="lx-muted">Dataset này chưa có snapshot đã khóa.</p>}
        {snapshots.data?.next && <button type="button" className="lx-btn lx-btn--sm" onClick={() => setSnapshotCursor(cursorFrom(snapshots.data?.next))}>Trang snapshot tiếp</button>}
        <div className="lx-field"><label htmlFor="analysis-config">Phiên bản cấu hình</label><select id="analysis-config" value={configId ?? ''} onChange={(e) => { const nextId = e.target.value ? Number(e.target.value) : null; setConfigId(nextId); setSelectedConfigRecord(configs.data?.results.find((c) => c.id === nextId) ?? (selectedConfigRecord?.id === nextId ? selectedConfigRecord : null)); setPending(null); }} disabled={configs.isPending}>
          <option value="">Chọn config đã publish</option>
          {selectedConfigRecord && !configs.data?.results.some((c) => c.id === selectedConfigRecord.id) && (
            <option key={selectedConfigRecord.id} value={selectedConfigRecord.id}>{selectedConfigRecord.name} · v{selectedConfigRecord.id} (đang chọn)</option>
          )}
          {configs.data?.results.map((c) => <option key={c.id} value={c.id}>{c.name} · v{c.id}</option>)}
        </select></div>
        {configs.isError && <p role="alert">{errorMessage(configs.error)}</p>}
        {configs.data?.results.length === 0 && <p role="alert" className="lx-callout">Chưa có config version đã publish. QC Admin hoặc Super Admin cần tạo và publish một phiên bản trước khi tạo run.</p>}
        {configs.data?.next && <button type="button" className="lx-btn lx-btn--sm" onClick={() => setConfigCursor(cursorFrom(configs.data?.next))}>Trang config tiếp</button>}
        <div className="lx-execution-config">
          <EngineThresholdsTable
            config={activeConfig}
            isLoading={configs.isPending}
            error={configs.isError ? errorMessage(configs.error) : null}
            emptyTitle={configs.data?.results.length === 0 ? 'Chưa có cấu hình đã phát hành' : 'Chưa chọn phiên bản cấu hình'}
            emptyDescription={configs.data?.results.length === 0
              ? 'API chưa trả về phiên bản cấu hình engine đã phát hành. Không thể xác nhận ngưỡng từ dữ liệu hiện có; riêng việc thiếu cấu hình published không xác định trạng thái engine đang chạy.'
              : 'Vui lòng chọn một phiên bản cấu hình đã phát hành từ danh sách phía trên để xem chi tiết ngưỡng kiểm tra engine.'}
          />
          {activeConfig && <pre className="lx-code" aria-label="Ngưỡng và model tham chiếu">{JSON.stringify({ thresholds: activeConfig.thresholds, models: activeConfig.models }, null, 2)}</pre>}
        </div>
        {selectedSnapshot && <p>Snapshot SNP-{selectedSnapshot.id}: <strong>{selectedSnapshot.status}</strong></p>}
        <div className="lx-field"><label htmlFor="analysis-seed">Seed</label><input id="analysis-seed" type="number" value={seed} onChange={(e) => { setSeed(Number(e.target.value)); setPending(null); }} /></div>
        {!canCreate && <p className="lx-muted">Vai trò hiện tại chỉ được xem cấu hình và lịch sử; QA Lead hoặc Super Admin mới được tạo run.</p>}
        {submitError && <p role="alert" className="lx-callout">{submitError}</p>}
        <button type="submit" className="lx-btn lx-btn--primary" disabled={!canCreate || !selectedSnapshot || !selectedConfig || submitting}>{submitting ? 'Đang tạo…' : 'Tạo QC run'}</button>
      </form>
    </section>
    {canConfigure && <section className="lx-card lx-card__body lx-stack" aria-label="Tạo phiên bản cấu hình">
      <h2 className="lx-h2">Tạo phiên bản cấu hình</h2>
      <p className="lx-muted">Một phiên bản mới sẽ được phát hành để QA Lead chọn khi chạy QC. Phiên bản đã phát hành không chỉnh sửa trực tiếp.</p>
      <form onSubmit={saveConfig} className="lx-stack">
        <div className="lx-field"><label htmlFor="config-name">Tên cấu hình</label><input id="config-name" value={configName} maxLength={128} onChange={(e) => { setConfigName(e.target.value); setConfigPending(null); }} required /></div>
        <fieldset><legend>Engine cần chạy</legend><div className="lx-execution-actions">{ENGINES.map((engine) => <label key={engine}><input type="checkbox" checked={enabledEngines.includes(engine)} onChange={(e) => { setEnabledEngines((current) => e.target.checked ? [...current, engine] : current.filter((item) => item !== engine)); setConfigPending(null); }} /> {engine}</label>)}</div></fieldset>
        <div className="lx-field"><label htmlFor="config-thresholds">Ngưỡng kiểm tra (JSON)</label><textarea id="config-thresholds" rows={3} value={thresholdsText} onChange={(e) => { setThresholdsText(e.target.value); setConfigPending(null); }} /></div>
        <div className="lx-field"><label htmlFor="config-models">Model tham chiếu (JSON)</label><textarea id="config-models" rows={3} value={modelsText} onChange={(e) => { setModelsText(e.target.value); setConfigPending(null); }} /></div>
        {configError && <p role="alert" className="lx-callout">{configError}</p>}
        {draftId && <div className="lx-callout">Config v{draftId} đã được tạo nhưng chưa xác nhận publish. <button type="button" className="lx-btn" disabled={configBusy} onClick={retryPublish}>Thử publish lại</button></div>}
        {enabledEngines.length === 0 && <p role="alert">Cần bật ít nhất một engine.</p>}
        <button type="submit" className="lx-btn lx-btn--primary" disabled={configBusy || !configName.trim() || enabledEngines.length === 0}>{configBusy ? 'Đang lưu…' : 'Tạo và publish config'}</button>
      </form>
    </section>}
  </AppShell>;
}

export default function AnalysisConfigPage() {
  return <AuthGuard permissionCheck={canAccessAnalysis} requiredPermissionName="Quyền Phân tích Chất lượng"><ConfigContent /></AuthGuard>;
}
