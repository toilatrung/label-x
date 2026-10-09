'use client';

import React from 'react';
import type { components } from '@/lib/api/contract';

export type ConfigVersion = components['schemas']['ConfigVersion'];

export interface EngineThresholdsTableProps {
  config: ConfigVersion | null;
  isLoading?: boolean;
  error?: string | null;
  hasPermission?: boolean;
}

interface EngineMeta {
  key: string;
  name: string;
  sub: string;
  formatParams: (params: Record<string, unknown>) => string | null;
}

const ENGINES_META: EngineMeta[] = [
  {
    key: 'schema',
    name: 'Schema / Taxonomy',
    sub: 'Xác định · Chạy nhanh',
    formatParams: (params) => {
      const parts: string[] = [];
      if (typeof params.taxonomy_version === 'string' && params.taxonomy_version.trim()) {
        parts.push(params.taxonomy_version);
      }
      if (typeof params.required_attributes === 'boolean') {
        parts.push(params.required_attributes ? 'Thuộc tính bắt buộc theo lớp' : 'Không bắt buộc thuộc tính');
      } else if (typeof params.required_attributes === 'string' && params.required_attributes.trim()) {
        parts.push(params.required_attributes);
      }
      return parts.length > 0 ? parts.join(' · ') : null;
    },
  },
  {
    key: 'geometry',
    name: 'Geometry',
    sub: 'Xác định · Dung sai và diện tích',
    formatParams: (params) => {
      const parts: string[] = [];
      if (typeof params.tolerance_px === 'number') {
        parts.push(`Dung sai biên ${params.tolerance_px} px`);
      }
      if (typeof params.min_area_px === 'number') {
        parts.push(`Diện tích tối thiểu ${params.min_area_px} px²`);
      }
      return parts.length > 0 ? parts.join(' · ') : null;
    },
  },
  {
    key: 'duplicate',
    name: 'Duplicate / Overlap',
    sub: 'Xác định · Trùng lặp cùng lớp',
    formatParams: (params) => {
      const parts: string[] = [];
      if (typeof params.iou_threshold === 'number') {
        parts.push(`Intersection over Union (IoU) ≥ ${params.iou_threshold}`);
      }
      if (typeof params.same_class === 'boolean') {
        parts.push(params.same_class ? 'Cùng lớp' : 'Khác lớp');
      }
      return parts.length > 0 ? parts.join(' · ') : null;
    },
  },
  {
    key: 'detector',
    name: 'Mô hình độc lập (Detector)',
    sub: 'Chạy nền · Mất vài giờ',
    formatParams: (params) => {
      const parts: string[] = [];
      if (typeof params.model_version === 'string' && params.model_version.trim()) {
        parts.push(params.model_version);
      }
      if (typeof params.confidence_threshold === 'number') {
        parts.push(`Ngưỡng tin cậy ≥ ${params.confidence_threshold}`);
      }
      return parts.length > 0 ? parts.join(' · ') : null;
    },
  },
  {
    key: 'vlm',
    name: 'Mô hình thị giác – ngôn ngữ (VLM)',
    sub: 'Chỉ chạy trên candidate cần hiểu ảnh',
    formatParams: (params) => {
      const parts: string[] = [];
      if (typeof params.model_version === 'string' && params.model_version.trim()) {
        parts.push(params.model_version);
      }
      if (typeof params.max_candidates === 'number') {
        parts.push(`Tối đa ${params.max_candidates} candidate mỗi lần chạy`);
      }
      return parts.length > 0 ? parts.join(' · ') : null;
    },
  },
  {
    key: 'metric',
    name: 'Metric',
    sub: 'Cần Ground Truth',
    formatParams: (params) => {
      const parts: string[] = [];
      if (typeof params.benchmark === 'string' && params.benchmark.trim()) {
        parts.push(`Benchmark: ${params.benchmark}`);
      }
      if (typeof params.ground_truth === 'string' && params.ground_truth.trim()) {
        parts.push(`Ground Truth: ${params.ground_truth}`);
      }
      return parts.length > 0 ? parts.join(' · ') : null;
    },
  },
];

