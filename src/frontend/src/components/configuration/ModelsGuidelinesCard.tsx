'use client';

import React, { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessConfiguration } from '@/lib/auth/roles';
import { ConfigTabs, EditIconButton } from './ConfigTabs';
import { VlmSettingsModal } from './VlmSettingsModal';
import { getVlmSettings, type VlmSettings } from '@/lib/configuration/vlm-api';
import { errorMessage } from '@/lib/api/errors';
import { GpuWorkerPanel } from './GpuWorkerPanel';
import { DetectorSettingsModal } from './DetectorSettingsModal';
import { listDetectorArtifacts, type RegisteredDetector } from '@/lib/execution/api';

type TabKey = 'models' | 'guideline' | 'worker';

const TABS = [
  { key: 'models' as const, label: 'Mô hình' },
  { key: 'guideline' as const, label: 'Phiên bản guideline' },
];

// Dữ liệu minh họa lấy từ docs/design/screens/ModelsGuidelines.dc.html.
const MODELS = [
  { name: 'Detector', role: 'Phát hiện object độc lập', version: null, mapping: null, confidence: null, status: 'Chưa cấu hình', badge: 'lx-badge', kind: 'detector' },
  { name: 'Classifier', role: 'Kiểm tra lại nhãn của object', version: 'v1.8', mapping: 'Taxonomy v3 · 12 lớp', confidence: '0.70', status: 'Đang dùng', badge: 'lx-badge lx-badge--success' },
  { name: 'Mô hình thị giác – ngôn ngữ', role: 'Kiểm tra có chọn lọc', version: null, mapping: 'Mô tả bằng văn bản', confidence: null, status: 'Theo cấu hình QC', badge: 'lx-badge', kind: 'vlm' },
];

/**
 * ModelsGuidelines: hai tab cũ (Mô hình, Guideline); tab GPU Worker dùng API thật cho admin toàn hệ thống.
 * TODO(backend): GET /api/models/ (bảng Mô hình), PATCH /api/models/{id}/ (chỉnh mô hình),
 */
