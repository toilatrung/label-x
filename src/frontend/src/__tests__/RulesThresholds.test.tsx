import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RulesThresholdsPage from '@/app/configuration/rules-thresholds/page';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace }),
  usePathname: () => '/configuration/rules-thresholds',
}));

const MAPPINGS_PATH = '/api/guidelines/mappings/';
const CONFIG_VERSIONS_PATH = '/api/config-versions/';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const mapping = (
  error_group: string,
  class_name: string,
  paired_class: string,
  rule_id: string,
  guideline_version = 'v1.0'
) => ({
  error_group,
  class_name,
  paired_class,
  rule_id,
  guideline_version,
});

const samplePublishedConfig = {
  id: 10,
  name: 'cfg-v1',
  status: 'published' as const,
  engines: {
    schema: { enabled: true, version: '1.0.0', params: { taxonomy_version: 'Taxonomy v3' } },
    geometry: { enabled: true, version: '1.0.0', params: { tolerance_px: 2, min_area_px: 24 } },
    duplicate: { enabled: true, version: '1.0.0', params: { iou_threshold: 0.85 } },
    detector: { enabled: true, version: '2.3.0', params: { model_version: 'Detector v2.3', confidence_threshold: 0.6 } },
    vlm: { enabled: true, version: '1.0.0', params: { max_candidates: 400 } },
    metric: { enabled: false, version: '1.0.0', params: {} },
  },
  thresholds: { iou: 0.85 },
  models: { detector: 'v2.3' },
  created_by: 1,
  created_at: '2026-10-09T10:00:00Z',
  published_at: '2026-10-09T10:30:00Z',
};

