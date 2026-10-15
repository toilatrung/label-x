'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { FlowNav } from '@/components/layout/FlowNav';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, hasDatasetPermission } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import { ApiRequestError } from '@/lib/api/client';
import { DatasetPicker } from '@/lib/execution/DatasetPicker';
import { createRun, cursorFrom, listConfigs, listSnapshots, type ConfigVersion, type RunCreate } from '@/lib/execution/api';
import { EngineThresholdsTable } from '@/components/execution/EngineThresholdsTable';
import { GroundTruthUpload } from '@/components/execution/GroundTruthUpload';
import { currentGroundTruth } from '@/lib/execution/api';
import { formatCount, shortRevision, snapshotCode } from '@/lib/format';

const ENGINES = ['schema', 'geometry', 'duplicate', 'detector', 'metric', 'vlm'] as const;

function ConfigContent() {
  const { session, datasetId } = useAuth();
  const router = useRouter();
  const canCreate = hasDatasetPermission(session, datasetId, (role) => role === 'qa_lead' || role === 'super_admin');
  const [snapshotCursor, setSnapshotCursor] = useState<string | null>(null);
  const [configCursor, setConfigCursor] = useState<string | null>(null);
  const [snapshotId, setSnapshotId] = useState<number | null>(null);
  const [configId, setConfigId] = useState<number | null>(null);
  const [selectedConfigRecord, setSelectedConfigRecord] = useState<ConfigVersion | null>(null);
  const [seed, setSeed] = useState(42);
  const [pending, setPending] = useState<{ body: RunCreate; key: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const snapshots = useQuery({ queryKey: ['analysis-snapshots', session?.user.id, datasetId, snapshotCursor], queryFn: ({ signal }) => listSnapshots(datasetId!, snapshotCursor, signal), enabled: datasetId !== null, retry: false });
  const configs = useQuery({ queryKey: ['analysis-configs', session?.user.id, configCursor], queryFn: ({ signal }) => listConfigs(configCursor, signal), enabled: !!session, retry: false });
  const groundTruth = useQuery({ queryKey: ['ground-truth', session?.user.id, datasetId], queryFn: ({ signal }) => currentGroundTruth(datasetId!, signal), enabled: canCreate && datasetId !== null, retry: false, refetchInterval: 5000 });
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
  const metricConfig = rawEngines.metric as { enabled?: boolean } | undefined;
  const metricEnabled = metricConfig?.enabled === true;
  const detectorEnabled = (rawEngines.detector as { enabled?: boolean } | undefined)?.enabled === true;
  const detectorModelReady = !detectorEnabled || (typeof activeConfig?.models?.name === 'string' &&
    !!activeConfig.models.name && typeof activeConfig.models.version === 'string' && !!activeConfig.models.version);
  const gt = groundTruth.data;
  const groundTruthReady = !metricEnabled || (!groundTruth.isPending && !groundTruth.isError && (!gt || (!gt.deleted_at && gt.reference.status === 'locked' && gt.reference.snapshot_id === snapshotId)));
  const taskCount = selectedSnapshot?.jobs ? new Set(selectedSnapshot.jobs.map((job) => job.cvat_task_id)).size : 0;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!canCreate || !snapshotId || !configId || submitting) return;
    if (!groundTruthReady) return;
    if (!detectorModelReady) return;
    const body = { snapshot_id: snapshotId, config_version_id: configId, seed,
      ...(metricEnabled && gt ? { metric_reference_id: gt.reference.id } : {}) };
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

  return <AppShell activeKey="analysis" flowStep={2} showFlowNav={false} pageHeader={<div className="lx-head"><div className="lx-head__text"><h1 className="lx-h1">Analysis Configuration</h1><p className="lx-lead">Chọn phiên bản cấu hình đã phát hành để chạy cho Snapshot. Chỉnh Detector và tạo phiên bản tại Models &amp; Guidelines.</p></div><Link className="lx-btn" href="/configuration/guidelines">Models &amp; Guidelines</Link></div>}>
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
          {configs.data?.results.length === 0 && <div className="lx-callout lx-callout--neutral" role="status">Chưa có phiên bản cấu hình đã phát hành. Quality Control Admin hoặc Super Admin cần chỉnh Detector tại Models &amp; Guidelines để tạo phiên bản trước khi chạy phân tích.</div>}
          {(snapshots.data?.next || configs.data?.next) && <div className="lx-actions">{snapshots.data?.next && <button type="button" className="lx-btn lx-btn--sm" onClick={() => setSnapshotCursor(cursorFrom(snapshots.data?.next))}>Trang Snapshot tiếp</button>}{configs.data?.next && <button type="button" className="lx-btn lx-btn--sm" onClick={() => setConfigCursor(cursorFrom(configs.data?.next))}>Trang phiên bản tiếp</button>}</div>}
          <dl className="lx-kv">
            <dt>Snapshot</dt><dd className="lx-mono">{selectedSnapshot ? `${snapshotCode(selectedSnapshot.id)} · ${shortRevision(selectedSnapshot.revision_hash)}` : '—'}</dd>
            <dt>Phạm vi</dt><dd>{selectedSnapshot ? `${taskCount} task · ${selectedSnapshot.jobs?.length ?? 0} job · ${formatCount(frameCount)} frame` : '—'}</dd>
            <dt>Engine</dt><dd>{activeConfig ? `${enabledEngineCount} bật · ${ENGINES.length - enabledEngineCount} tắt` : '—'}</dd>
            <dt>Thời gian dự kiến</dt><dd>—</dd>
          </dl>
          <div className="lx-field"><label className="lx-label" htmlFor="analysis-seed">Seed</label><input className="lx-input" id="analysis-seed" type="number" value={seed} onChange={(e) => { setSeed(Number(e.target.value)); setPending(null); }} /></div>
          {canCreate && <GroundTruthUpload key={`${datasetId}-${snapshotId}`} datasetId={datasetId} snapshotId={snapshotId}
            userId={session!.user.id} enabled={canCreate} busy={submitting} />}
          {activeConfig && enabledEngineCount < ENGINES.length && <div className="lx-callout lx-callout--warning"><span className="lx-callout__text">{ENGINES.length - enabledEngineCount} engine đang tắt, nên kết quả sẽ ghi là Not checked.</span></div>}
          {!detectorModelReady && <div className="lx-callout lx-callout--warning" role="alert">Phiên bản này bật Detector nhưng chưa chọn model. Chỉnh Detector tại <Link href="/configuration/guidelines">Models &amp; Guidelines</Link>, rồi chọn phiên bản mới để chạy.</div>}
          <ol className="lx-muted lx-text-13"><li>Chạy các engine song song</li><li>Gộp Issue trùng và tính mức ưu tiên</li><li>Đưa vào các hàng đợi tại Review Center</li></ol>
          {!canCreate && <p className="lx-muted">Vai trò hiện tại chỉ được xem cấu hình và lịch sử; Quality Assurance Lead hoặc Super Admin mới được chạy phân tích.</p>}
          {submitError && <p role="alert" className="lx-callout">{submitError}</p>}
          <button type="submit" className="lx-btn lx-btn--primary lx-btn--block" disabled={!canCreate || !selectedSnapshot || !selectedConfig || !groundTruthReady || !detectorModelReady || submitting}>{submitting ? 'Đang chạy…' : 'Chạy phân tích'}</button>
        </div>
      </aside>
    </form>
  </AppShell>;
}

export default function AnalysisConfigPage() {
  return <AuthGuard permissionCheck={canAccessAnalysis} requiredPermissionName="Quyền Phân tích Chất lượng"><ConfigContent /></AuthGuard>;
}
