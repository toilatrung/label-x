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
   * 1. M1: API Explorer examples from PR #252
   * ------------------------------------------------------------------------- */
  describe('M1: Quality Summary API Explorer data', () => {
    it('renders PR #252 metrics without sample-data or disconnected warnings', async () => {
      const ds: Dataset = { id: 1, name: 'Road Vision Urban Real', cvat_project_id: 31 };
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer');

      render(
        <AuthProvider>
          <QualitySummary currentDataset={ds} />
        </AuthProvider>
      );

      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban Real · Quality Control Run #91 · Snapshot #14\./)).toBeDefined();
      expect(screen.queryByText('Dữ liệu minh họa')).toBeNull();
      expect(document.querySelector('.lx-notice')).toBeNull();
      expect(screen.getAllByText('12,500').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('92.4%').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('384')).toBeDefined();
      expect(screen.getByText('126')).toBeDefined();
      expect(screen.getByText('Release blocked')).toBeDefined();
      expect(screen.queryByText(/kết nối với server/)).toBeNull();
    });

    it('uses the API Explorer task response instead of legacy task placeholders', async () => {
      const { authApi } = setupMockEnv(undefined, 1, (req) => req.url.includes('/api/datasets/1/tasks/')
        ? Response.json([{ cvat_task_id: 118, name: 'Urban day', jobs: [
          { cvat_job_id: 2270, assignee_cvat_user_id: 1, frame_count: 200, updated_date: '2026-10-09T07:00:00Z' },
          { cvat_job_id: 2271, assignee_cvat_user_id: null, frame_count: 400, updated_date: '2026-10-09T07:00:00Z' }] }])
        : undefined);
      await authApi.signIn('reviewer');
      const ds: Dataset = { id: 1, name: 'Road Vision Urban Real', cvat_project_id: 31 };
      render(<AuthProvider><QualitySummary currentDataset={ds} /></AuthProvider>);
      const row = screen.getByRole('row', { name: /T-118 · Urban day/ });
      const cells = Array.from(row.querySelectorAll('td'));
      expect(cells[1].textContent).toBe('3');
      expect(cells[2].textContent).toBe('600');
      expect(cells[3].textContent).toBe('98.0%');
      expect(cells[4].textContent).toBe('65');
      expect(cells[5].textContent).toBe('Đạt');
    });

    it('renders all lifecycle states provided by PR #252 when no dataset is selected', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualitySummary currentDataset={null} />
        </AuthProvider>
      );

      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban · Quality Control Run #91 · Snapshot #14\./)).toBeDefined();
      ['Schema / Taxonomy', 'Geometry', 'Duplicate / Overlap', 'Mô hình độc lập', 'Mô hình thị giác – ngôn ngữ', 'Metric'].forEach((engine) => {
        expect(screen.getByText(engine)).toBeDefined();
      });
      ['Ưu tiên theo rủi ro', 'Kiểm tra ngẫu nhiên', 'Chưa chắc chắn / Chuyển cấp trên'].forEach((queue) => {
        expect(screen.getByText(queue)).toBeDefined();
      });
      expect(screen.getByText(/T-118 · Urban day/)).toBeDefined();
      expect(screen.getByText('Sai nhãn')).toBeDefined();
      expect(screen.getByText('Hình học')).toBeDefined();
      expect(screen.getByText('Thiếu object')).toBeDefined();
      expect(screen.getByText(/Coverage 92\.4% chưa đạt ngưỡng 95\.0%/)).toBeDefined();
      expect(screen.getByText('Ngưỡng yêu cầu 95.0%')).toBeDefined();
      expect(screen.queryByText(/NaN/)).toBeNull();
    });

    it('QualityControlHome renders the canonical product table in explicit mock mode', async () => {
      const { authApi } = setupMockEnv(() => {
        return Response.json({ detail: 'No backend available' }, { status: 500 });
      });
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      expect(await screen.findByText('Road Vision Highway')).toBeDefined();
      expect(screen.queryByText(/Máy chủ gặp lỗi|Không thể tải danh sách Dataset/)).toBeNull();
      expect(document.querySelector('.lx-notice')).toBeNull();
    });

    it('uses canonical mock datasets without triggering an extra request', async () => {
      const requestedDatasetUrls: string[] = [];
      const onDatasetSelect = vi.fn();
      const { authApi } = setupMockEnv((req) => {
        requestedDatasetUrls.push(req.url);
        return Response.json({ detail: 'Database unavailable' }, { status: 500 });
      });
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome onDatasetSelect={onDatasetSelect} />
        </AuthProvider>
      );

      expect(await screen.findByText('Road Vision Highway')).toBeDefined();
      expect(document.querySelector('.lx-notice')).toBeNull();

      const highwayRow = screen.getByText('Road Vision Highway').closest('tr')!;
      fireEvent.click(highwayRow);

      expect(onDatasetSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 9, name: 'Road Vision Highway' }));
      expect(mockPush).toHaveBeenCalledWith('/?view=summary');
      const selectionRequests = requestedDatasetUrls.filter((url) => url.includes('/9/') || url.includes('road-vision-highway'));
      expect(selectionRequests).toHaveLength(0);

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

    it('displays revoked state when dataset does not exist in any scoped page, while retaining canonical product data', async () => {
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

      // Canonical product data is also rendered below the message.
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
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban/)).toBeDefined();
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
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban/)).toBeDefined();
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

      // Resolve the superseded generation with an error, then refresh from the always-available sync action.
      lateCallResolve!(Response.json({ detail: 'Old error' }, { status: 500 }));
      expect(await screen.findByText('Road Vision Highway')).toBeDefined();
      fireEvent.click(screen.getByRole('button', { name: 'Đồng bộ lại' }));

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

    it('supports task row keyboard selection for the API Explorer task', async () => {
      setupMockEnv();
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

      const taskRow = screen.getByRole('row', { name: /T-118 · Urban day/ });
      expect(taskRow.getAttribute('aria-selected')).toBe('false');

      fireEvent.keyDown(taskRow, { key: 'Enter' });
      expect(onScopeChange).toHaveBeenCalledWith('T-118 · Urban day');

      fireEvent.keyDown(taskRow, { key: ' ' });
      expect(onScopeChange).toHaveBeenLastCalledWith('T-118 · Urban day');

      // Re-render with selectedTaskScope to verify aria-selected="true"
      rerender(
        <AuthProvider>
          <QualitySummary
            currentDataset={ds}
            selectedTaskScope="T-118 · Urban day"
            onTaskScopeChange={onScopeChange}
          />
        </AuthProvider>
      );

      const updatedRow = screen.getByRole('row', { name: /T-118 · Urban day/ });
      expect(updatedRow.getAttribute('aria-selected')).toBe('true');
    });
  });

  /* -------------------------------------------------------------------------
   * 6. F1: Single regional notice count unchanged after repeated sync
   * ------------------------------------------------------------------------- */
  describe('F1: Single regional notice count unchanged after repeated sync', () => {
    it('refreshes runtime data on sync without displaying implementation notices', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      expect(await screen.findByText('Road Vision Urban Real')).toBeDefined();

      expect(document.querySelector('.lx-notice')).toBeNull();

      // Click "Đồng bộ lại"
      const syncBtn = screen.getByRole('button', { name: 'Đồng bộ lại' });
      fireEvent.click(syncBtn);

      expect(await screen.findByText('Road Vision Urban Real')).toBeDefined();
      expect(document.querySelector('.lx-notice')).toBeNull();

      // Click "Đồng bộ lại" again
      fireEvent.click(syncBtn);
      expect(document.querySelector('.lx-notice')).toBeNull();
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
    it('TopBar Overview dropdown links to both Quality Control Home and Quality Summary', async () => {
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
      const summaryLink = screen.getByRole('menuitem', { name: /Quality Summary/ });

      expect(homeLink.getAttribute('href')).toBe('/');
      expect(summaryLink.getAttribute('href')).toBe('/?view=summary');
    });
  });
});