export function ModelsGuidelinesCard({ guidelineExtra }: {
  /** Thư viện Guideline và tra cứu rule ở tab Phiên bản guideline. */
  guidelineExtra?: React.ReactNode;
} = {}) {
  const { hasPermission, session } = useAuth();
  const canManageWorker = session?.roles.some(grant => grant.dataset_id === null &&
    (grant.role === 'super_admin' || grant.role === 'qc_admin')) ?? false;
  const canWrite = hasPermission(canAccessConfiguration);
  const canConfigureVlm = hasPermission(role => ['qc_admin', 'super_admin'].includes(role));
  const canReadVlm = hasPermission(role => ['qa_lead', 'qc_admin', 'super_admin'].includes(role));
  const [tab, setTab] = useState<TabKey>('models');
  const [editingVlm, setEditingVlm] = useState(false);
  const [editingDetector, setEditingDetector] = useState(false);
  const [detectorModel, setDetectorModel] = useState<RegisteredDetector | undefined>();
  const [detectorArtifacts, setDetectorArtifacts] = useState<RegisteredDetector[]>([]);
  const [detectorError, setDetectorError] = useState<string | null>(null);
  const [detectorLoading, setDetectorLoading] = useState(true);
  const [vlmSettings, setVlmSettings] = useState<VlmSettings | null>(null);
  const [vlmError, setVlmError] = useState<string | null>(null);

  function acceptVlm(value: VlmSettings) {
    setVlmSettings(current => current && current.revision > value.revision ? current : value);
    setVlmError(null);
  }

  useEffect(() => {
    if (tab !== 'models' || !canReadVlm) return;
    const controller = new AbortController();
    getVlmSettings(controller.signal).then(value => {
      if (!controller.signal.aborted) acceptVlm(value);
    }).catch(error => { if (!controller.signal.aborted) setVlmError(errorMessage(error)); });
    return () => controller.abort();
  }, [canReadVlm, tab]);

  useEffect(() => {
    if (tab !== 'models' || !canReadVlm) return;
    const controller = new AbortController();
    listDetectorArtifacts(controller.signal).then(artifacts => {
      if (controller.signal.aborted) return;
      setDetectorArtifacts(artifacts); setDetectorError(null);
    }).catch(error => { if (!controller.signal.aborted) setDetectorError(errorMessage(error)); })
      .finally(() => { if (!controller.signal.aborted) setDetectorLoading(false); });
    return () => controller.abort();
  }, [canReadVlm, tab]);

  const selectedDetector = detectorModel ?? detectorArtifacts[0];
  return (
    <>
    <section className="lx-card" aria-label="Mô hình và phiên bản guideline">
      <ConfigTabs tabs={canManageWorker ? [...TABS, { key: 'worker' as const, label: 'GPU Worker' }] : TABS} current={tab} onPick={next => { if (next === 'models' && next !== tab) setDetectorLoading(true); setTab(next); }} label="Mô hình và phiên bản guideline" />
      {tab === 'worker' && canManageWorker && <GpuWorkerPanel />}
      {tab === 'models' && (
        <>
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-760">
              <thead><tr>
                <th>Mô hình</th><th>Vai trò</th><th>Phiên bản</th><th>Ánh xạ lớp</th><th className="r">Ngưỡng tin cậy</th><th>Trạng thái</th><th></th>
              </tr></thead>
              <tbody>
                {MODELS.map(model => (
                  <tr key={model.name}>
                    <td className="lx-cell__main">{model.name}</td>
                    <td className="lx-muted">{model.role}</td>
                    <td className="lx-mono">{model.kind === 'detector' ? selectedDetector?.version ?? '—' : model.kind === 'vlm' ? vlmSettings?.model ?? '—' : model.version}</td>
                    <td className="lx-muted">{model.kind === 'detector' ? selectedDetector?.class_mapping_version ?? '—' : model.mapping}</td>
                    <td className="r" title={model.kind === 'vlm' ? 'Ngưỡng điểm detector để gọi VLM' : undefined}>{model.kind === 'detector' ? 'Theo cấu hình Analysis' : model.kind === 'vlm' ? vlmSettings?.confidence_threshold?.toFixed(2) ?? '—' : model.confidence ?? '—'}</td>
                    <td><span className={model.badge}>{model.kind === 'detector' ? detectorLoading ? 'Đang tải…' : detectorError ? 'Không tải được' : selectedDetector ? 'Đã đăng ký' : 'Chưa đăng ký' : model.kind === 'vlm' && vlmSettings ? vlmSettings.api_key_configured ? 'Đã cấu hình' : 'Chưa cấu hình' : model.status}</span></td>
                    <td className="r"><EditIconButton label={model.kind === 'detector' ? 'Chỉnh Detector' : 'Chỉnh mô hình'} disabled={model.kind === 'detector' ? !canConfigureVlm || detectorLoading || !!detectorError : model.kind === 'vlm' ? !canConfigureVlm : !canWrite} onBlocked={() => { if (model.kind === 'vlm') setEditingVlm(true); if (model.kind === 'detector') setEditingDetector(true); }} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {vlmError && <p role="alert" className="lx-gap__notice">Không tải được cấu hình VLM: {vlmError}</p>}
          {detectorError && <p role="alert" className="lx-gap__notice">Không tải được cấu hình Detector: {detectorError}</p>}
          <div className="lx-card__foot"><span>Mô hình chưa được xác minh không tự động biến candidate thành lỗi đã xác nhận.</span></div>
        </>
      )}

    </section>
    {editingVlm && <VlmSettingsModal onClose={() => setEditingVlm(false)} onSaved={acceptVlm} />}
    {editingDetector && <DetectorSettingsModal initialModel={selectedDetector} canRegister={canManageWorker} onClose={() => setEditingDetector(false)} onSelected={model => {
      setDetectorModel(model);
      setDetectorArtifacts(current => current.some(value => value.id === model.id) ? current : [...current, model]);
    }} />}
    {tab === 'guideline' && guidelineExtra}
    </>
  );
}
