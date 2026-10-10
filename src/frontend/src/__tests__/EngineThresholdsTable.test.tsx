import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EngineThresholdsTable } from '@/components/execution/EngineThresholdsTable';
import type { ConfigVersion } from '@/components/execution/EngineThresholdsTable';

describe('EngineThresholdsTable component (T-029)', () => {
  const publishedConfig: ConfigVersion = {
    id: 42,
    name: 'pilot-config-v2',
    status: 'published',
    engines: {
      schema: { enabled: true, version: '1.2.0', params: { taxonomy_version: 'Taxonomy v4', required_attributes: true } },
      geometry: { enabled: true, version: '1.0.0', params: { tolerance_px: 3, min_area_px: 30 } },
      duplicate: { enabled: true, version: '1.0.0', params: { iou_threshold: 0.90 } },
      detector: { enabled: true, version: '2.4.0', params: { model_version: 'Detector v2.4', confidence_threshold: 0.75 } },
      vlm: { enabled: false, version: '1.0.0', params: { max_candidates: 200 } },
      metric: { enabled: false, version: '1.0.0', params: {} },
    },
    thresholds: { iou: 0.90 },
    models: {},
    created_by: 1,
    created_at: '2026-10-09T08:00:00Z',
    published_at: '2026-10-09T09:00:00Z',
  };

  it('renders all standard engines with published config params and separates configured flags from runtime', () => {
    render(<EngineThresholdsTable config={publishedConfig} />);

    expect(screen.getByText('pilot-config-v2')).toBeDefined();
    expect(screen.getByText(/#42/)).toBeDefined();

    // Engines
    expect(screen.getByText('Schema / Taxonomy')).toBeDefined();
    expect(screen.getByText('Geometry')).toBeDefined();
    expect(screen.getByText('Duplicate / Overlap')).toBeDefined();
    expect(screen.getByText('Mô hình độc lập (Detector)')).toBeDefined();
    expect(screen.getByText('Mô hình thị giác – ngôn ngữ (VLM)')).toBeDefined();
    expect(screen.getByText('Metric')).toBeDefined();

    // Thresholds
    expect(screen.getByText(/Taxonomy v4 · Thuộc tính bắt buộc theo lớp/)).toBeDefined();
    expect(screen.getByText(/Dung sai biên 3 px · Diện tích tối thiểu 30 px²/)).toBeDefined();
    expect(screen.getByText(/Intersection over Union \(IoU\) ≥ 0.9/)).toBeDefined();
    expect(screen.getByText(/Detector v2.4 · Ngưỡng tin cậy ≥ 0.75/)).toBeDefined();
    expect(screen.getByText(/Tối đa 200 candidate mỗi lần chạy/)).toBeDefined();

    // Metric has empty params, so it should display unconfigured notice rather than a fake default
    expect(screen.getByText('Chưa được cấu hình/không có dữ liệu từ API')).toBeDefined();

    // Badges
    const enabledBadges = screen.getAllByText('Bật trong config');
    expect(enabledBadges.length).toBe(4);
    const disabledBadges = screen.getAllByText('Tắt trong config');
    expect(disabledBadges.length).toBe(2);
    expect(screen.getByText('Trạng thái cấu hình')).toBeDefined();
    expect(screen.getByText('Trạng thái trong cấu hình')).toBeDefined();
    expect(screen.getByText(/Mỗi QC run dùng một config version riêng/)).toBeDefined();
  });

  it('displays indeterminate status and unconfigured notice when engines are missing or lack required params without fake fallbacks', () => {
    const sparseConfig: ConfigVersion = {
      id: 99,
      name: 'sparse-config',
      status: 'published',
      engines: {
        schema: { version: '0.1' }, // missing enabled and params
      },
      created_by: 1,
      created_at: '2026-10-09T08:00:00Z',
    };

    render(<EngineThresholdsTable config={sparseConfig} />);

    // None should be inferred as "Bật"
    expect(screen.queryByText('Bật')).toBeNull();

    // All 6 engines should be marked as not declared since enabled boolean is missing
    const unknownBadges = screen.getAllByText('Chưa khai báo');
    expect(unknownBadges.length).toBe(6);

    // All 6 engines should display unconfigured notice
    const unconfiguredNotices = screen.getAllByText('Chưa được cấu hình/không có dữ liệu từ API');
    expect(unconfiguredNotices.length).toBe(6);

    // Verify absolutely NO fake fallback defaults appear
    expect(screen.queryByText(/Taxonomy v3/)).toBeNull();
    expect(screen.queryByText(/Dung sai 2 px/)).toBeNull();
    expect(screen.queryByText(/24 px²/)).toBeNull();
    expect(screen.queryByText(/0\.85/)).toBeNull();
    expect(screen.queryByText(/Detector v2\.3/)).toBeNull();
    expect(screen.queryByText(/400/)).toBeNull();
  });

  it('renders loading state when isLoading is true', () => {
    render(<EngineThresholdsTable config={null} isLoading={true} />);
    expect(screen.getByText('Đang tải cấu hình ngưỡng engine…')).toBeDefined();
  });

  it('renders error message when error is provided', () => {
    render(<EngineThresholdsTable config={null} error="Lỗi kết nối máy chủ" />);
    expect(screen.getByText('Không tải được cấu hình engine')).toBeDefined();
    expect(screen.getByText('Lỗi kết nối máy chủ')).toBeDefined();
  });

  it('renders permission restriction notice when hasPermission is false', () => {
    render(<EngineThresholdsTable config={null} hasPermission={false} />);
    expect(screen.getByText('Giới hạn quyền truy cập')).toBeDefined();
    expect(
      screen.getByText(/Bạn không có quyền xem cấu hình ngưỡng engine/)
    ).toBeDefined();
  });

  it('renders factual empty published state without inferring whether runtime checks are active', () => {
    render(<EngineThresholdsTable config={null} />);
    expect(screen.getByText('Chưa có cấu hình đã phát hành')).toBeDefined();
    expect(
      screen.getByText(/Không thể xác nhận ngưỡng từ dữ liệu hiện có/)
    ).toBeDefined();
    expect(screen.queryByText(/Hệ thống chưa kích hoạt ngưỡng kiểm tra tự động/)).toBeNull();
  });

  it('displays raw params value when params is not empty even if formatter returns null, without calling it unconfigured (F-2)', () => {
    const configWithDetectorParams: ConfigVersion = {
      id: 50,
      name: 'detector-tau-config',
      status: 'published',
      engines: {
        detector: {
          enabled: true,
          version: '2.4.0',
          params: { tau_loc: 0.55 },
        },
      },
      created_by: 1,
      created_at: '2026-10-09T08:00:00Z',
    };

    render(<EngineThresholdsTable config={configWithDetectorParams} />);

    // Raw params must be displayed
    expect(screen.getByText('{"tau_loc":0.55}')).toBeDefined();

    // Verify UI does NOT label this data as "Chưa được cấu hình"
    const detectorTitle = screen.getByText('Mô hình độc lập (Detector)');
    const row = detectorTitle.closest('tr');
    expect(row).toBeDefined();
    expect(row?.textContent).not.toContain('Chưa được cấu hình');
    expect(row?.textContent).toContain('{"tau_loc":0.55}');
  });
});
