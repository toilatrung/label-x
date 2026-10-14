'use client';

import React, { useState } from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessConfiguration } from '@/lib/auth/roles';
import { ConfigTabs, EditIconButton } from './ConfigTabs';

type TabKey = 'models' | 'guideline';

const TABS = [
  { key: 'models' as const, label: 'Mô hình' },
  { key: 'guideline' as const, label: 'Phiên bản guideline' },
];

// Dữ liệu minh họa lấy từ docs/design/screens/ModelsGuidelines.dc.html.
const MODELS = [
  { name: 'Detector', role: 'Phát hiện object độc lập', version: 'v2.3', mapping: 'Taxonomy v3 · 12 lớp', confidence: '0.60', status: 'Đang dùng', badge: 'lx-badge lx-badge--success' },
  { name: 'Classifier', role: 'Kiểm tra lại nhãn của object', version: 'v1.8', mapping: 'Taxonomy v3 · 12 lớp', confidence: '0.70', status: 'Đang dùng', badge: 'lx-badge lx-badge--success' },
  { name: 'Mô hình thị giác – ngôn ngữ', role: 'Kiểm tra có chọn lọc', version: 'v0.9', mapping: 'Mô tả bằng văn bản', confidence: null, status: 'Thử nghiệm', badge: 'lx-badge lx-badge--warning' },
];

/**
 * Hai tab cấu hình: bảng Detector/Classifier còn minh họa; Guideline dùng API thật.
 * TODO(backend): GET /api/models/ (bảng Mô hình), PATCH /api/models/{id}/ (chỉnh mô hình),
 */
export function ModelsGuidelinesCard({ guidelineExtra }: {
  /** Thư viện Guideline và tra cứu rule ở tab Phiên bản guideline. */
  guidelineExtra?: React.ReactNode;
} = {}) {
  const { hasPermission } = useAuth();
  const canWrite = hasPermission(canAccessConfiguration);
  const [tab, setTab] = useState<TabKey>('models');
  return (
    <>
    <section className="lx-card" aria-label="Mô hình và phiên bản guideline">
      <ConfigTabs tabs={TABS} current={tab} onPick={setTab} label="Mô hình và phiên bản guideline" />
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
                    <td className={model.confidence ? 'r' : 'r lx-subtle'}>{model.confidence ?? '—'}</td>
                    <td><span className={model.badge}>{model.status}</span></td>
                    <td className="r"><EditIconButton label="Chỉnh mô hình" disabled={!canWrite} onBlocked={() => undefined} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="lx-card__foot"><span>Mô hình chưa được xác minh không tự động biến candidate thành lỗi đã xác nhận.</span></div>
        </>
      )}

    </section>
    {tab === 'guideline' && guidelineExtra}
    </>
  );
}
