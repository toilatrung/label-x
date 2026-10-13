import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
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
    render(<EngineThresholdsTable config={publishedConfig} layout="analysis" />);

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
    expect(screen.getByText(/Intersection over Union ≥ 0.9/)).toBeDefined();
    expect(screen.getByText(/Detector v2.4 · Ngưỡng tin cậy ≥ 0.75/)).toBeDefined();
    expect(screen.getByText(/Tối đa 200 candidate mỗi lần chạy/)).toBeDefined();

    // Metric has no Ground Truth and the design provides a benchmark action.
    expect(screen.getByText('Chưa có Ground Truth')).toBeDefined();
    expect(screen.getByRole('link', { name: 'Chọn benchmark Ground Truth' }).getAttribute('href')).toBe('/calibration/benchmark');
    expect(screen.getAllByRole('link', { name: /Chỉnh cấu hình/ })).toHaveLength(5);

    // Thiết kế FE-03 biểu diễn cờ cấu hình bằng switch chỉ đọc.
    expect(screen.getAllByRole('checkbox').filter((control) => (control as HTMLInputElement).checked)).toHaveLength(4);
    expect(screen.getAllByRole('checkbox').filter((control) => !(control as HTMLInputElement).checked)).toHaveLength(2);
    expect(screen.getByRole('columnheader', { name: 'Bật' })).toBeDefined();
    expect(screen.getByRole('columnheader', { name: 'Cấu hình hiện tại' })).toBeDefined();
  });

  it('keeps configured status badges in the thresholds layout', () => {
    render(<EngineThresholdsTable config={publishedConfig} layout="thresholds" />);

    expect(screen.getAllByText('Bật trong config')).toHaveLength(4);
    expect(screen.getAllByText('Tắt trong config')).toHaveLength(2);
  });

  it('shows undeclared status badges in the thresholds layout', () => {
    render(<EngineThresholdsTable config={{ ...publishedConfig, engines: {} }} layout="thresholds" />);

    expect(screen.getAllByText('Chưa khai báo')).toHaveLength(6);
  });

  it('keeps Ground Truth status explicit when Metric is enabled without benchmark data', () => {
    render(<EngineThresholdsTable config={{ ...publishedConfig, engines: { metric: { enabled: true, version: '1.0.0', params: {} } } }} layout="analysis" />);

    const metricTitle = screen.getByText('Metric');
    const row = metricTitle.closest('tr');
    expect(row).toBeDefined();
    expect(within(row!).getByText('Chưa có Ground Truth')).toBeDefined();
    expect(within(row!).queryByText('Chưa được cấu hình')).toBeNull();
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

    render(<EngineThresholdsTable config={sparseConfig} layout="analysis" />);

    // Không engine nào bị suy diễn là bật; aria-label nói rõ trạng thái chưa khai báo.
    const unknownControls = screen.getAllByRole('checkbox', { name: /chưa khai báo/ });
    expect(unknownControls).toHaveLength(6);
    expect(unknownControls.every((control) => !(control as HTMLInputElement).checked)).toBe(true);

    // Five non-Metric engines display the generic notice; Metric has a specific Ground Truth state.
    const unconfiguredNotices = screen.getAllByText('Chưa được cấu hình');
    expect(unconfiguredNotices.length).toBe(5);
    expect(screen.getByText('Chưa có Ground Truth')).toBeDefined();

    // Verify absolutely NO fake fallback defaults appear
    expect(screen.queryByText(/Taxonomy v3/)).toBeNull();
    expect(screen.queryByText(/Dung sai 2 px/)).toBeNull();
    expect(screen.queryByText(/24 px²/)).toBeNull();
    expect(screen.queryByText(/0\.85/)).toBeNull();
    expect(screen.queryByText(/Detector v2\.3/)).toBeNull();
    expect(screen.queryByText(/400/)).toBeNull();
  });

  it('shows nonempty params outside the formatter instead of claiming data is missing', () => {
    const params = { required_attributes: { car: ['occluded'] }, custom_threshold: 0.42 };
    render(
      <EngineThresholdsTable
        config={{
          ...publishedConfig,
          engines: { schema: { enabled: true, version: '1.0.0', params } },
        }}
        layout="analysis"
      />
    );

    const row = screen.getByText('Schema / Taxonomy').closest('tr')!;
    expect(within(row).getByText(JSON.stringify(params))).toBeDefined();
    expect(within(row).queryByText('Chưa được cấu hình')).toBeNull();
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
      screen.getByText(/Trạng thái này không đồng nghĩa engine đang tắt/)
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
