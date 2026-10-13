'use client';

import React, { useState } from 'react';
import { ConfigTabs, EditIconButton } from './ConfigTabs';

type TabKey = 'rules' | 'gate' | 'sampling';

const TABS = [
  { key: 'rules' as const, label: 'Quy tắc kiểm tra' },
  { key: 'gate' as const, label: 'Ngưỡng phát hành' },
  { key: 'sampling' as const, label: 'Chính sách lấy mẫu' },
];

type Severity = { label: string; badge: string };
const CRITICAL: Severity = { label: 'Nghiêm trọng', badge: 'lx-badge lx-badge--danger' };
const MEDIUM: Severity = { label: 'Trung bình', badge: 'lx-badge lx-badge--warning' };
const LIGHT: Severity = { label: 'Nhẹ', badge: 'lx-badge' };

// Dữ liệu minh họa lấy từ docs/design/screens/RulesThresholds.dc.html.
const RULES = [
  { id: 'S-001', name: 'Thiếu thuộc tính bắt buộc', group: 'Schema', threshold: '—', severity: CRITICAL, on: true },
  { id: 'G-009', name: 'Biên polygon lệch so với vật thể', group: 'Geometry', threshold: 'Dung sai 2 px', severity: MEDIUM, on: true },
  { id: 'G-014', name: 'Bounding box quá nhỏ hoặc nằm ngoài khung', group: 'Geometry', threshold: 'Tối thiểu 24 px²', severity: MEDIUM, on: true },
  { id: 'D-002', name: 'Hai annotation chồng lấn cùng lớp', group: 'Duplicate', threshold: 'Intersection over Union ≥ 0.85', severity: MEDIUM, on: true },
  { id: 'A-003', name: 'Thuộc tính occluded thiếu nhất quán', group: 'Attribute', threshold: '—', severity: LIGHT, on: false },
];

const GATE = [
  { id: 't1', label: 'Coverage tối thiểu để phát hành', value: '95%' },
  { id: 't2', label: 'Lỗi nghiêm trọng chưa đóng tối đa', value: '0' },
  { id: 't3', label: 'Tỷ lệ lỗi còn sót tối đa', value: '5%' },
  { id: 't4', label: 'Mức thống nhất reviewer tối thiểu', value: '90%' },
  { id: 't5', label: 'Rework bắt buộc đã xác minh', value: '100%' },
];

/**
 * Thẻ ba tab của RulesThresholds theo thiết kế. Toàn bộ dữ liệu là minh họa; chưa có API.
 * TODO(backend): GET /api/config-versions/{id}/rules/ (bảng quy tắc), GET/PATCH ngưỡng phát hành và chính sách lấy mẫu,
 * POST /api/config-versions/ (lưu thành phiên bản mới).
 */
export function RulesPolicyCard({ blockedAction: _blockedAction, onBlocked, canWrite, rulesExtra }: {
  blockedAction: string | null; onBlocked: (action: string) => void; canWrite: boolean;
  /** Nội dung dữ liệu thật (API) chỉ hiện ở tab Quy tắc kiểm tra, ngoài thẻ ba tab của thiết kế. */
  rulesExtra?: React.ReactNode;
}) {
  void _blockedAction;
  const [tab, setTab] = useState<TabKey>('rules');
  return (
    <>
    <section className="lx-card" aria-label="Cấu hình quy tắc và ngưỡng">
      <ConfigTabs tabs={TABS} current={tab} onPick={setTab} label="Cấu hình quy tắc và ngưỡng" />
      {tab === 'rules' && (
        <div className="lx-scroll">
          <table className="lx-table lx-table--min-760">
            <thead><tr>
              <th className="lx-th--toggle">Bật</th><th>Mã</th><th>Quy tắc</th><th>Nhóm</th><th>Ngưỡng</th><th>Mức độ</th><th></th>
            </tr></thead>
            <tbody>
              {RULES.map(rule => (
                <tr key={rule.id}>
                  <td><label className="lx-switch"><input type="checkbox" checked={rule.on} disabled readOnly aria-label={rule.id} /><span></span></label></td>
                  <td className="lx-mono">{rule.id}</td>
                  <td className="lx-cell__main">{rule.name}</td>
                  <td className="lx-muted">{rule.group}</td>
                  <td className="lx-muted">{rule.threshold}</td>
                  <td><span className={rule.severity.badge}>{rule.severity.label}</span></td>
                  <td className="r"><EditIconButton label="Chỉnh quy tắc" disabled={!canWrite} onBlocked={() => onBlocked('Chỉnh quy tắc')} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'gate' && (
        <div className="lx-card__body lx-grid lx-grid--3">
          {GATE.map(field => (
            <div className="lx-field" key={field.id}>
              <label className="lx-label" htmlFor={field.id}>{field.label}</label>
              <input id={field.id} className="lx-input" value={field.value} readOnly />
            </div>
          ))}
        </div>
      )}

      {tab === 'sampling' && (
        <div className="lx-card__body lx-grid lx-grid--3">
          <div className="lx-field">
            <label className="lx-label" htmlFor="s1">Kiểm tra ngẫu nhiên · tỷ lệ frame</label>
            <input id="s1" className="lx-input" value="0.8%" readOnly />
            <span className="lx-hint">Tối thiểu 100 frame mỗi lần chạy</span>
          </div>
          <div className="lx-field">
            <label className="lx-label" htmlFor="s2">Lấy mẫu theo rủi ro · tỷ lệ frame</label>
            <input id="s2" className="lx-input" value="0.8%" readOnly />
          </div>
          <div className="lx-field">
            <label className="lx-label" htmlFor="s3">Cách chọn seed</label>
            <select id="s3" className="lx-select" disabled><option>Tự sinh và lưu vào manifest</option><option>Nhập thủ công</option></select>
          </div>
        </div>
      )}
    </section>
    {tab === 'rules' && rulesExtra}
    </>
  );
}