async function setup(
  username: string,
  mappingHandler: (url: URL) => Response,
  configHandler?: (url: URL) => Response
) {
  const api = installMockAuthApi();
  await api.signIn(username);
  const passthrough = api.fetchSpy.getMockImplementation()!;
  api.fetchSpy.mockImplementation(async (request: Request) => {
    const url = new URL(request.url);
    if (url.pathname === MAPPINGS_PATH) return mappingHandler(url);
    if (url.pathname === CONFIG_VERSIONS_PATH) {
      return configHandler ? configHandler(url) : json({ next: null, previous: null, results: [] });
    }
    return passthrough(request);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <RulesThresholdsPage />
      </AuthProvider>
    </QueryClientProvider>
  );
  const mappingCalls = () =>
    api.fetchSpy.mock.calls
      .map(([request]) => new URL(request.url))
      .filter((url) => url.pathname === MAPPINGS_PATH);
  const configCalls = () =>
    api.fetchSpy.mock.calls
      .map(([request]) => new URL(request.url))
      .filter((url) => url.pathname === CONFIG_VERSIONS_PATH);
  return { api, mappingCalls, configCalls };
}

describe('Rules & Thresholds page (T-017 & T-029)', () => {
  it('renders mapping table and restricts engine config viewing for reviewer', async () => {
    const { configCalls } = await setup('reviewer', () =>
      json({
        next: null,
        previous: null,
        results: [
          mapping('E2', 'car', 'truck', 'RULE-01', 'bdd-v1'),
          mapping('E1', 'pedestrian', '', 'RULE-02', 'bdd-v1'),
        ],
      })
    );

    expect(await screen.findByText('RULE-01')).toBeDefined();
    expect(screen.getByText('Rules và Thresholds')).toBeDefined();
    expect(screen.getByText('RULE-02')).toBeDefined();
    expect(screen.getByText('car')).toBeDefined();
    expect(screen.getByText('truck')).toBeDefined();
    expect(screen.getByText('pedestrian')).toBeDefined();
    expect(screen.getByText(/2 mapping trên trang/)).toBeDefined();

    // Reviewer không có quyền xem cấu hình engine; hiển thị thông báo quyền, không gọi API
    expect(screen.getByText('Giới hạn quyền truy cập')).toBeDefined();
    expect(
      screen.getByText(/Bạn không có quyền xem cấu hình ngưỡng engine/)
    ).toBeDefined();
    expect(configCalls()).toHaveLength(0);

    // Xác nhận không có bất kỳ nút hoặc điều khiển sửa/xóa nào
    expect(screen.queryByRole('button', { name: /sửa|chỉnh sửa|edit|xoá|xóa|delete/i })).toBeNull();
  });

  it('renders published engine thresholds and effective params when QA Lead accesses the page', async () => {
    const { configCalls } = await setup(
      'qalead',
      () => json({ next: null, previous: null, results: [] }),
      () => json({ next: null, previous: null, results: [samplePublishedConfig] })
    );

    expect(await screen.findByText('cfg-v1')).toBeDefined();
    expect(screen.getByText(/Ngưỡng kiểm tra engine/)).toBeDefined();
    expect(screen.getByText(/Phiên bản phát hành:/)).toBeDefined();

    // Hiển thị đầy đủ các engine
    expect(screen.getByText('Schema / Taxonomy')).toBeDefined();
    expect(screen.getByText('Geometry')).toBeDefined();
    expect(screen.getByText('Duplicate / Overlap')).toBeDefined();
    expect(screen.getByText('Mô hình độc lập (Detector)')).toBeDefined();
    expect(screen.getByText('Mô hình thị giác – ngôn ngữ (VLM)')).toBeDefined();
    expect(screen.getByText('Metric')).toBeDefined();

    // Hiển thị ngưỡng hiệu lực từ params
    expect(screen.getByText(/Intersection over Union \(IoU\) ≥ 0.85/)).toBeDefined();
    expect(screen.getByText(/Dung sai biên 2 px · Diện tích tối thiểu 24 px²/)).toBeDefined();
    expect(screen.getByText(/Detector v2.3 · Ngưỡng tin cậy ≥ 0.6/)).toBeDefined();

    expect(configCalls()).toHaveLength(1);
  });

  it('shows empty state for engine configuration when no published config exists', async () => {
    await setup(
      'qcadmin',
      () => json({ next: null, previous: null, results: [] }),
      () => json({ next: null, previous: null, results: [] })
    );

    expect(await screen.findByText('Chưa có cấu hình đã phát hành')).toBeDefined();
    expect(
      screen.getByText(/Không thể xác nhận ngưỡng từ dữ liệu hiện có/)
    ).toBeDefined();
    expect(screen.getByText('Chưa có mapping guideline.')).toBeDefined();
  });

  it('shows error alert when config-versions API fails for authorized user', async () => {
    await setup(
      'qcadmin',
      () => json({ next: null, previous: null, results: [] }),
      () => json({ code: 'SERVER_ERROR', message: 'Database connection failed' }, 500)
    );

    expect(await screen.findByText('Không tải được cấu hình engine')).toBeDefined();
  });

  it('handles pagination: next button fetches next page with cursor and previous button returns', async () => {
    const { mappingCalls } = await setup('reviewer', (url) => {
      const cursor = url.searchParams.get('cursor');
      if (cursor === 'page-2-token') {
        return json({
          next: null,
          previous: 'http://localhost/api/guidelines/mappings/?cursor=page-1-token',
          results: [mapping('structural', 'bus', '', 'RULE-51', 'bdd-v1')],
        });
      }
      return json({
        next: 'http://localhost/api/guidelines/mappings/?cursor=page-2-token',
        previous: null,
        results: [mapping('E1', 'car', '', 'RULE-01', 'bdd-v1')],
      });
    });

    // Trang 1
    expect(await screen.findByText('RULE-01')).toBeDefined();
    expect(screen.getByText(/Trang 1/)).toBeDefined();
    const nextBtn = screen.getByRole('button', { name: 'Trang sau' }) as HTMLButtonElement;
    const prevBtn = screen.getByRole('button', { name: 'Trang trước' }) as HTMLButtonElement;
    expect(nextBtn.disabled).toBe(false);
    expect(prevBtn.disabled).toBe(true);

    // Bấm Trang sau
    fireEvent.click(nextBtn);
    expect(await screen.findByText('RULE-51')).toBeDefined();
    expect(screen.getByText(/Trang 2/)).toBeDefined();
    expect(nextBtn.disabled).toBe(true);
    expect(prevBtn.disabled).toBe(false);

    // Bấm Trang trước
    fireEvent.click(prevBtn);
    expect(await screen.findByText('RULE-01')).toBeDefined();
    expect(screen.getByText(/Trang 1/)).toBeDefined();

    expect(mappingCalls().length).toBeGreaterThanOrEqual(2);
  });

  it('shows error alert when mapping API fails', async () => {
    await setup('reviewer', () =>
      json({ code: 'SERVER_ERROR', message: 'Internal Server Error' }, 500)
    );
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Không tải được mapping')).toBeDefined();
  });

  it('blocks unauthorized roles (annotator) via AuthGuard before calling API', async () => {
    const { mappingCalls, configCalls } = await setup('annotator', () =>
      json({ next: null, previous: null, results: [] })
    );
    expect(await screen.findByText('403 - Quyền truy cập bị từ chối')).toBeDefined();
    expect(mappingCalls()).toHaveLength(0);
    expect(configCalls()).toHaveLength(0);
  });
});
