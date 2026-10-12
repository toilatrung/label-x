'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { FlowNav } from '@/components/layout/FlowNav';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, hasDatasetPermission } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import { ApiRequestError } from '@/lib/api/client';
import { DatasetPicker } from '@/lib/execution/DatasetPicker';
import { createConfig, createRun, cursorFrom, listConfigs, listSnapshots, publishConfig, type ConfigVersion, type ConfigVersionCreate, type RunCreate } from '@/lib/execution/api';
import { ENGINES_META, EngineThresholdsTable } from '@/components/execution/EngineThresholdsTable';
import { formatCount, shortRevision, snapshotCode } from '@/lib/format';

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
  const rawEngines = (activeConfig?.engines ?? {}) as Record<string, unknown>;
  const enabledEngineCount = ENGINES.filter((engine) => {
    const value = rawEngines[engine];
    return typeof value === 'object' && value !== null && (value as Record<string, unknown>).enabled === true;
  }).length;
  const frameCount = selectedSnapshot?.jobs?.reduce((total, job) => total + (job.frames?.length ?? 0), 0) ?? 0;
  const taskCount = selectedSnapshot?.jobs ? new Set(selectedSnapshot.jobs.map((job) => job.cvat_task_id)).size : 0;

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

  return <AppShell activeKey="analysis" flowStep={2} showFlowNav={false} pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Analysis Configuration</h1><p className="lx-lead">Chọn engine, đặt ngưỡng và chính sách lấy mẫu cho Snapshot. Engine không bật sẽ được ghi là Not checked, không bao giờ được xem là đạt.</p></div></div>}>
    <form onSubmit={submit} className="lx-cols">
      <div className="lx-main lx-stack">
        <div className="lx-execution-config">
          <EngineThresholdsTable
            config={activeConfig}
            layout="analysis"
            topSlot={<FlowNav flow="analysis" currentStep={2} variant="tabs" inCard />}
            isLoading={configs.isPending}
            error={configs.isError ? errorMessage(configs.error) : null}
            emptyTitle={configs.data?.results.length === 0 ? 'Chưa có cấu hình đã phát hành' : 'Chưa chọn phiên bản cấu hình'}
            emptyDescription={configs.data?.results.length === 0
              ? 'Chưa có phiên bản cấu hình engine đã phát hành. Trạng thái này không đồng nghĩa engine đang tắt.'
              : 'Chọn một phiên bản cấu hình đã phát hành ở cột "Sẵn sàng chạy" để xem chi tiết ngưỡng kiểm tra engine.'}
          />
          {activeConfig && <details className="lx-card lx-card__body"><summary>Ngưỡng và model tham chiếu (JSON)</summary>
            <pre className="lx-code" aria-label="Ngưỡng và model tham chiếu">{JSON.stringify({ thresholds: activeConfig.thresholds, models: activeConfig.models }, null, 2)}</pre></details>}
        </div>
        <section className="lx-card" aria-label="Lấy mẫu">
          <header className="lx-card__head"><h2 className="lx-h2">Lấy mẫu</h2><div className="lx-row"><Link className="lx-link lx-text-13" href="/calibration/audit-sampling">Xem chi tiết lấy mẫu</Link></div></header>
          {/* TODO(backend): add typed sampling policy fields to ConfigVersion instead of illustrative disabled controls. */}
          <div className="lx-card__body lx-stack">
            <div className="lx-grid lx-grid--3">
              <div className="lx-field"><label className="lx-label" htmlFor="random-sample">Kiểm tra ngẫu nhiên · số frame</label><input className="lx-input" id="random-sample" value="100" disabled /><span className="lx-hint">Dùng để ước lượng chất lượng toàn Dataset</span></div>
              <div className="lx-field"><label className="lx-label" htmlFor="risk-sample">Lấy mẫu theo rủi ro · số frame</label><input className="lx-input" id="risk-sample" value="100" disabled /><span className="lx-hint">Dùng để tìm lỗi, không suy ra tỷ lệ lỗi</span></div>
              <div className="lx-field"><label className="lx-label" htmlFor="risk-criteria">Tiêu chí rủi ro</label><select className="lx-select" id="risk-criteria" disabled><option>Bất đồng mô hình, lớp khó, vật thể nhỏ</option></select></div>
            </div>
          </div>
        </section>
      </div>
      <aside className="lx-card lx-side">
        <header className="lx-card__head"><h2 className="lx-h2">Sẵn sàng chạy</h2></header>
        <div className="lx-card__body lx-stack">
          <DatasetPicker onChange={() => { setSnapshotCursor(null); setSnapshotId(null); setPending(null); }} />
          <div className="lx-field"><label className="lx-label" htmlFor="analysis-snapshot">Snapshot đã khoá</label><select className="lx-select" id="analysis-snapshot" value={snapshotId ?? ''} onChange={(e) => { setSnapshotId(e.target.value ? Number(e.target.value) : null); setPending(null); }} disabled={!datasetId || snapshots.isPending}>
            <option value="">Chọn Snapshot</option>{locked.map((s) => <option key={s.id} value={s.id}>{snapshotCode(s.id)} · {shortRevision(s.revision_hash)}</option>)}
          </select></div>
          <div className="lx-field"><label className="lx-label" htmlFor="analysis-config">Phiên bản cấu hình</label><select className="lx-select" id="analysis-config" value={configId ?? ''} onChange={(e) => { const nextId = e.target.value ? Number(e.target.value) : null; setConfigId(nextId); setSelectedConfigRecord(configs.data?.results.find((c) => c.id === nextId) ?? (selectedConfigRecord?.id === nextId ? selectedConfigRecord : null)); setPending(null); }} disabled={configs.isPending}>
            <option value="">Chọn phiên bản đã phát hành</option>
            {selectedConfigRecord && !configs.data?.results.some((c) => c.id === selectedConfigRecord.id) && <option value={selectedConfigRecord.id}>{selectedConfigRecord.name} · v{selectedConfigRecord.id} (đang chọn)</option>}
            {configs.data?.results.map((c) => <option key={c.id} value={c.id}>{c.name} · v{c.id}</option>)}
          </select></div>
          {(snapshots.isError || configs.isError) && <div className="lx-callout" role="alert">{snapshots.isError ? errorMessage(snapshots.error) : errorMessage(configs.error)}</div>}
          {datasetId && snapshots.data && locked.length === 0 && <p className="lx-muted lx-text-13">Dataset này chưa có Snapshot đã khoá.</p>}
          {configs.data?.results.length === 0 && <div className="lx-callout lx-callout--neutral" role="status">Chưa có phiên bản cấu hình đã phát hành. Quality Control Admin hoặc Super Admin cần tạo và phát hành một phiên bản trước khi chạy phân tích.</div>}
          {(snapshots.data?.next || configs.data?.next) && <div className="lx-actions">{snapshots.data?.next && <button type="button" className="lx-btn lx-btn--sm" onClick={() => setSnapshotCursor(cursorFrom(snapshots.data?.next))}>Trang Snapshot tiếp</button>}{configs.data?.next && <button type="button" className="lx-btn lx-btn--sm" onClick={() => setConfigCursor(cursorFrom(configs.data?.next))}>Trang phiên bản tiếp</button>}</div>}
          <dl className="lx-kv">
            <dt>Snapshot</dt><dd className="lx-mono">{selectedSnapshot ? `${snapshotCode(selectedSnapshot.id)} · ${shortRevision(selectedSnapshot.revision_hash)}` : '—'}</dd>
            <dt>Phạm vi</dt><dd>{selectedSnapshot ? `${taskCount} task · ${selectedSnapshot.jobs?.length ?? 0} job · ${formatCount(frameCount)} frame` : '—'}</dd>
            <dt>Engine</dt><dd>{activeConfig ? `${enabledEngineCount} bật · ${ENGINES.length - enabledEngineCount} tắt` : '—'}</dd>
            <dt>Thời gian dự kiến</dt><dd>—</dd>
          </dl>
          <div className="lx-field"><label className="lx-label" htmlFor="analysis-seed">Seed</label><input className="lx-input" id="analysis-seed" type="number" value={seed} onChange={(e) => { setSeed(Number(e.target.value)); setPending(null); }} /></div>
          {activeConfig && enabledEngineCount < ENGINES.length && <div className="lx-callout lx-callout--warning"><span className="lx-callout__text">{ENGINES.length - enabledEngineCount} engine đang tắt, nên kết quả sẽ ghi là Not checked.</span></div>}
          <ol className="lx-muted lx-text-13"><li>Chạy các engine song song</li><li>Gộp Issue trùng và tính mức ưu tiên</li><li>Đưa vào các hàng đợi tại Review Center</li></ol>
          {!canCreate && <p className="lx-muted">Vai trò hiện tại chỉ được xem cấu hình và lịch sử; Quality Assurance Lead hoặc Super Admin mới được chạy phân tích.</p>}
          {submitError && <p role="alert" className="lx-callout">{submitError}</p>}
          <button type="submit" className="lx-btn lx-btn--primary lx-btn--block" disabled={!canCreate || !selectedSnapshot || !selectedConfig || submitting}>{submitting ? 'Đang chạy…' : 'Chạy phân tích'}</button>
        </div>
      </aside>
    </form>
    {canConfigure && <section className="lx-card" aria-label="Tạo phiên bản cấu hình">
      <header className="lx-card__head"><h2 className="lx-h2">Tạo phiên bản cấu hình</h2><span className="lx-hint">Phiên bản đã phát hành không chỉnh sửa trực tiếp</span></header>
      <form onSubmit={saveConfig} className="lx-card__body lx-stack">
        <p className="lx-muted lx-text-13">Phiên bản mới được phát hành để Quality Assurance Lead chọn khi chạy phân tích.</p>
        <div className="lx-field"><label className="lx-label" htmlFor="config-name">Tên cấu hình</label><input className="lx-input" id="config-name" value={configName} maxLength={128} onChange={(e) => { setConfigName(e.target.value); setConfigPending(null); }} required /></div>
        <fieldset className="lx-field lx-fieldset">
          <legend className="lx-label">Engine cần chạy</legend>
          <div className="lx-card lx-card--inner"><table className="lx-table"><tbody>{ENGINES_META.map((meta) => <tr key={meta.key}>
            <td className="lx-th--check"><label className="lx-switch"><input type="checkbox" aria-label={meta.name} checked={enabledEngines.includes(meta.key)} onChange={(e) => { setEnabledEngines((current) => e.target.checked ? [...current, meta.key] : current.filter((item) => item !== meta.key)); setConfigPending(null); }} /><span /></label></td>
            <td><div className="lx-cell__main">{meta.name}</div><div className="lx-cell__sub">{meta.sub}</div></td>
          </tr>)}</tbody></table></div>
        </fieldset>
        <div className="lx-field"><label className="lx-label" htmlFor="config-thresholds">Ngưỡng kiểm tra (JSON)</label><textarea className="lx-textarea" id="config-thresholds" rows={3} value={thresholdsText} onChange={(e) => { setThresholdsText(e.target.value); setConfigPending(null); }} /></div>
        <div className="lx-field"><label className="lx-label" htmlFor="config-models">Mô hình tham chiếu (JSON)</label><textarea className="lx-textarea" id="config-models" rows={3} value={modelsText} onChange={(e) => { setModelsText(e.target.value); setConfigPending(null); }} /></div>
        {configError && <p role="alert" className="lx-callout">{configError}</p>}
        {draftId && <div className="lx-callout lx-callout--warning">Phiên bản v{draftId} đã được tạo nhưng chưa xác nhận phát hành. <button type="button" className="lx-btn" disabled={configBusy} onClick={retryPublish}>Thử phát hành lại</button></div>}
        {enabledEngines.length === 0 && <p role="alert" className="lx-callout lx-callout--warning">Cần bật ít nhất một engine.</p>}
        <div className="lx-actions lx-actions--end"><button type="submit" className="lx-btn lx-btn--primary" disabled={configBusy || !configName.trim() || enabledEngines.length === 0}>{configBusy ? 'Đang lưu…' : 'Tạo và phát hành'}</button></div>
      </form>
    </section>}
  </AppShell>;
}

export default function AnalysisConfigPage() {
  return <AuthGuard permissionCheck={canAccessAnalysis} requiredPermissionName="Quyền Phân tích Chất lượng"><ConfigContent /></AuthGuard>;
}