export function EngineThresholdsTable({
  config,
  isLoading = false,
  error = null,
  hasPermission = true,
}: EngineThresholdsTableProps) {
  if (!hasPermission) {
    return (
      <section className="lx-card" aria-label="Cấu hình ngưỡng engine">
        <header className="lx-card__head">
          <span className="lx-cell__main">Ngưỡng kiểm tra engine</span>
          <span className="lx-subtle">Chỉ đọc</span>
        </header>
        <div className="lx-card__body">
          <div className="lx-callout" role="note">
            <strong>Giới hạn quyền truy cập</strong>
            <div>
              Bạn không có quyền xem cấu hình ngưỡng engine. Cần quyền Quality Assurance Lead, Quality Control Admin hoặc Super Admin.
            </div>
          </div>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="lx-card" aria-label="Cấu hình ngưỡng engine">
        <header className="lx-card__head">
          <span className="lx-cell__main">Ngưỡng kiểm tra engine</span>
          <span className="lx-subtle">Chỉ đọc</span>
        </header>
        <div className="lx-card__body">
          <div className="lx-callout" role="alert">
            <strong>Không tải được cấu hình engine</strong>
            <div>{error}</div>
          </div>
        </div>
      </section>
    );
  }

  if (isLoading) {
    return (
      <section className="lx-card" aria-label="Cấu hình ngưỡng engine">
        <header className="lx-card__head">
          <span className="lx-cell__main">Ngưỡng kiểm tra engine</span>
          <span className="lx-subtle">Chỉ đọc</span>
        </header>
        <div className="lx-scroll">
          <table className="lx-table">
            <tbody>
              <tr>
                <td className="c lx-subtle" colSpan={4}>
                  Đang tải cấu hình ngưỡng engine…
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    );
  }

  if (!config) {
    return (
      <section className="lx-card" aria-label="Cấu hình ngưỡng engine">
        <header className="lx-card__head">
          <span className="lx-cell__main">Ngưỡng kiểm tra engine</span>
          <span className="lx-subtle">Chỉ đọc</span>
        </header>
        <div className="lx-card__body">
          <div className="lx-callout" role="status">
            <strong>Chưa có cấu hình đã phát hành</strong>
            <div>
              API chưa trả về phiên bản cấu hình engine đã phát hành. Không thể xác nhận ngưỡng từ dữ liệu hiện có; riêng việc thiếu cấu hình published không xác định trạng thái engine đang chạy.
            </div>
          </div>
        </div>
      </section>
    );
  }

  const rawEngines = (config.engines || {}) as Record<string, unknown>;

  return (
    <section className="lx-card" aria-label="Cấu hình ngưỡng engine">
      <header className="lx-card__head">
        <div>
          <span className="lx-cell__main">Ngưỡng kiểm tra engine</span>
          <span className="lx-hint" style={{ marginLeft: 8 }}>
            Phiên bản phát hành: <strong className="lx-mono">{config.name}</strong> (#{config.id})
          </span>
        </div>
        <span className="lx-subtle">Chỉ đọc · Giá trị trong cấu hình published</span>
      </header>
      <div className="lx-card__body">
        <div className="lx-callout" role="note">
          <strong>Trạng thái trong cấu hình</strong>
          <div>
            Bảng này hiển thị bản cấu hình đã phát hành do API trả về. Mỗi QC run dùng một config version riêng; trạng thái của một run cần xem theo phiên bản gắn với run đó.
          </div>
        </div>
      </div>
      <div className="lx-scroll">
        <table className="lx-table">
          <thead>
            <tr>
              <th style={{ width: '150px' }}>Trạng thái cấu hình</th>
              <th>Engine</th>
              <th style={{ width: '120px' }}>Phiên bản</th>
              <th>Tham số ngưỡng trong config</th>
            </tr>
          </thead>
          <tbody>
            {ENGINES_META.map((meta) => {
              const engineConf =
                typeof rawEngines[meta.key] === 'object' && rawEngines[meta.key] !== null
                  ? (rawEngines[meta.key] as Record<string, unknown>)
                  : undefined;

              const isEnabled =
                engineConf && typeof engineConf.enabled === 'boolean'
                  ? engineConf.enabled
                  : null;

              const version =
                engineConf && typeof engineConf.version === 'string' && engineConf.version.trim()
                  ? engineConf.version
                  : '—';

              const params =
                engineConf && typeof engineConf.params === 'object' && engineConf.params !== null
                  ? (engineConf.params as Record<string, unknown>)
                  : {};

              const effectiveThreshold = meta.formatParams(params);

              return (
                <tr key={meta.key}>
                  <td>
                    {isEnabled === true ? (
                      <span className="lx-badge lx-badge--success">Bật trong config</span>
                    ) : isEnabled === false ? (
                      <span className="lx-badge">Tắt trong config</span>
                    ) : (
                      <span className="lx-badge">Chưa khai báo</span>
                    )}
                  </td>
                  <td>
                    <div className="lx-cell__main">{meta.name}</div>
                    <div className="lx-cell__sub">{meta.sub}</div>
                  </td>
                  <td>
                    <span className="lx-mono">{version}</span>
                  </td>
                  <td>
                    {effectiveThreshold ? (
                      <>
                        <div className="lx-cell__main">{effectiveThreshold}</div>
                        {Object.keys(params).length > 0 && (
                          <div className="lx-cell__sub lx-mono">
                            {JSON.stringify(params)}
                          </div>
                        )}
                      </>
                    ) : (
                      <span className="lx-subtle">Chưa được cấu hình/không có dữ liệu từ API</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <footer className="lx-card__foot">
        <span>
          Cấu hình phát hành lúc:{' '}
          {config.published_at
            ? new Date(config.published_at).toLocaleString('vi-VN')
            : config.created_at
            ? new Date(config.created_at).toLocaleString('vi-VN')
            : '—'}
          . Các giá trị <span className="lx-mono">params</span> và cờ bật/tắt ở đây thuộc phiên bản cấu hình được hiển thị, không đại diện cho mọi QC run.
        </span>
      </footer>
    </section>
  );
}
