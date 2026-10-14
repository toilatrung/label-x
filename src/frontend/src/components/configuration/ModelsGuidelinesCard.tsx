'use client';

import React, { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessConfiguration } from '@/lib/auth/roles';
import { ConfigTabs, EditIconButton } from './ConfigTabs';
import { VlmSettingsModal } from './VlmSettingsModal';
import { getVlmSettings, type VlmSettings } from '@/lib/configuration/vlm-api';
import { errorMessage } from '@/lib/api/errors';
import { GpuWorkerPanel } from './GpuWorkerPanel';

type TabKey = 'models' | 'guideline' | 'worker';

const TABS = [
  { key: 'models' as const, label: 'Mô hình' },
  { key: 'guideline' as const, label: 'Phiên bản guideline' },
];

// Dữ liệu minh họa lấy từ docs/design/screens/ModelsGuidelines.dc.html.
const MODELS = [
  { name: 'Detector', role: 'Phát hiện object độc lập', version: 'v2.3', mapping: 'Taxonomy v3 · 12 lớp', confidence: '0.60', status: 'Đang dùng', badge: 'lx-badge lx-badge--success' },
  { name: 'Classifier', role: 'Kiểm tra lại nhãn của object', version: 'v1.8', mapping: 'Taxonomy v3 · 12 lớp', confidence: '0.70', status: 'Đang dùng', badge: 'lx-badge lx-badge--success' },
  { name: 'Mô hình thị giác – ngôn ngữ', role: 'Kiểm tra có chọn lọc', version: 'qwen3-vl-plus', mapping: 'Mô tả bằng văn bản', confidence: null, status: 'Theo cấu hình QC', badge: 'lx-badge', kind: 'vlm' },
];

const GUIDELINES = [
  { name: 'Guideline v1.2', taxonomy: 'v3', datasets: 'Road Vision Urban v1.3 – v1.4', effective: '2026-08-20', status: 'Đang dùng', badge: 'lx-badge lx-badge--success' },
  { name: 'Guideline v1.3', taxonomy: 'v3', datasets: 'Chưa áp dụng', effective: 'Chờ phê duyệt', status: 'Chờ phê duyệt', badge: 'lx-badge lx-badge--warning' },
  { name: 'Guideline v1.1', taxonomy: 'v2', datasets: 'Road Vision Urban v1.1 – v1.2', effective: '2026-06-01', status: 'Đã thay thế', badge: 'lx-badge' },
];

/**
 * ModelsGuidelines: hai tab cũ giữ nguyên; tab GPU Worker dùng API thật cho admin toàn hệ thống.
 * TODO(backend): GET /api/models/ (bảng Mô hình), PATCH /api/models/{id}/ (chỉnh mô hình),
 * GET /api/guidelines/versions/ (hiệu lực guideline, taxonomy và Dataset áp dụng).
 */
export function ModelsGuidelinesCard({ guidelineExtra }: {
  /** Nội dung dữ liệu thật (API) chỉ hiện ở tab Phiên bản guideline, ngoài thẻ hai tab của thiết kế. */
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
  return (
    <>
    <section className="lx-card" aria-label="Mô hình và phiên bản guideline">
      <ConfigTabs tabs={canManageWorker ? [...TABS, { key: 'worker' as const, label: 'GPU Worker' }] : TABS} current={tab} onPick={setTab} label="Mô hình và phiên bản guideline" />
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
                    <td className="lx-mono">{model.version}</td>
                    <td className="lx-muted">{model.mapping}</td>
                    <td className={model.confidence || (model.kind === 'vlm' && vlmSettings) ? 'r' : 'r lx-subtle'} title={model.kind === 'vlm' ? 'Ngưỡng điểm detector để gọi VLM' : undefined}>{model.kind === 'vlm' ? vlmSettings?.confidence_threshold?.toFixed(2) ?? '—' : model.confidence ?? '—'}</td>
                    <td><span className={model.badge}>{model.kind === 'vlm' && vlmSettings ? vlmSettings.api_key_configured ? 'Đã cấu hình' : 'Chưa cấu hình' : model.status}</span></td>
                    <td className="r"><EditIconButton label="Chỉnh mô hình" disabled={model.kind === 'vlm' ? !canConfigureVlm : !canWrite} onBlocked={() => { if (model.kind === 'vlm') setEditingVlm(true); }} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {vlmError && <p role="alert" className="lx-gap__notice">Không tải được cấu hình VLM: {vlmError}</p>}
          <div className="lx-card__foot"><span>Mô hình chưa được xác minh không tự động biến candidate thành lỗi đã xác nhận.</span></div>
        </>
      )}

      {tab === 'guideline' && (
        <div className="lx-scroll">
          <table className="lx-table lx-table--min-680">
            <thead><tr><th>Guideline</th><th>Taxonomy</th><th>Áp dụng cho Dataset</th><th>Hiệu lực từ</th><th>Trạng thái</th></tr></thead>
            <tbody>
              {GUIDELINES.map(guideline => (
                <tr key={guideline.name}>
                  <td className="lx-cell__main">{guideline.name}</td>
                  <td className="lx-muted">{guideline.taxonomy}</td>
                  <td className="lx-muted">{guideline.datasets}</td>
                  <td className="lx-muted">{guideline.effective}</td>
                  <td><span className={guideline.badge}>{guideline.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
    {editingVlm && <VlmSettingsModal onClose={() => setEditingVlm(false)} onSaved={acceptVlm} />}
    {tab === 'guideline' && guidelineExtra}
    </>
  );
}
