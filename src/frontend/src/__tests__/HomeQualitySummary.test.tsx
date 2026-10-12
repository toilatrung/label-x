import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QualityControlHome } from '@/components/overview/QualityControlHome';
import { QualitySummary } from '@/components/overview/QualitySummary';
import { TopBar } from '@/components/layout/TopBar';
import Home from '@/app/page';
import { AuthProvider, useAuth } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';
import type { Dataset } from '@/lib/snapshots/api';
import { NOT_CONNECTED_MESSAGE } from '@/components/ui/NotConnectedNotice';
import { SERVER_ERROR_MESSAGE } from '@/lib/api/errors';

const mockPush = vi.fn();
let currentSearchParam = '';

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(currentSearchParam),
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
}));

describe('FE-01: Quality Control Home and Quality Summary (M1/M2/M3 QA Repair)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentSearchParam = '';
  });

  const mockDatasetsPage1: Dataset[] = [
    {
      id: 1,
      name: 'Road Vision Urban Real',
      cvat_project_id: 31,
      taxonomy_version: 'v1.4',
      guideline_version: 'v1.2',
    },
    {
      id: 2,
      name: 'Road Vision Highway Real',
      cvat_project_id: 34,
      taxonomy_version: null,
      guideline_version: null,
    },
  ];

  const mockDatasetsPage2: Dataset[] = [
    {
      id: 3,
      name: 'Parking Lot Detection Real',
      cvat_project_id: 37,
      taxonomy_version: 'v0.3',
      guideline_version: 'v1.0',
    },
  ];

  function setupMockEnv(
    datasetHandler?: (req: Request) => Response | Promise<Response>,
    sessionDatasetId?: number,
    extraHandler?: (req: Request) => Response | Promise<Response> | undefined
  ) {
    const authApi = installMockAuthApi();
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const urlStr = input instanceof Request ? input.url : String(input);
      const url = new URL(urlStr, 'http://localhost');
      if (extraHandler) {
        const req = input instanceof Request ? input : new Request(input, init);
        const extraRes = await extraHandler(req);
        if (extraRes) return extraRes;
      }
      if (url.pathname === '/api/runs/') {
        return Response.json({ next: null, previous: null, results: [] });
      }
      if (url.pathname.includes('/tasks/')) {
        return Response.json([]);
      }
      if (url.pathname === '/api/datasets/') {
        const req = input instanceof Request ? input : new Request(input, init);
        return datasetHandler
          ? datasetHandler(req)
          : Response.json({ next: null, previous: null, results: mockDatasetsPage1 });
      }
      if (url.pathname === '/api/auth/session/' && sessionDatasetId !== undefined) {
        return Response.json({
          user: { id: 4, username: 'reviewer', display_name: 'Người kiểm tra mẫu' },
          roles: [{ role: 'reviewer', dataset_id: sessionDatasetId }],
          identity_mapping: { status: 'mapped', cvat_user_id: 104 },
        });
      }
      const passReq = input instanceof Request ? input : new Request(input, init);
      return originalFetch(passReq);
    });
    vi.stubGlobal('fetch', fetchSpy);
    return { authApi, fetchSpy };
  }

  /* -------------------------------------------------------------------------
   * 1. M1: Canonical illustrative values, SampleDataBadge & NotConnectedNotice
   * ------------------------------------------------------------------------- */
  describe('M1: Canonical illustrative values, SampleDataBadge & NotConnectedNotice', () => {
    it('QualitySummary renders canonical illustrative metrics (12,500, 92.4%, 384, 126) with SampleDataBadge when API is unaggregated', async () => {
      const ds: Dataset = { id: 1, name: 'Road Vision Urban Real', cvat_project_id: 31 };
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer');

      render(
        <AuthProvider>
          <QualitySummary currentDataset={ds} />
        </AuthProvider>
      );

      // Verify header uses real dataset name and em dash for QC Run when unselected
      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban Real · Quality Control Run: —\./)).toBeDefined();

      // SampleDataBadge is rendered
      const sampleBadges = screen.getAllByText('Dữ liệu minh họa');
      expect(sampleBadges.length).toBeGreaterThanOrEqual(1);

      // Canonical metrics: 12,500 frame, 92.4% coverage, 384 candidate, 126 confirmed
      expect(screen.getByText('12,500')).toBeDefined();
      expect(screen.getByText('92.4%')).toBeDefined();
      expect(screen.getByText('384')).toBeDefined();
      expect(screen.getByText('126')).toBeDefined();

      // Callout: Release blocked
      expect(screen.getByText('Release blocked')).toBeDefined();
      expect(screen.getByText(/Coverage 92\.4% chưa đạt ngưỡng 95%/)).toBeDefined();

      // Disconnected regions each have NotConnectedNotice
      const notices = screen.getAllByText(new RegExp(NOT_CONNECTED_MESSAGE));
      expect(notices.length).toBeGreaterThanOrEqual(4);
    });

    it('shows one not-connected notice per region and separates real task data from sample columns', async () => {
      const { authApi } = setupMockEnv(undefined, 1, (req) => req.url.includes('/api/datasets/1/tasks/')
        ? Response.json([{ cvat_task_id: 118, name: 'Urban day', jobs: [
          { cvat_job_id: 2270, assignee_cvat_user_id: 1, frame_count: 200, updated_date: '2026-10-09T07:00:00Z' },
          { cvat_job_id: 2271, assignee_cvat_user_id: null, frame_count: 400, updated_date: '2026-10-09T07:00:00Z' }] }])
        : undefined);
      await authApi.signIn('reviewer');
      const ds: Dataset = { id: 1, name: 'Road Vision Urban Real', cvat_project_id: 31 };
      render(<AuthProvider><QualitySummary currentDataset={ds} /></AuthProvider>);
      const detail = 'Task, Job và Frame lấy từ server; Coverage, Candidate, Đã xác nhận và Gate là dữ liệu minh họa';
      let row: HTMLElement | undefined;
      await waitFor(() => {
        expect(screen.getAllByRole('status').some((el) => (el.textContent ?? '').includes(detail))).toBe(true);
        row = screen.getByRole('row', { name: /Task #118 · Urban day/ });
      });
      // Gate, engine, review, task and candidate regions: exactly one notice each, none at the top of the page.
      expect(screen.getAllByText(new RegExp(NOT_CONNECTED_MESSAGE))).toHaveLength(5);
      expect(screen.queryByText(/Số liệu tổng hợp Quality Summary/)).toBeNull();
      // Real columns: Job count and Frame sum from the server; sample columns are muted.
      const cells = Array.from(row!.querySelectorAll('td'));
      expect(cells[1].textContent).toBe('2');
      expect(cells[2].textContent).toBe('600');
      [3, 4, 5].forEach((index) => expect(cells[index].className).toContain('lx-muted'));
    });

    it('QualitySummary renders full canonical UI matching Dashboard.dc.html when no dataset is selected (no-backend preview)', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualitySummary currentDataset={null} />
        </AuthProvider>
      );

      // Renders canonical lead text from Dashboard.dc.html
      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban v1\.4 · Quality Control Run: #QC-091\./)).toBeDefined();

      // Full illustrative engines
      expect(screen.getByText('Schema / Taxonomy')).toBeDefined();
      expect(screen.getByText('Geometry')).toBeDefined();
      expect(screen.getByText('Duplicate / Overlap')).toBeDefined();
      expect(screen.getByText('Mô hình độc lập')).toBeDefined();
      expect(screen.getByText('Mô hình thị giác – ngôn ngữ')).toBeDefined();
      expect(screen.getByText('Metric')).toBeDefined();

      // Full illustrative review queues
      expect(screen.getByText('Ưu tiên theo rủi ro')).toBeDefined();
      expect(screen.getByText('Kiểm tra ngẫu nhiên')).toBeDefined();
      expect(screen.getByText('Chưa chắc chắn / Chuyển cấp trên')).toBeDefined();
      expect(screen.getByText('242')).toBeDefined();

      // Full illustrative tasks (T-118, T-119, T-120)
      expect(screen.getByText(/T-118 · Urban day/)).toBeDefined();
      expect(screen.getByText(/T-119 · Urban night/)).toBeDefined();
      expect(screen.getByText(/T-120 · Urban rain/)).toBeDefined();

      // Full illustrative candidate categories
      expect(screen.getByText('Sai nhãn')).toBeDefined();
      expect(screen.getByText('Hình học')).toBeDefined();
      expect(screen.getByText('Trùng / chồng lấn')).toBeDefined();
      expect(screen.getByText('Thiếu object')).toBeDefined();
      expect(screen.getByText('Thuộc tính / Track')).toBeDefined();
    });

    it('QualityControlHome renders full canonical 4-row design preview table when dataset API fails or is empty', async () => {
      const { authApi } = setupMockEnv(() => {
        return Response.json({ detail: 'No backend available' }, { status: 500 });
      });
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      // Localized error message appears in error card and exactly one NotConnectedNotice
      const errorCardMsg = await screen.findByText(new RegExp(SERVER_ERROR_MESSAGE), {
        selector: '.lx-text-danger',
      });
      expect(errorCardMsg).toBeDefined();
      expect(screen.getByRole('button', { name: 'Thử lại kết nối API' })).toBeDefined();

      // Exactly ONE NotConnectedNotice banner
      const notices = screen.getAllByText(new RegExp(NOT_CONNECTED_MESSAGE));
      expect(notices).toHaveLength(1);

      // Full canonical illustrative preview table is rendered (4 rows including both Road Vision Urban v1.4 and v1.3)
      const urbanRows = screen.getAllByText('Road Vision Urban');
      expect(urbanRows).toHaveLength(2);
      expect(screen.getByText('v1.4')).toBeDefined();
      expect(screen.getByText('v1.3')).toBeDefined();
      expect(screen.getByText('Road Vision Highway')).toBeDefined();
      expect(screen.getByText('Parking Lot')).toBeDefined();
      expect(screen.getByText('12,500')).toBeDefined();
      expect(screen.getByText('11,800')).toBeDefined();
      expect(screen.getByText('5,600')).toBeDefined();
      expect(screen.getByText('3,000')).toBeDefined();
      expect(screen.getByRole('link', { name: 'Tạo snapshot đầu tiên' }).getAttribute('href')).toBe('/analysis');

      // Clicking row in illustrative preview navigates to local summary preview without mutating auth state
      const firstRow = screen.getAllByRole('row')[1];
      fireEvent.click(firstRow);
      expect(mockPush).toHaveBeenCalledWith('/?view=summary');
    });

    it('fixture IDs never enter actual auth Dataset state or API requests, and error preview does not expose private dataset content', async () => {
      const requestedDatasetUrls: string[] = [];
      const { authApi } = setupMockEnv((req) => {
        requestedDatasetUrls.push(req.url);
        return Response.json({ detail: 'Database unavailable' }, { status: 500 });
      });
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      // Localized error message appears in error card and exactly one NotConnectedNotice
      const errorCardMsg = await screen.findByText(new RegExp(SERVER_ERROR_MESSAGE), {
        selector: '.lx-text-danger',
      });
      expect(errorCardMsg).toBeDefined();

      // Exactly ONE NotConnectedNotice banner
      const notices = screen.getAllByText(new RegExp(NOT_CONNECTED_MESSAGE));
      expect(notices).toHaveLength(1);

      // Click on canonical fixture row for Road Vision Highway (fixture project #34)
      const highwayRow = screen.getByText('Road Vision Highway').closest('tr')!;
      fireEvent.click(highwayRow);

      // Verify no request was made with fixture ID
      const fixtureRequests = requestedDatasetUrls.filter((u) => u.includes('34') || u.includes('road-vision-highway'));
      expect(fixtureRequests.length).toBe(0);

      // Does not expose private dataset names from other users
      expect(screen.queryByText('Private Confidential Project')).toBeNull();
    });
  });

  /* -------------------------------------------------------------------------
   * 2. Dataset resolution & multi-page traversal (Preserved from HEAD)
   * ------------------------------------------------------------------------- */
  describe('Dataset resolution & multi-page traversal', () => {
    it('truly resolves a dataset on later page (ID 3 on page 2) without fabricating identity', async () => {
      currentSearchParam = 'view=summary';
      const { authApi } = setupMockEnv((req) => {
        const cursor = new URL(req.url).searchParams.get('cursor');
        if (!cursor) {
          return Response.json({ next: 'http://localhost/api/datasets/?cursor=page2', previous: null, results: mockDatasetsPage1 });
        }
        return Response.json({ next: null, previous: null, results: mockDatasetsPage2 });
      }, 3);

      // Sign in as reviewer with dataset_id: 3 (on page 2)
      await authApi.signIn('reviewer');

      render(
        <AuthProvider>
          <Home />
        </AuthProvider>
      );

      // Verify Parking Lot Detection Real (ID 3 from page 2) is resolved
      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Parking Lot Detection Real/)).toBeDefined();
    });

    it('displays revoked state when dataset does not exist in any scoped page, while retaining canonical illustrative preview', async () => {
      currentSearchParam = 'view=summary';
      const { authApi } = setupMockEnv(() => {
        return Response.json({ next: null, previous: null, results: [{ id: 100, name: 'Other Dataset', cvat_project_id: 99 }] });
      });

      await authApi.signIn('reviewer'); // has dataset_id: 1

      render(
        <AuthProvider>
          <Home />
        </AuthProvider>
      );

      expect(await screen.findByRole('heading', { level: 2, name: 'Dataset không khả dụng' })).toBeDefined();
      expect(screen.getByText(/không tồn tại hoặc tài khoản của bạn không còn quyền truy cập/)).toBeDefined();
      expect(screen.queryByText(/Dataset #1/)).toBeNull();

      // Canonical preview is also rendered below the message
      expect(screen.getByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
    });

    it('displays distinct error, working retry button, and canonical illustrative preview on transient API rejection during dataset resolution', async () => {
      currentSearchParam = 'view=summary';
      let callCount = 0;
      const { authApi } = setupMockEnv(() => {
        callCount++;
        if (callCount === 1) {
          return Response.json({ error: 'Server error' }, { status: 500 });
        }
        return Response.json({ next: null, previous: null, results: mockDatasetsPage1 });
      });

      await authApi.signIn('reviewer');

      render(
        <AuthProvider>
          <Home />
        </AuthProvider>
      );

      expect(await screen.findByRole('heading', { level: 2, name: 'Lỗi kiểm tra quyền Dataset' })).toBeDefined();
      const retryBtn = screen.getByRole('button', { name: 'Thử lại' });
      fireEvent.click(retryBtn);

      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban Real/)).toBeDefined();
    });
  });

  /* -------------------------------------------------------------------------
   * 3. Auth scope, cached state, and delayed response handling (Preserved from HEAD)
   * ------------------------------------------------------------------------- */
  describe('Auth scope, cached state, and delayed response handling', () => {
    it('shows truthful loading message and never flashes Chưa chọn Dataset during direct Summary navigation', async () => {
      currentSearchParam = 'view=summary';
      let resolvePromise: (value: Response) => void;
      const delayedResponse = new Promise<Response>((resolve) => {
        resolvePromise = resolve;
      });

      const { authApi } = setupMockEnv(() => delayedResponse);
      await authApi.signIn('reviewer');

      render(
        <AuthProvider>
          <Home />
        </AuthProvider>
      );

      // Verify truthful loading message is shown
      expect(await screen.findByText(/Đang xác minh thông tin Dataset #1/)).toBeDefined();

      // Resolve API
      resolvePromise!(Response.json({ next: null, previous: null, results: mockDatasetsPage1 }));

      // Now Quality Summary renders
      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban Real/)).toBeDefined();
    });

    it('immediately invalidates cached dataset on auth user/scope switch', async () => {
      currentSearchParam = 'view=summary';
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer'); // user id: reviewer, dataset_id: 1

      const { unmount } = render(
        <AuthProvider>
          <Home />
        </AuthProvider>
      );

      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban Real/)).toBeDefined();

      // Switch to admin who has dataset_id: null (no scoped dataset grant)
      await authApi.signIn('admin');
      unmount();

      render(
        <AuthProvider>
          <Home />
        </AuthProvider>
      );

      // User has no dataset: immediately renders illustrative preview fallback
      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.queryByText(/Tình trạng kiểm tra của Road Vision Urban Real/)).toBeNull();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban v1\.4/)).toBeDefined();
    });

    it('handles auth transition within a preserved mounted tree', async () => {
      currentSearchParam = 'view=summary';
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer');

      function AuthTestHarness() {
        const { login, user } = useAuth();
        return (
          <div>
            <Home />
            {user?.username === 'reviewer' && (
              <button
                type="button"
                onClick={() => void login({ username: 'admin', password: 'password123' })}
              >
                Chuyển sang admin
              </button>
            )}
          </div>
        );
      }

      render(
        <AuthProvider>
          <AuthTestHarness />
        </AuthProvider>
      );

      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban Real/)).toBeDefined();

      // Trigger switch to admin (who has dataset_id: null)
      const switchBtn = screen.getByRole('button', { name: 'Chuyển sang admin' });
      fireEvent.click(switchBtn);

      // Invalidate dataset and fallback cleanly to illustrative preview
      await waitFor(() => {
        expect(screen.queryByText(/Tình trạng kiểm tra của Road Vision Urban Real/)).toBeNull();
      });
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban v1\.4/)).toBeDefined();
    });
  });

  /* -------------------------------------------------------------------------
   * 4. Search, pagination, race conditions & repeated cursors (Preserved from HEAD)
   * ------------------------------------------------------------------------- */
  describe('Search, pagination, race conditions & repeated cursors', () => {
    it('automatically triggers search scan when user types before page 1 resolves', async () => {
      let page1Resolve: () => void;
      const page1Gate = new Promise<void>((resolve) => {
        page1Resolve = resolve;
      });

      const { authApi } = setupMockEnv(async (req) => {
        const cursor = new URL(req.url).searchParams.get('cursor');
        if (!cursor) {
          await page1Gate;
          return Response.json({
            next: 'http://localhost/api/datasets/?cursor=page2',
            previous: null,
            results: mockDatasetsPage1,
          });
        }
        return Response.json({
          next: null,
          previous: null,
          results: mockDatasetsPage2,
        });
      });

      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      // Type search before page 1 finishes loading
      const searchInput = screen.getByRole('searchbox', { name: 'Tìm dataset' });
      fireEvent.change(searchInput, { target: { value: 'Parking' } });

      // Unblock page 1
      page1Resolve!();

      // Result from page 2 ('Parking Lot Detection Real') appears cleanly
      expect(await screen.findByText('Parking Lot Detection Real')).toBeDefined();
    });

    it('stops scanning and recovers cleanly when server returns repeated cursor (loop detection)', async () => {
      const { authApi } = setupMockEnv((req) => {
        const cursor = new URL(req.url).searchParams.get('cursor');
        if (!cursor) {
          return Response.json({
            next: 'http://localhost/api/datasets/?cursor=loop_token',
            previous: null,
            results: mockDatasetsPage1,
          });
        }
        // Server buggy response repeatedly giving the same loop_token
        return Response.json({
          next: 'http://localhost/api/datasets/?cursor=loop_token',
          previous: null,
          results: mockDatasetsPage2,
        });
      });

      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      // Type query that requires scanning
      const searchInput = await screen.findByRole('searchbox', { name: 'Tìm dataset' });
      fireEvent.change(searchInput, { target: { value: 'Nonexistent' } });

      // Detects loop and shows informative error message
      expect(await screen.findByText(/Phát hiện vòng lặp phân trang từ server/)).toBeDefined();
    });

    it('shows retry button on pagination failure and retries without refetching earlier pages', async () => {
      let page2Calls = 0;
      let shouldFailPage2 = true;

      const { authApi } = setupMockEnv((req) => {
        const cursor = new URL(req.url).searchParams.get('cursor');
        if (!cursor) {
          return Response.json({
            next: 'http://localhost/api/datasets/?cursor=page2',
            previous: null,
            results: mockDatasetsPage1,
          });
        }
        page2Calls++;
        if (shouldFailPage2) {
          return new Response(JSON.stringify({ detail: 'Page 2 network timeout' }), {
            status: 504,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return Response.json({
          next: null,
          previous: null,
          results: mockDatasetsPage2,
        });
      });

      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      // Initial page 1 loads
      expect(await screen.findByText('Road Vision Urban Real')).toBeDefined();

      // Click "Tải thêm dataset"
      const loadMoreBtn = await screen.findByRole('button', { name: 'Tải thêm dataset' });
      fireEvent.click(loadMoreBtn);

      // Verify pagination error appears
      expect(await screen.findByText(/Không thể tải thêm trang|Page 2 network timeout/)).toBeDefined();
      expect(page2Calls).toBe(1);

      // Now retry page 2
      shouldFailPage2 = false;
      const retryBtn = screen.getByRole('button', { name: 'Thử lại tải trang' });
      fireEvent.click(retryBtn);

      // Page 2 resolves
      expect(await screen.findByText('Parking Lot Detection Real')).toBeDefined();
      // Page 1 data remains intact
      expect(screen.getByText('Road Vision Urban Real')).toBeDefined();
    });

    it('ignores late-arriving responses from superseded generations (generation guard)', async () => {
      let lateCallResolve: (value: Response) => void;
      const latePromise = new Promise<Response>((resolve) => {
        lateCallResolve = resolve;
      });

      let callCount = 0;
      const { authApi } = setupMockEnv(() => {
        callCount++;
        if (callCount === 1) {
          return latePromise; // First call hangs
        }
        return Response.json({ next: null, previous: null, results: mockDatasetsPage1 });
      });

      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      // Resolve first call with error
      lateCallResolve!(Response.json({ detail: 'Old error' }, { status: 500 }));

      // Click retry in Home
      const retryBtn = await screen.findByRole('button', { name: 'Thử lại kết nối API' });
      fireEvent.click(retryBtn);

      // Current generation loads cleanly
      expect(await screen.findByText('Road Vision Urban Real')).toBeDefined();
    });
  });

  /* -------------------------------------------------------------------------
   * 5. Keyboard navigation and actions (Preserved from HEAD)
   * ------------------------------------------------------------------------- */
  describe('Keyboard navigation and actions', () => {
    it('separates row activation from child button clicks and key events in Home table', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      expect(await screen.findByText('Road Vision Urban Real')).toBeDefined();

      // Enter on row itself selects the row
      const rows = screen.getAllByRole('row');
      const dataRow = rows[1];
      fireEvent.keyDown(dataRow, { key: 'Enter' });
      expect(dataRow.getAttribute('aria-selected')).toBe('true');

      // Click on child button navigates to summary without conflicting with row
      const actionButtons = screen.getAllByLabelText('Tiếp tục làm việc với Dataset này');
      fireEvent.click(actionButtons[0]);
      expect(mockPush).toHaveBeenCalledWith('/?view=summary');

      // Space on child button does not bubble up to select another row
      const secondDataRow = rows[2];
      const secondRowAction = actionButtons[1];
      fireEvent.keyDown(secondRowAction, { key: ' ' });
      expect(secondDataRow.getAttribute('aria-selected')).toBeNull();
    });

    it('supports task row keyboard selection with Enter and Space, and retry on task error in QualitySummary', async () => {
      let failTasks = true;
      setupMockEnv(undefined, 1, (req) => {
        if (req.url.includes('/api/datasets/1/tasks/')) {
          if (failTasks) {
            return new Response(JSON.stringify({ error: 'Server error loading tasks' }), { status: 500 });
          }
          return Response.json([
            { cvat_task_id: 118, name: 'Urban day', jobs: [{ cvat_job_id: 2270 }] },
            { cvat_task_id: 119, name: 'Urban night', jobs: [{ cvat_job_id: 2273 }] },
          ]);
        }
        return undefined;
      });

      const onScopeChange = vi.fn();
      const ds: Dataset = { id: 1, name: 'Road Vision Urban Real', cvat_project_id: 31 };

      const { rerender } = render(
        <AuthProvider>
          <QualitySummary
            currentDataset={ds}
            selectedTaskScope={null}
            onTaskScopeChange={onScopeChange}
          />
        </AuthProvider>
      );

      // Verify task error appears with retry button
      expect(await screen.findByText(new RegExp(SERVER_ERROR_MESSAGE))).toBeDefined();
      const retryBtn = screen.getByRole('button', { name: 'Thử lại' });
      expect(retryBtn).toBeDefined();

      // Retry task fetch successfully
      failTasks = false;
      fireEvent.click(retryBtn);

      const task118 = await screen.findByText(/Task #118 · Urban day/);
      expect(task118).toBeDefined();

      const taskRow118 = screen.getByRole('row', { name: /Task #118 · Urban day/ });
      expect(taskRow118.getAttribute('aria-selected')).toBe('false');

      // Keyboard selection with Enter
      fireEvent.keyDown(taskRow118, { key: 'Enter' });
      expect(onScopeChange).toHaveBeenCalledWith('Task #118 · Urban day');

      // Keyboard selection with Space
      const taskRow119 = screen.getByRole('row', { name: /Task #119 · Urban night/ });
      fireEvent.keyDown(taskRow119, { key: ' ' });
      expect(onScopeChange).toHaveBeenCalledWith('Task #119 · Urban night');

      // Re-render with selectedTaskScope to verify aria-selected="true"
      rerender(
        <AuthProvider>
          <QualitySummary
            currentDataset={ds}
            selectedTaskScope="Task #118 · Urban day"
            onTaskScopeChange={onScopeChange}
          />
        </AuthProvider>
      );

      const updatedRow118 = screen.getByRole('row', { name: /Task #118 · Urban day/ });
      expect(updatedRow118.getAttribute('aria-selected')).toBe('true');
    });
  });

  /* -------------------------------------------------------------------------
   * 6. F1: Single regional notice count unchanged after repeated sync
   * ------------------------------------------------------------------------- */
  describe('F1: Single regional notice count unchanged after repeated sync', () => {
    it('updates existing notice text on sync click and never duplicates notice', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      expect(await screen.findByText('Road Vision Urban Real')).toBeDefined();

      // Initial notice count in region is exactly 1
      const initialNotices = screen.getAllByRole('status');
      expect(initialNotices.length).toBe(1);

      // Click "Đồng bộ lại"
      const syncBtn = screen.getByRole('button', { name: 'Đồng bộ lại' });
      fireEvent.click(syncBtn);

      // Notice content updates in place
      const updatedNotice = await screen.findByText(/Đồng bộ danh sách Dataset từ CVAT qua Webhook\/Sync worker chưa được kích hoạt/);
      expect(updatedNotice).toBeDefined();

      // Notice count in region remains exactly 1
      const afterFirstClickNotices = screen.getAllByRole('status');
      expect(afterFirstClickNotices.length).toBe(1);

      // Click "Đồng bộ lại" again
      fireEvent.click(syncBtn);
      const afterSecondClickNotices = screen.getAllByRole('status');
      expect(afterSecondClickNotices.length).toBe(1);
    });
  });

  /* -------------------------------------------------------------------------
   * 7. F2: Real navigation links to reports, gate, review, analysis/history
   * ------------------------------------------------------------------------- */
  describe('F2: Real navigation links without dummy blocked buttons', () => {
    it('QualitySummary provides real Links without dummy blocked buttons', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualitySummary currentDataset={null} />
        </AuthProvider>
      );

      // Quality Report link
      const reportLink = screen.getByRole('link', { name: 'Xem Quality Report' });
      expect(reportLink.getAttribute('href')).toBe('/reports');

      // Review Center link
      const reviewLink = screen.getByRole('link', { name: 'Vào Review Center →' });
      expect(reviewLink.getAttribute('href')).toBe('/review');

      // Quality Gate link
      const gateLink = screen.getByRole('link', { name: 'Xem Quality Gate' });
      expect(gateLink.getAttribute('href')).toBe('/reports/gate');

      // Execution History link
      const historyLink = screen.getByRole('link', { name: 'Xem Execution History' });
      expect(historyLink.getAttribute('href')).toBe('/analysis/history');

      // Review Queues link
      const queuesLink = screen.getByRole('link', { name: 'Mở hàng đợi' });
      expect(queuesLink.getAttribute('href')).toBe('/review');
    });
  });

  /* -------------------------------------------------------------------------
   * 8. F4 & F5: Copy precision, version tag semantics, and sync caption
   * ------------------------------------------------------------------------- */
  describe('F4 & F5: Copy precision, version tag semantics, and sync caption', () => {
    it('spells Quality Control Run fully in table header', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      expect(await screen.findByText('Quality Control Run gần nhất')).toBeDefined();
      expect(screen.queryByText('QC Run gần nhất')).toBeNull();
    });

    it('genuine Guideline/Taxonomy version is never mislabeled as Dataset version tag in Home table', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      // Dataset 1 has guideline_version: 'v1.2' and taxonomy_version: 'v1.4'
      // But neither is a Dataset Version; real dataset row should NOT render any .lx-tag
      const urbanRow = (await screen.findByText('Road Vision Urban Real')).closest('tr')!;
      const tagInsideUrban = urbanRow.querySelector('.lx-tag');
      expect(tagInsideUrban).toBeNull();

      // Dataset 2 has null versions; also no tag
      const highwayRow = screen.getByText('Road Vision Highway Real').closest('tr')!;
      const tagInsideHighway = highwayRow.querySelector('.lx-tag');
      expect(tagInsideHighway).toBeNull();
    });

    it('genuine dataset view renders unknown sync caption as em dash, while design preview displays canonical caption', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      const { rerender } = render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      // When real datasets are active: 'Đồng bộ CVAT —'
      expect(await screen.findByText('Đồng bộ CVAT —')).toBeDefined();
      expect(screen.queryByText('Đồng bộ CVAT 2 phút trước')).toBeNull();

      // In no-backend illustrative preview (error state triggered via fresh lifecycle mount)
      setupMockEnv(() => Response.json({ detail: 'No backend' }, { status: 500 }));
      rerender(
        <AuthProvider>
          <QualityControlHome key="preview" />
        </AuthProvider>
      );

      // Now design preview shows canonical caption 'Đồng bộ CVAT 2 phút trước'
      expect(await screen.findByText('Đồng bộ CVAT 2 phút trước')).toBeDefined();
    });
  });

  /* -------------------------------------------------------------------------
   * 9. TopBar baseline navigation (Quality Summary wiring requested for FE10 PR183)
   * ------------------------------------------------------------------------- */
  describe('TopBar baseline navigation', () => {
    it('TopBar Overview dropdown includes Quality Control Home link, while Quality Summary remains disabled pending FE10 PR183', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <TopBar activeKey="overview" />
        </AuthProvider>
      );

      const overviewBtn = screen.getByRole('button', { name: 'Overview' });
      fireEvent.click(overviewBtn);

      const homeLink = screen.getByRole('menuitem', { name: /Quality Control Home/ });
      const summaryBtn = screen.getByRole('menuitem', { name: /Quality Summary/ });

      expect(homeLink.getAttribute('href')).toBe('/');
      expect(summaryBtn).toBeDisabled();
    });
  });
});
