import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QualityControlHome } from '@/components/overview/QualityControlHome';
import { QualitySummary } from '@/components/overview/QualitySummary';
import { TopBar } from '@/components/layout/TopBar';
import { ContextBar } from '@/components/layout/ContextBar';
import { AppShell } from '@/components/layout/AppShell';
import Home from '@/app/page';
import { AuthProvider, useAuth } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';
import type { Dataset, CvatTask } from '@/lib/snapshots/api';
import type { Run } from '@/lib/execution/api';
import { NOT_CONNECTED_MESSAGE } from '@/components/ui/NotConnectedNotice';

const mockPush = vi.fn();
let currentSearchParam = '';

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(currentSearchParam),
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
}));

describe('FE-01: Quality Control Home and Quality Summary (Revision 2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentSearchParam = '';
  });

  const mockDatasetsPage1: Dataset[] = [
    {
      id: 1,
      name: 'Road Vision Urban',
      cvat_project_id: 31,
      taxonomy_version: 'v1.4',
      guideline_version: 'v1.2',
    },
    {
      id: 2,
      name: 'Road Vision Highway',
      cvat_project_id: 34,
      taxonomy_version: 'v1.1',
      guideline_version: 'v1.0',
    },
  ];

  const mockDatasetsPage2: Dataset[] = [
    {
      id: 3,
      name: 'Parking Lot Detection',
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

  describe('Revision 2: Honest rendering with em dash (—) and no sample badges', () => {
    it('renders em dash for unknown fields in QualitySummary without sample badges or fake identifiers', async () => {
      const ds: Dataset = { id: 1, name: 'Road Vision Urban', cvat_project_id: 31 };
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer');

      render(
        <AuthProvider>
          <QualitySummary currentDataset={ds} />
        </AuthProvider>
      );

      // Verify header uses real dataset name and em dash for QC Run
      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban · Quality Control Run: —\./)).toBeDefined();

      // Verify no sample badges or illustrative values exist in rendered UI
      expect(screen.queryByText('Dữ liệu minh họa')).toBeNull();
      expect(screen.queryByText(/QC-091/)).toBeNull();
      expect(screen.queryByText(/T-118/)).toBeNull();
      expect(screen.queryByText(/Release blocked/)).toBeNull();

      // Neutral Quality Gate callout
      expect(screen.getByText('Quality Gate: —')).toBeDefined();
      expect(screen.getByText(/Chưa có dữ liệu đánh giá Quality Gate cho Dataset này/)).toBeDefined();

      // 4 Metric cards all render em dash
      const metricValues = screen.getAllByText('—');
      expect(metricValues.length).toBeGreaterThanOrEqual(10);

      // Task table renders honest no-data row
      expect(await screen.findByText('Chưa có dữ liệu Task cho Dataset này')).toBeDefined();

      // Disconnected regions each have NotConnectedNotice with exact base message and no duplicates
      const notices = screen.getAllByText(new RegExp(NOT_CONNECTED_MESSAGE));
      expect(notices.length).toBeGreaterThanOrEqual(4);
      for (const notice of notices) {
        // Assert exactly one occurrence of base message per notice
        const text = notice.textContent ?? '';
        const matches = text.match(new RegExp(NOT_CONNECTED_MESSAGE, 'g'));
        expect(matches?.length).toBe(1);
      }
    });

    it('renders em dash for unknown fields in Home table and has no sample badge on sync', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      expect(await screen.findByText('Road Vision Urban')).toBeDefined();

      // Sync button without fake "2 phút trước" or sample badge
      expect(screen.queryByText(/2 phút trước/)).toBeNull();
      expect(screen.queryByText('Dữ liệu minh họa')).toBeNull();

      // Unknown fields in Home table render em dash
      const emDashes = screen.getAllByText('—');
      expect(emDashes.length).toBeGreaterThanOrEqual(6);

      // Click sync shows notice with exactly one base message
      expect(screen.getByText('Đồng bộ CVAT —')).toBeDefined();
      const syncBtn = screen.getByRole('button', { name: 'Đồng bộ lại' });
      fireEvent.click(syncBtn);
      const syncNotice = await screen.findByText(/Đồng bộ danh sách Dataset từ CVAT qua Webhook\/Sync worker chưa được kích hoạt/);
      expect(syncNotice).toBeDefined();
      const occurrences = (syncNotice.textContent ?? '').match(new RegExp(NOT_CONNECTED_MESSAGE, 'g'));
      expect(occurrences?.length).toBe(1);
    });
  });

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

      // Sign in as reviewer with dataset_id: 3 (which is on page 2!)
      await authApi.signIn('reviewer');

      render(
        <AuthProvider>
          <Home />
        </AuthProvider>
      );

      // Verify Parking Lot Detection (ID 3 from page 2) is resolved!
      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Parking Lot Detection/)).toBeDefined();
    });

    it('displays revoked state when dataset does not exist in any scoped page', async () => {
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
    });

    it('displays distinct error and working retry button on transient API rejection during dataset resolution', async () => {
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
    });
  });

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
      expect(screen.queryByText('Chưa chọn Dataset')).toBeNull();

      // Resolve API
      resolvePromise!(Response.json({ next: null, previous: null, results: mockDatasetsPage1 }));

      // Now Quality Summary renders
      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban/)).toBeDefined();
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
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban/)).toBeDefined();

      // Switch to admin who has dataset_id: null (no scoped dataset grant)
      await authApi.signIn('admin');
      unmount();

      render(
        <AuthProvider>
          <Home />
        </AuthProvider>
      );

      // User has no dataset: immediately shows landing state
      expect(await screen.findByText('Chưa chọn Dataset')).toBeDefined();
      expect(screen.queryByText(/Tình trạng kiểm tra của Road Vision Urban/)).toBeNull();
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
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban/)).toBeDefined();

      // Trigger switch to admin (who has dataset_id: null)
      const switchBtn = screen.getByRole('button', { name: 'Chuyển sang admin' });
      fireEvent.click(switchBtn);

      // Immediately invalidates dataset and transitions to landing state
      expect(await screen.findByText('Chưa chọn Dataset')).toBeDefined();
      expect(screen.queryByText(/Tình trạng kiểm tra của Road Vision Urban/)).toBeNull();
    });
  });

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
          return Response.json({ next: 'http://localhost/api/datasets/?cursor=p2', previous: null, results: mockDatasetsPage1 });
        }
        return Response.json({ next: null, previous: null, results: mockDatasetsPage2 });
      });

      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      // User types query while page 1 is still loading!
      const searchInput = screen.getByRole('searchbox', { name: 'Tìm dataset' });
      fireEvent.change(searchInput, { target: { value: 'Parking' } });

      // Now page 1 gate opens
      page1Resolve!();

      // Search automatically scans page 2 and finds Parking Lot Detection!
      expect(await screen.findByText('Parking Lot Detection')).toBeDefined();
      expect(screen.queryByText(/Không tìm thấy Dataset phù hợp/)).toBeNull();
    });

    it('handles delayed page-2 responses during search scan without self-cancelling', async () => {
      let page2Resolve: () => void;
      const page2Gate = new Promise<void>((resolve) => {
        page2Resolve = resolve;
      });

      const { authApi } = setupMockEnv(async (req) => {
        const cursor = new URL(req.url).searchParams.get('cursor');
        if (!cursor) {
          return Response.json({
            next: 'http://localhost/api/datasets/?cursor=delayed_p2',
            previous: null,
            results: mockDatasetsPage1,
          });
        }
        await page2Gate;
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

      expect(await screen.findByText('Road Vision Urban')).toBeDefined();

      // User searches for item that is on page 2
      const searchInput = screen.getByRole('searchbox', { name: 'Tìm dataset' });
      fireEvent.change(searchInput, { target: { value: 'Parking' } });

      // Search scanning indicator is active
      expect(await screen.findByText('Đang tìm kiếm thêm trên các trang tiếp theo…')).toBeDefined();

      // Resolve delayed page 2
      page2Resolve!();

      // Discovers the item and finishes scan
      expect(await screen.findByText('Parking Lot Detection')).toBeDefined();
      expect(screen.queryByText('Đang tìm kiếm thêm trên các trang tiếp theo…')).toBeNull();
    });

    it('guards against repeated pagination cursors in Home and recovers via handleRetryPagination', async () => {
      let loopCount = 0;
      const { authApi } = setupMockEnv((req) => {
        const cursor = new URL(req.url).searchParams.get('cursor');
        if (!cursor) {
          // Page 1 returns next cursor = "loop_cursor"
          return Response.json({ next: 'http://localhost/api/datasets/?cursor=loop_cursor', previous: null, results: mockDatasetsPage1 });
        }
        loopCount++;
        if (loopCount <= 2) {
          // Page 2 returns the SAME cursor again (infinite loop!)
          return Response.json({ next: 'http://localhost/api/datasets/?cursor=loop_cursor', previous: null, results: mockDatasetsPage2 });
        }
        return Response.json({ next: null, previous: null, results: mockDatasetsPage2 });
      });

      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      expect(await screen.findByText('Road Vision Urban')).toBeDefined();

      // Trigger search to scan pages
      const searchInput = screen.getByRole('searchbox', { name: 'Tìm dataset' });
      fireEvent.change(searchInput, { target: { value: 'Unknown' } });

      // Detects loop and surfaces error without infinite hanging
      expect(await screen.findByText(/Phát hiện vòng lặp phân trang từ server/)).toBeDefined();

      // Click "Thử lại tải trang" which triggers handleRetryPagination
      const retryBtn = screen.getByRole('button', { name: 'Thử lại tải trang' });
      fireEvent.click(retryBtn);

      await waitFor(() => {
        expect(screen.queryByText(/Phát hiện vòng lặp phân trang từ server/)).toBeNull();
      });
    });

    it('guards against repeated pagination cursors during page.tsx dataset resolution', async () => {
      currentSearchParam = 'view=summary';
      const { authApi } = setupMockEnv((req) => {
        const cursor = new URL(req.url).searchParams.get('cursor');
        if (!cursor) {
          return Response.json({ next: 'http://localhost/api/datasets/?cursor=loop_cursor', previous: null, results: mockDatasetsPage1 });
        }
        return Response.json({ next: 'http://localhost/api/datasets/?cursor=loop_cursor', previous: null, results: [] });
      }, 99);

      // User has dataset_id: 99 which does not exist on page 1
      await authApi.signIn('reviewer');

      render(
        <AuthProvider>
          <Home />
        </AuthProvider>
      );

      // Detects loop and surfaces recoverable error
      expect(await screen.findByRole('heading', { level: 2, name: 'Lỗi kiểm tra quyền Dataset' })).toBeDefined();
      expect(screen.getByText(/Phát hiện vòng lặp phân trang từ server/)).toBeDefined();
    });

    it('discards late responses from previous generations after retry', async () => {
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

      // Resolve first call with fake error
      lateCallResolve!(Response.json({ detail: 'Old error' }, { status: 500 }));

      // Click retry in Home
      const retryBtn = await screen.findByRole('button', { name: 'Thử lại' });
      fireEvent.click(retryBtn);

      // Current generation loads cleanly
      expect(await screen.findByText('Road Vision Urban')).toBeDefined();
    });
  });

  describe('Keyboard navigation and actions', () => {
    it('separates row activation from child button clicks and key events in Home table', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <QualityControlHome />
        </AuthProvider>
      );

      expect(await screen.findByText('Road Vision Urban')).toBeDefined();

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
  });

  describe('Revision 3: Interactive ContextBar pickers & canonical TopBar', () => {
    it('renders exact canonical labels without colons, real data or em dash, and responds to clicks and Escape', async () => {
      const mockRuns: Run[] = [
        {
          id: 10,
          snapshot_id: 5,
          config_version_id: 1,
          seed: 42,
          status: 'completed',
          is_final: true,
          engines: [],
          created_by: 1,
          created_at: '2026-10-10T00:00:00Z',
        },
      ];
      const mockTasks: CvatTask[] = [
        {
          cvat_task_id: 101,
          name: 'Urban Segment 1',
          jobs: [
            {
              cvat_job_id: 201,
              assignee_cvat_user_id: 104,
              updated_date: '2026-10-10T00:00:00Z',
            },
          ],
        },
      ];

      const { authApi } = setupMockEnv(
        undefined,
        undefined,
        (req) => {
          const url = new URL(req.url);
          if (url.pathname === '/api/runs/') {
            return Response.json({ next: null, previous: null, results: mockRuns });
          }
          if (url.pathname.includes('/tasks/')) {
            return Response.json(mockTasks);
          }
          return undefined;
        }
      );

      // Sign in as qa_lead who has permission to view runs and tasks
      await authApi.signIn('qalead');

      const onScopeChange = vi.fn();
      const onRunSelect = vi.fn();

      render(
        <AuthProvider>
          <ContextBar
            datasetName="Road Vision Urban"
            datasetIdOverride={1}
            isOverview={true}
            onScopeChange={onScopeChange}
            onRunSelect={onRunSelect}
          />
        </AuthProvider>
      );

      // Canonical chip keys have NO colons in Overview
      expect(screen.getByText('Dataset')).toBeDefined();
      expect(screen.getByText('Quality Control Run')).toBeDefined();
      expect(screen.getByText('Snapshot')).toBeDefined();
      expect(screen.getByText('Phạm vi')).toBeDefined();
      expect(screen.getByText('Guideline')).toBeDefined();
      expect(screen.getByText('Taxonomy')).toBeDefined();

      // No seventh Vai trò chip in Overview
      expect(screen.queryByText('Vai trò')).toBeNull();

      // Missing values render em dash
      expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(3);

      // 1. Dataset chip opens canonical picker and responds to Escape
      const dsChip = screen.getByRole('button', { name: /Dataset Road Vision Urban/ });
      fireEvent.click(dsChip);
      expect(screen.getByText('Dataset và Version')).toBeDefined();

      // Wait for dataset items to load in menu
      expect(await screen.findByText('Road Vision Highway')).toBeDefined();

      fireEvent.keyDown(document, { key: 'Escape' });
      await waitFor(() => {
        expect(screen.queryByText('Dataset và Version')).toBeNull();
      });

      // 2. Quality Control Run chip opens canonical run picker
      const runChip = screen.getByRole('button', { name: /Quality Control Run/ });
      fireEvent.click(runChip);
      const runItem = await screen.findByRole('menuitem', { name: /#\s*10\s*COMPLETED/ });
      expect(runItem).toBeDefined();

      // 3. Snapshot chip is a canonical static pill; clicking shows informative callout with Chỉ đọc badge
      const snapChip = screen.getByRole('button', { name: /Snapshot/ });
      fireEvent.click(snapChip);
      expect(await screen.findByText(/Chưa chọn Snapshot cho phiên làm việc hiện tại/)).toBeDefined();
      expect(screen.getByText('Chỉ đọc')).toBeDefined();

      // 4. Scope chip opens canonical task picker and allows selecting "Toàn dataset" or individual task
      const scopeChip = screen.getByRole('button', { name: /Phạm vi/ });
      fireEvent.click(scopeChip);
      const allDsBtn = screen.getByRole('menuitem', { name: /Toàn dataset/ });
      fireEvent.click(allDsBtn);
      expect(onScopeChange).toHaveBeenCalledWith('Toàn dataset');

      // Click scope chip again and select task #101
      fireEvent.click(scopeChip);
      const taskBtn = await screen.findByRole('menuitem', { name: /Task #101 · Urban Segment 1/ });
      fireEvent.click(taskBtn);
      expect(onScopeChange).toHaveBeenCalledWith('Task #101 · Urban Segment 1');

      // 5. Guideline & Taxonomy static pills show informative notices on click
      const guidelineChip = screen.getByRole('button', { name: /Guideline/ });
      fireEvent.click(guidelineChip);
      expect(await screen.findByText(/Dataset hiện tại chưa có thông tin Guideline/)).toBeDefined();

      const taxonomyChip = screen.getByRole('button', { name: /Taxonomy/ });
      fireEvent.click(taxonomyChip);
      expect(await screen.findByText(/Dataset hiện tại chưa có thông tin Taxonomy/)).toBeDefined();
    });

    it('supports ArrowDown/ArrowUp/Home/End keyboard navigation within open menus', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer');

      render(
        <AuthProvider>
          <ContextBar
            datasetName="Road Vision Urban"
            datasetIdOverride={1}
            isOverview={true}
          />
        </AuthProvider>
      );

      const dsChip = screen.getByRole('button', { name: /Dataset Road Vision Urban/ });
      fireEvent.click(dsChip);

      // Wait for dataset items to load
      const menuItems = await screen.findAllByRole('menuitem');
      expect(menuItems.length).toBe(2);

      // ArrowDown moves focus to next item
      menuItems[0].focus();
      fireEvent.keyDown(menuItems[0], { key: 'ArrowDown' });
      expect(document.activeElement).toBe(menuItems[1]);

      // ArrowUp moves focus back to previous item
      fireEvent.keyDown(menuItems[1], { key: 'ArrowUp' });
      expect(document.activeElement).toBe(menuItems[0]);

      // End moves focus to last item
      fireEvent.keyDown(menuItems[0], { key: 'End' });
      expect(document.activeElement).toBe(menuItems[1]);

      // Home moves focus to first item
      fireEvent.keyDown(menuItems[1], { key: 'Home' });
      expect(document.activeElement).toBe(menuItems[0]);

      // Escape closes menu and returns focus to dsChip
      fireEvent.keyDown(menuItems[0], { key: 'Escape' });
      expect(document.activeElement).toBe(dsChip);
    });

    it('preserves ContextBar row click during realistic pointerdown -> mousedown -> click sequences', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');

      const onDatasetSelect = vi.fn();

      render(
        <AuthProvider>
          <AppShell
            activeKey="overview"
            activeItem="home"
            context={{
              datasetName: 'Road Vision Urban',
              datasetIdOverride: 1,
              isOverview: true,
              onDatasetSelect,
            }}
          >
            <div>App Content</div>
          </AppShell>
        </AuthProvider>
      );

      const dsChip = screen.getByRole('button', { name: /Dataset Road Vision Urban/ });
      fireEvent.click(dsChip);

      const menuItems = await screen.findAllByRole('menuitem');
      const secondItem = menuItems[1]; // Road Vision Highway

      // Dispatch realistic pointer sequence: pointerdown -> mousedown -> mouseup -> click
      fireEvent.pointerDown(secondItem);
      fireEvent.mouseDown(secondItem);
      fireEvent.mouseUp(secondItem);
      fireEvent.click(secondItem);

      expect(onDatasetSelect).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Road Vision Highway' })
      );
    });

    it('displays selected run in QualitySummary headline and supports clicking task row to scope', async () => {
      const ds: Dataset = { id: 1, name: 'Road Vision Urban', cvat_project_id: 31 };
      const selectedRun: Run = {
        id: 42,
        snapshot_id: 12,
        config_version_id: 1,
        seed: 42,
        status: 'completed',
        is_final: true,
        engines: [],
        created_by: 1,
        created_at: '2026-10-10T12:00:00Z',
      };
      const mockTasks: CvatTask[] = [
        {
          cvat_task_id: 101,
          name: 'Urban Segment 1',
          jobs: [
            {
              cvat_job_id: 201,
              assignee_cvat_user_id: 104,
              updated_date: '2026-10-10T00:00:00Z',
            },
          ],
        },
      ];

      const { authApi } = setupMockEnv(
        undefined,
        undefined,
        (req) => {
          const url = new URL(req.url);
          if (url.pathname.includes('/tasks/')) {
            return Response.json(mockTasks);
          }
          return undefined;
        }
      );

      await authApi.signIn('reviewer');

      const onTaskScopeChange = vi.fn();

      render(
        <AuthProvider>
          <QualitySummary
            currentDataset={ds}
            selectedRun={selectedRun}
            onTaskScopeChange={onTaskScopeChange}
          />
        </AuthProvider>
      );

      // Verify headline contains real run ID and status
      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();
      expect(screen.getByText(/Tình trạng kiểm tra của Road Vision Urban · Quality Control Run: #42 · COMPLETED\./)).toBeDefined();

      // Verify real task is loaded in Theo Task table
      const taskElement = await screen.findByText(/Urban Segment 1/);
      expect(taskElement).toBeDefined();

      // Click task row to set scope
      const taskRow = taskElement.closest('tr')!;
      fireEvent.click(taskRow);
      expect(onTaskScopeChange).toHaveBeenCalledWith('Task #101 · Urban Segment 1');
    });

    it('renders em dash for unresolved dataset name in Overview ContextBar without inventing identifiers', async () => {
      const authApi = installMockAuthApi();
      await authApi.signIn('reviewer');

      render(
        <AuthProvider>
          <ContextBar
            datasetIdOverride={1}
            isOverview={true}
          />
        </AuthProvider>
      );

      // Must display '—', NOT 'Dataset #1'
      expect(screen.queryByText(/Dataset #1/)).toBeNull();
      const dsChip = screen.getByRole('button', { name: /Dataset —/ });
      expect(dsChip).toBeDefined();
    });

    it('preserves shared static baseline ContextBar when isOverview is not passed', async () => {
      const authApi = installMockAuthApi();
      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <ContextBar />
        </AuthProvider>
      );

      // Baseline chips with colons
      expect(screen.getByText('Dataset:')).toBeDefined();
      expect(screen.getByText('Quality Control Run:')).toBeDefined();
      expect(screen.getByText('Snapshot:')).toBeDefined();
      expect(screen.getByText('Guideline:')).toBeDefined();
      expect(screen.getByText('Taxonomy:')).toBeDefined();
      expect(screen.getByText('Vai trò:')).toBeDefined();
      expect(await screen.findByText('Super Admin')).toBeDefined();
    });

    it('Overview dropdown correctly switches between Home and Summary with active styling', async () => {
      const authApi = installMockAuthApi();
      await authApi.signIn('admin');

      const { rerender } = render(
        <AuthProvider>
          <TopBar activeKey="overview" activeItem="home" />
        </AuthProvider>
      );

      const overviewBtn = screen.getByRole('button', { name: 'Overview' });
      fireEvent.click(overviewBtn);

      const homeLink = screen.getByRole('menuitem', { name: /Quality Control Home/ });
      const summaryLink = screen.getByRole('menuitem', { name: /Quality Summary/ });

      expect(homeLink.getAttribute('href')).toBe('/');
      expect(summaryLink.getAttribute('href')).toBe('/?view=summary');
      expect(homeLink.classList.contains('is-active')).toBe(true);
      expect(summaryLink.classList.contains('is-active')).toBe(false);

      // Re-render with activeItem='summary'
      rerender(
        <AuthProvider>
          <TopBar activeKey="overview" activeItem="summary" />
        </AuthProvider>
      );

      expect(homeLink.classList.contains('is-active')).toBe(false);
      expect(summaryLink.classList.contains('is-active')).toBe(true);
    });

    it('supports task row keyboard selection with Enter and Space, and retry on task error', async () => {
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
      const ds: Dataset = { id: 1, name: 'Road Vision Urban', cvat_project_id: 31 };

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
      expect(await screen.findByText(/Máy chủ gặp lỗi/)).toBeDefined();
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

    it('renders neutral unfilled tracks without fake percentages or numbers', async () => {
      const { authApi } = setupMockEnv(undefined, 1);
      await authApi.signIn('admin');
      const ds: Dataset = { id: 1, name: 'Road Vision Urban', cvat_project_id: 31 };

      render(
        <AuthProvider>
          <QualitySummary currentDataset={ds} />
        </AuthProvider>
      );

      // Coverage progress track has 0% width and honest aria-label
      const coverageTrack = await screen.findByRole('img', { name: 'Coverage: —' });
      expect(coverageTrack).toBeDefined();
      const coverageBar = coverageTrack.querySelector('i');
      expect(coverageBar?.style.width).toBe('0%');

      // Review volume tracks have 0% width
      const riskTrack = screen.getByRole('img', { name: 'Ưu tiên theo rủi ro: —' });
      expect(riskTrack.querySelector('i')?.style.width).toBe('0%');

      const randomTrack = screen.getByRole('img', { name: 'Kiểm tra ngẫu nhiên: —' });
      expect(randomTrack.querySelector('i')?.style.width).toBe('0%');

      const escalateTrack = screen.getByRole('img', { name: 'Chưa chắc chắn / Chuyển cấp trên: —' });
      expect(escalateTrack.querySelector('i')?.style.width).toBe('0%');
    });

    it('clears snapshot lock icon immediately when snapshot changes or is unselected', async () => {
      const { authApi } = setupMockEnv(undefined, undefined, (req) => {
        if (req.url.includes('/api/snapshots/99/')) {
          return Response.json({ id: 99, status: 'locked', dataset_id: 1 });
        }
        return undefined;
      });

      await authApi.signIn('admin');

      const runWithSnap: Run = {
        id: 10,
        snapshot_id: 99,
        config_version_id: 1,
        seed: 42,
        status: 'completed',
        is_final: true,
        engines: [],
        created_by: 1,
        created_at: '2026-10-10T00:00:00Z',
      };
      const runWithoutSnap: Run | null = null;

      const { rerender } = render(
        <AuthProvider>
          <ContextBar
            datasetIdOverride={1}
            isOverview={true}
            selectedRun={runWithSnap}
          />
        </AuthProvider>
      );

      // Locked snapshot should display lock icon
      expect(await screen.findByRole('img', { name: 'Đã khoá' })).toBeDefined();

      // Switch run to one without snapshot: lock icon must clear immediately
      rerender(
        <AuthProvider>
          <ContextBar
            datasetIdOverride={1}
            isOverview={true}
            selectedRun={runWithoutSnap}
          />
        </AuthProvider>
      );

      expect(screen.queryByRole('img', { name: 'Đã khoá' })).toBeNull();
    });
  });

  describe('Follow-up 17: Picker failure, error owner guards & state ownership', () => {
    it('shows visible error and retry button on first Dataset 500, preserves error on reopen, and displays empty state after retry success without refetch loop', async () => {
      let dsCalls = 0;
      let shouldFailDs = true;
      const { authApi } = setupMockEnv(undefined, 1, (req) => {
        if (req.url.includes('/api/datasets/')) {
          dsCalls++;
          if (shouldFailDs) {
            return new Response(JSON.stringify({ detail: 'Internal server error' }), {
              status: 500,
              headers: { 'Content-Type': 'application/json' },
            });
          }
          return Response.json({ next: null, previous: null, results: [] });
        }
        return undefined;
      });

      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <ContextBar datasetIdOverride={1} isOverview={true} />
        </AuthProvider>
      );

      // Open dataset picker
      const dsChip = screen.getByRole('button', { name: /Dataset/ });
      fireEvent.click(dsChip);

      // Verify visible error appears with retry button (does NOT render empty state)
      expect(await screen.findByText(/Máy chủ gặp lỗi/)).toBeDefined();
      const retryBtn = screen.getByRole('button', { name: 'Thử lại' });
      expect(retryBtn).toBeDefined();
      expect(screen.queryByText('Chưa có Dataset nào')).toBeNull();
      const initialDsCalls = dsCalls;

      // Close menu with Escape
      fireEvent.keyDown(dsChip, { key: 'Escape' });
      expect(screen.queryByRole('menu')).toBeNull();

      // Re-open menu: error and retry must still be visible without automatic refetch loop
      fireEvent.click(dsChip);
      expect(screen.getByText(/Máy chủ gặp lỗi/)).toBeDefined();
      expect(dsCalls).toBe(initialDsCalls);

      // Click retry successfully with empty list
      shouldFailDs = false;
      fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));

      // Empty state appears
      expect(await screen.findByText('Chưa có Dataset nào')).toBeDefined();
      const afterRetryCalls = dsCalls;

      // Close and reopen: stays empty, no extra request loop
      fireEvent.keyDown(dsChip, { key: 'Escape' });
      fireEvent.click(dsChip);
      expect(screen.getByText('Chưa có Dataset nào')).toBeDefined();
      expect(dsCalls).toBe(afterRetryCalls);
    });

    it('shows visible error and retry button on first Run 403, and loads runs on retry success', async () => {
      let runCalls = 0;
      let shouldFailRun = true;
      const { authApi } = setupMockEnv(undefined, undefined, (req) => {
        if (req.url.includes('/api/runs/')) {
          runCalls++;
          if (shouldFailRun) {
            return new Response(JSON.stringify({ detail: 'Forbidden' }), {
              status: 403,
              headers: { 'Content-Type': 'application/json' },
            });
          }
          return Response.json({
            next: null,
            previous: null,
            results: [
              {
                id: 45,
                status: 'completed',
                created_at: '2026-10-10T00:00:00Z',
                created_by: 1,
                engines: [],
                is_final: true,
                seed: 1,
                snapshot_id: null,
                config_version_id: 1,
              },
            ],
          });
        }
        return undefined;
      });

      await authApi.signIn('qalead');

      function RunHarness() {
        const { session } = useAuth();
        if (!session) return <div>Đang khởi tạo phiên...</div>;
        return <ContextBar datasetIdOverride={1} isOverview={true} />;
      }

      render(
        <AuthProvider>
          <RunHarness />
        </AuthProvider>
      );

      // Open run picker once session is ready
      const runChip = await screen.findByRole('button', { name: /Quality Control Run/ });
      fireEvent.click(runChip);

      // Error appears with retry button
      expect(await screen.findByText(/Bạn không có quyền|Forbidden/)).toBeDefined();
      const retryBtn = screen.getByRole('button', { name: 'Thử lại' });
      expect(retryBtn).toBeDefined();
      const initialRunCalls = runCalls;

      // Close menu and reopen: error persists without auto refetch
      fireEvent.keyDown(runChip, { key: 'Escape' });
      fireEvent.click(runChip);
      expect(screen.getByText(/Bạn không có quyền|Forbidden/)).toBeDefined();
      expect(runCalls).toBe(initialRunCalls);

      // Retry succeeds
      shouldFailRun = false;
      fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));

      // Run row appears
      expect(await screen.findByText('#45')).toBeDefined();
    });

    it('shows visible error and retry button on first Task 500, and loads tasks on retry success', async () => {
      let taskCalls = 0;
      let shouldFailTask = true;
      const { authApi } = setupMockEnv(undefined, 1, (req) => {
        if (req.url.includes('/tasks/')) {
          taskCalls++;
          if (shouldFailTask) {
            return new Response(JSON.stringify({ detail: 'Server error' }), {
              status: 500,
              headers: { 'Content-Type': 'application/json' },
            });
          }
          return Response.json([{ cvat_task_id: 118, name: 'Urban day', jobs: [] }]);
        }
        return undefined;
      });

      await authApi.signIn('admin');

      render(
        <AuthProvider>
          <ContextBar datasetIdOverride={1} isOverview={true} />
        </AuthProvider>
      );

      // Open scope picker
      const scopeChip = screen.getByRole('button', { name: /Phạm vi/ });
      fireEvent.click(scopeChip);

      // Error appears with retry button
      expect(await screen.findByText(/Máy chủ gặp lỗi/)).toBeDefined();
      const retryBtn = screen.getByRole('button', { name: 'Thử lại' });
      expect(retryBtn).toBeDefined();
      const initialTaskCalls = taskCalls;

      // Close menu and reopen: error persists without auto refetch
      fireEvent.keyDown(scopeChip, { key: 'Escape' });
      fireEvent.click(scopeChip);
      expect(screen.getByText(/Máy chủ gặp lỗi/)).toBeDefined();
      expect(taskCalls).toBe(initialTaskCalls);

      // Retry succeeds
      shouldFailTask = false;
      fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));

      // Task item appears
      expect(await screen.findByText(/Task #118 · Urban day/)).toBeDefined();
    });

    it('handles delayed first dataset success and reopen while pending without self-cancellation', async () => {
      let resolvePromise: (value: Response) => void;
      const delayedPromise = new Promise<Response>((resolve) => {
        resolvePromise = resolve;
      });

      const { authApi } = setupMockEnv(undefined, 1, (req) => {
        if (req.url.includes('/api/datasets/')) {
          return delayedPromise;
        }
        return undefined;
      });

      await authApi.signIn('reviewer');

      function DsHarness() {
        const { session } = useAuth();
        if (!session) return <div>Đang khởi tạo phiên...</div>;
        return <ContextBar datasetIdOverride={1} isOverview={true} />;
      }

      render(
        <AuthProvider>
          <DsHarness />
        </AuthProvider>
      );

      const dsChip = await screen.findByRole('button', { name: /Dataset/ });
      fireEvent.click(dsChip);

      // In flight loading indicator
      expect(await screen.findByText('Đang tải danh sách Dataset…')).toBeDefined();

      // Close menu while request is still pending
      fireEvent.keyDown(dsChip, { key: 'Escape' });
      expect(screen.queryByRole('menu')).toBeNull();

      // Reopen menu while request is still pending
      fireEvent.click(dsChip);
      expect(screen.getByText('Đang tải danh sách Dataset…')).toBeDefined();

      // Resolve delayed promise
      resolvePromise!(
        Response.json({
          next: null,
          previous: null,
          results: [{ id: 1, name: 'Road Vision Urban', cvat_project_id: 31 }],
        })
      );

      // Menu renders the resolved dataset without cancelling or restarting
      expect(await screen.findByText('Road Vision Urban')).toBeDefined();
    });

    it('clears lock icon immediately when switching to a different delayed snapshot', async () => {
      let resolveSnap100: (value: Response) => void;
      const delayedSnap100Promise = new Promise<Response>((resolve) => {
        resolveSnap100 = resolve;
      });

      const { authApi } = setupMockEnv(undefined, 1, (req) => {
        if (req.url.includes('/api/snapshots/99/')) {
          return Response.json({ id: 99, status: 'locked', dataset_id: 1 });
        }
        if (req.url.includes('/api/snapshots/100/')) {
          return delayedSnap100Promise;
        }
        return undefined;
      });

      await authApi.signIn('admin');

      const runWithSnap99: Run = {
        id: 10,
        snapshot_id: 99,
        config_version_id: 1,
        seed: 42,
        status: 'completed',
        is_final: true,
        engines: [],
        created_by: 1,
        created_at: '2026-10-10T00:00:00Z',
      };
      const runWithSnap100: Run = {
        id: 11,
        snapshot_id: 100,
        config_version_id: 1,
        seed: 43,
        status: 'completed',
        is_final: true,
        engines: [],
        created_by: 1,
        created_at: '2026-10-10T00:00:00Z',
      };

      const { rerender } = render(
        <AuthProvider>
          <ContextBar datasetIdOverride={1} isOverview={true} selectedRun={runWithSnap99} />
        </AuthProvider>
      );

      // Initially locked
      expect(await screen.findByRole('img', { name: 'Đã khoá' })).toBeDefined();

      // Switch to DIFFERENT run with snapshot 100 (which is delayed)
      rerender(
        <AuthProvider>
          <ContextBar datasetIdOverride={1} isOverview={true} selectedRun={runWithSnap100} />
        </AuthProvider>
      );

      // Lock icon must clear IMMEDIATELY without waiting for snapshot 100
      expect(screen.queryByRole('img', { name: 'Đã khoá' })).toBeNull();

      // When snapshot 100 resolves with 'active', lock icon remains absent
      resolveSnap100!(Response.json({ id: 100, status: 'active', dataset_id: 1 }));
      await waitFor(() => {
        expect(screen.queryByRole('img', { name: 'Đã khoá' })).toBeNull();
      });
    });

    it('binds QualitySummary tasks and notices to ownerKey across same-ID auth switches in a preserved mounted tree', async () => {
      let currentUser = 2;
      const { authApi } = setupMockEnv(undefined, undefined, (req) => {
        if (req.url.includes('/tasks/')) {
          if (currentUser === 2) {
            return Response.json([{ cvat_task_id: 101, name: 'Task User 1', jobs: [] }]);
          } else {
            return Response.json([{ cvat_task_id: 202, name: 'Task User 2', jobs: [] }]);
          }
        }
        return undefined;
      });

      await authApi.signIn('qalead'); // user id 2
      const ds: Dataset = { id: 1, name: 'Road Vision Urban', cvat_project_id: 31 };

      function AuthPreservedHarness() {
        const { session, login, user } = useAuth();
        if (!session) return <div>Đang khởi tạo phiên...</div>;
        return (
          <div>
            <QualitySummary currentDataset={ds} />
            {user?.username === 'qalead' && (
              <button
                type="button"
                onClick={() => {
                  currentUser = 4;
                  void login({ username: 'reviewer', password: 'password123' });
                }}
              >
                Chuyển sang reviewer
              </button>
            )}
          </div>
        );
      }

      render(
        <AuthProvider>
          <AuthPreservedHarness />
        </AuthProvider>
      );

      // User 1's task appears
      expect(await screen.findByText(/Task #101 · Task User 1/)).toBeDefined();

      // Click "Xem Quality Report" to trigger notice
      fireEvent.click(screen.getByRole('button', { name: 'Xem Quality Report' }));
      expect(screen.getByText(/Chức năng vẫn chưa được kết nối với server.*Xem Quality Report/)).toBeDefined();

      // Trigger switch to reviewer (same dataset 1) in the preserved tree
      fireEvent.click(screen.getByRole('button', { name: 'Chuyển sang reviewer' }));

      // The previous notice from user 1 must clear immediately
      await waitFor(() => {
        expect(screen.queryByText(/Chức năng vẫn chưa được kết nối với server.*Xem Quality Report/)).toBeNull();
      });

      // User 2's task appears, and User 1's task is no longer present
      expect(await screen.findByText(/Task #202 · Task User 2/)).toBeDefined();
      expect(screen.queryByText(/Task #101 · Task User 1/)).toBeNull();
    });

    it('calls task selection callback exactly once on click, Enter, and Space', async () => {
      const { authApi } = setupMockEnv(undefined, 1, (req) => {
        if (req.url.includes('/tasks/')) {
          return Response.json([{ cvat_task_id: 118, name: 'Urban day', jobs: [] }]);
        }
        return undefined;
      });
      await authApi.signIn('admin');
      const ds: Dataset = { id: 1, name: 'Road Vision Urban', cvat_project_id: 31 };
      const onScopeChange = vi.fn();

      render(
        <AuthProvider>
          <QualitySummary currentDataset={ds} onTaskScopeChange={onScopeChange} />
        </AuthProvider>
      );

      const taskRow = await screen.findByRole('row', { name: /Task #118 · Urban day/ });

      // Click once
      fireEvent.click(taskRow);
      expect(onScopeChange).toHaveBeenCalledTimes(1);
      expect(onScopeChange).toHaveBeenLastCalledWith('Task #118 · Urban day');

      // Press Enter once
      fireEvent.keyDown(taskRow, { key: 'Enter' });
      expect(onScopeChange).toHaveBeenCalledTimes(2);

      // Press Space once
      fireEvent.keyDown(taskRow, { key: ' ' });
      expect(onScopeChange).toHaveBeenCalledTimes(3);
    });

    it('promptly clears parent run and scope selection on auth owner change', async () => {
      currentSearchParam = 'view=summary';
      const { authApi } = setupMockEnv(undefined, undefined);
      await authApi.signIn('qalead');

      function AuthHomeHarness() {
        const { session, login, user } = useAuth();
        if (!session) return <div>Đang khởi tạo phiên...</div>;
        return (
          <div>
            <Home />
            {user?.username === 'qalead' && (
              <button
                type="button"
                onClick={() => void login({ username: 'reviewer', password: 'password123' })}
              >
                Chuyển tài khoản Home
              </button>
            )}
          </div>
        );
      }

      render(
        <AuthProvider>
          <AuthHomeHarness />
        </AuthProvider>
      );

      // Wait for QualitySummary to appear for qalead
      expect(await screen.findByRole('heading', { level: 1, name: 'Quality Summary' })).toBeDefined();

      // Switch auth user
      fireEvent.click(screen.getByRole('button', { name: 'Chuyển tài khoản Home' }));

      // Ensure that header displays clean em dash for run without carrying over old run
      expect(await screen.findByText(/Quality Control Run: —\./)).toBeDefined();
    });

    it('binds ContextBar notice identity to user and dataset, dropping immediately upon dataset or auth change', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer');

      function ContextBarNoticeHarness() {
        const { session, datasetId, setDatasetId } = useAuth();
        if (!session) return <div>Đang khởi tạo phiên...</div>;
        return (
          <div>
            <ContextBar
              datasetIdOverride={datasetId ?? undefined}
              datasetName={datasetId === 1 ? 'Road Vision Urban' : 'Road Vision Highway'}
              guidelineVersion={datasetId === 1 ? 'v1.2' : '—'}
              isOverview={true}
            />
            <button type="button" onClick={() => setDatasetId(2)}>
              Chuyển sang Dataset 2
            </button>
          </div>
        );
      }

      render(
        <AuthProvider>
          <ContextBarNoticeHarness />
        </AuthProvider>
      );

      const guidelineChip = await screen.findByRole('button', { name: /Guideline v1\.2/ });
      fireEvent.click(guidelineChip);

      // Notice appears for dataset 1
      expect(await screen.findByText(/Phiên bản Guideline: v1\.2/)).toBeDefined();

      // Switch to dataset 2
      fireEvent.click(screen.getByRole('button', { name: 'Chuyển sang Dataset 2' }));

      // Notice must be immediately dropped
      expect(screen.queryByText(/Phiên bản Guideline: v1\.2/)).toBeNull();
    });
  });
});
