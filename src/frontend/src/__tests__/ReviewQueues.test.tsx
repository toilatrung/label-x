import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import ReviewPage from '@/app/review/page';
import { installMockAuthApi } from './helpers/mock-api';
import { toMockSession, MOCK_USERS } from '@/lib/auth/mock-users';
import type { RankedFrame, LeaseGrant, Run } from '@/lib/review/types';

const { push, replace, searchParamsState } = vi.hoisted(() => {
  const state = { current: 'run=12' };
  return {
    push: vi.fn((url: string) => {
      const q = url.includes('?') ? url.split('?')[1] : '';
      state.current = q;
    }),
    replace: vi.fn((url: string) => {
      const q = url.includes('?') ? url.split('?')[1] : '';
      state.current = q;
    }),
    searchParamsState: state,
  };
});

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace }),
  usePathname: () => '/review',
  useSearchParams: () => new URLSearchParams(searchParamsState.current),
}));

// Strictly matches OpenAPI Run schema (no dataset_id)
const mockRun12: Run = {
  id: 12,
  snapshot_id: 4,
  config_version_id: 7,
  seed: 42,
  status: 'completed',
  is_final: false,
  origin_run_id: null,
  score_version: 'score_v0',
  model_artifact: null,
  engines: [],
  created_by: 2,
  created_at: '2026-10-10T00:00:00Z',
  finished_at: '2026-10-10T00:05:00Z',
};

const mockRun99: Run = {
  id: 99,
  snapshot_id: 5,
  config_version_id: 7,
  seed: 99,
  status: 'completed',
  is_final: false,
  origin_run_id: null,
  score_version: 'score_v0',
  model_artifact: null,
  engines: [],
  created_by: 2,
  created_at: '2026-10-10T01:00:00Z',
  finished_at: '2026-10-10T01:05:00Z',
};

const mockRiskFrame1: RankedFrame = {
  frame_id: 340,
  frame_key: { cvat_task_id: 10, frame_number: 100 },
  rank: 1,
  score: 0.85,
  baseline_score: 0.1,
  score_version: 'score_v0',
  queue: 'risk',
  source: 'risk',
  review_state: 'unreviewed',
  missing_evidence: false,
  issue_counts: { E1: 2, E2: 1 },
  explanation: { baseline: 0.1, factors: [{ name: 'E1', contrib: 0.5 }] },
  lease_holder_user_id: null,
};

// Frame with same frame_number 100 but different cvat_task_id 20 to test composite key uniqueness
const mockRiskFrame2: RankedFrame = {
  frame_id: 341,
  frame_key: { cvat_task_id: 20, frame_number: 100 },
  rank: 2,
  score: 0.65,
  baseline_score: 0.2,
  score_version: 'score_v0',
  queue: 'risk',
  source: 'risk',
  review_state: 'incomplete',
  missing_evidence: true,
  issue_counts: { E3: 1 },
  explanation: { baseline: 0.2 },
  lease_holder_user_id: 4,
};

const mockRandomFrame: RankedFrame = {
  frame_id: 342,
  frame_key: { cvat_task_id: 10, frame_number: 200 },
  rank: 1,
  score: 0.05,
  baseline_score: 0.05,
  score_version: 'score_v0',
  queue: 'random',
  source: 'random_audit',
  review_state: 'unreviewed',
  missing_evidence: false,
  issue_counts: {},
  explanation: { baseline: 0.05 },
  lease_holder_user_id: null,
};

const mockLeaseGrant: LeaseGrant = {
  lease: {
    id: 350,
    frame_id: 340,
    holder_user_id: 4,
    expires_at: '2026-10-11T12:00:00Z',
  },
  frame: {
    id: 340,
    run_id: 12,
    frame_key: { cvat_task_id: 10, frame_number: 100 },
    cvat_job_id: 50,
    rank: 1,
    review_state: 'in_review',
    missing_evidence: false,
    image_url: 'http://localhost:8000/media/frames/340.jpg',
    width: 1920,
    height: 1080,
    cvat_deep_link: 'http://localhost:8080/tasks/10/jobs/50?frame=100',
  },
  resumed: false,
};

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
}

describe('ReviewQueues Frontend (T-034)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchParamsState.current = 'run=12';
  });

  async function renderReviewPage(
    username = 'reviewer',
    customHandler?: (req: Request) => Promise<Response | null>
  ) {
    const api = installMockAuthApi();
    await api.signIn(username);
    const originalFetch = api.fetchSpy.getMockImplementation()!;
    const calls: Request[] = [];

    api.fetchSpy.mockImplementation(async (request: Request) => {
      const url = new URL(request.url);
      const path = url.pathname;

      if (path.startsWith('/api/auth/')) {
        return originalFetch(request);
      }

      // Record non-auth data/mutation requests
      calls.push(request);

      if (customHandler) {
        const customResp = await customHandler(request);
        if (customResp) return customResp;
      }

      // Default mock responses with full OpenAPI envelopes
      if (path === '/api/runs/12/') {
        return Response.json(mockRun12);
      }
      if (path === '/api/runs/99/') {
        return Response.json(mockRun99);
      }

      if (path === '/api/runs/12/ranking/' || path === '/api/runs/99/ranking/') {
        const queue = url.searchParams.get('queue') || 'risk';
        const cursor = url.searchParams.get('cursor');

        if (queue === 'random') {
          return Response.json({
            next: null,
            previous: null,
            source: 'random_audit',
            content_hash: 'content_hash_rnd',
            ranking_hash: 'ranking_hash_rnd',
            results: [mockRandomFrame],
          });
        }

        if (cursor === 'cur_p2') {
          return Response.json({
            next: null,
            previous: 'http://localhost/api/runs/12/ranking/?queue=risk&cursor=cur_p1',
            source: 'risk',
            content_hash: 'content_hash_p2',
            ranking_hash: 'ranking_hash_p2',
            results: [mockRiskFrame2],
          });
        }

        return Response.json({
          next: 'http://localhost/api/runs/12/ranking/?queue=risk&cursor=cur_p2',
          previous: null,
          source: 'risk',
          content_hash: 'content_hash_p1',
          ranking_hash: 'ranking_hash_p1',
          results: [mockRiskFrame1],
        });
      }

      if (path === '/api/queues/risk/next/' || path === '/api/queues/random/next/') {
        return Response.json(mockLeaseGrant);
      }

      if (path === '/api/leases/350/renew/') {
        return Response.json({
          ...mockLeaseGrant.lease,
          expires_at: '2026-10-11T12:30:00Z',
        });
      }

      return Response.json({ code: 'NOT_FOUND', message: 'Not found' }, { status: 404 });
    });

    const queryClient = createTestQueryClient();
    const renderResult = render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ReviewPage />
        </AuthProvider>
      </QueryClientProvider>
    );

    return { api, calls, queryClient, ...renderResult };
  }

  // --- AC A1: Two independent queues, server filters, pagination, fields ---
  describe('A1: Queues, Filters & Pagination', () => {
    it('renders risk queue frames with rank, score, issue counts, and composite frame key', async () => {
      await renderReviewPage('reviewer');

      // Check header and wait for tabs to render upon run query success
      expect(await screen.findByText('Trung tâm kiểm tra (Review Queues)')).toBeDefined();
      expect(await screen.findByRole('tab', { name: /Hàng đợi rủi ro/i })).toBeDefined();

      // Check frame key contains both task and frame number
      expect(await screen.findByText('Task #10 • Frame #100')).toBeDefined();
      expect(screen.getByText('#1')).toBeDefined();
      expect(screen.getByText('0.850')).toBeDefined();
      expect(screen.getByText('Nền: 0.100')).toBeDefined();
      expect(screen.getByText('E1: 2')).toBeDefined();
      expect(screen.getByText('E2: 1')).toBeDefined();
    });

    it('switches to random queue tab independently and fetches random queue data', async () => {
      const { calls } = await renderReviewPage('reviewer');

      await screen.findByText('Task #10 • Frame #100');

      const randomTab = await screen.findByRole('tab', { name: /Kiểm định ngẫu nhiên/i });
      fireEvent.click(randomTab);

      // Verify random frame is rendered
      expect(await screen.findByText('Task #10 • Frame #200')).toBeDefined();
      expect(screen.queryByText('Task #10 • Frame #100')).toBeNull();

      // Verify network request had queue=random
      const randomCall = calls.find(
        (c) =>
          c.url.includes('/api/runs/12/ranking/') &&
          new URL(c.url).searchParams.get('queue') === 'random'
      );
      expect(randomCall).toBeDefined();
    });

    it('paginates using server cursors and allows navigating forward and backward', async () => {
      const { calls } = await renderReviewPage('reviewer');

      await screen.findByText('Task #10 • Frame #100');

      const nextBtn = screen.getByRole('button', { name: 'Trang tiếp' });
      expect(nextBtn).toBeDefined();
      expect((nextBtn as HTMLButtonElement).disabled).toBe(false);

      fireEvent.click(nextBtn);

      // Second page shows mockRiskFrame2
      expect(await screen.findByText('Task #20 • Frame #100')).toBeDefined();
      expect(screen.getByText('Thiếu bằng chứng')).toBeDefined();

      const prevBtn = screen.getByRole('button', { name: 'Trang trước' });
      expect((prevBtn as HTMLButtonElement).disabled).toBe(false);

      // Verify call had cursor=cur_p2
      const page2Call = calls.find(
        (c) =>
          c.url.includes('/api/runs/12/ranking/') &&
          new URL(c.url).searchParams.get('cursor') === 'cur_p2'
      );
      expect(page2Call).toBeDefined();

      // Click previous to return
      fireEvent.click(prevBtn);
      expect(await screen.findByText('Task #10 • Frame #100')).toBeDefined();
    });

    it('resets cursor when changing filters', async () => {
      const { calls } = await renderReviewPage('reviewer');

      await screen.findByText('Task #10 • Frame #100');

      const familySelect = screen.getByLabelText(/Lọc theo nhóm lỗi/i);
      fireEvent.change(familySelect, { target: { value: 'E1' } });

      await waitFor(() => {
        const filterCall = calls.find(
          (c) =>
            c.url.includes('/api/runs/12/ranking/') &&
            new URL(c.url).searchParams.get('family') === 'E1'
        );
        expect(filterCall).toBeDefined();
        // Cursor parameter should be absent when reset
        expect(new URL(filterCall!.url).searchParams.get('cursor')).toBeNull();
      });
    });
  });

  // --- AC A2: Access Control, Guard & Dataset Context ---
  describe('A2: Access Control & Isolation', () => {
    it('blocks annotator from review center and makes 0 data queries', async () => {
      const { calls } = await renderReviewPage('annotator');

      expect(await screen.findByText('403 - Quyền truy cập bị từ chối')).toBeDefined();
      expect(screen.queryByText('Trung tâm kiểm tra (Review Queues)')).toBeNull();

      // Assert 0 data queries to ranking, run, or queue
      const dataCalls = calls.filter((c) => !c.url.includes('/api/auth/'));
      expect(dataCalls.length).toBe(0);
    });

    it('blocks user without CVAT identity mapping and makes 0 data queries', async () => {
      const reviewerUser = MOCK_USERS.find((u) => u.role === 'reviewer')!;
      const calls: Request[] = [];
      vi.stubGlobal(
        'fetch',
        vi.fn(async (input: Request) => {
          const url = new URL(input.url);
          if (url.pathname === '/api/auth/session/') {
            return Response.json({
              ...toMockSession(reviewerUser),
              identity_mapping: { status: 'missing' },
            });
          }
          if (url.pathname === '/api/auth/csrf/') {
            return new Response(null, { status: 204 });
          }
          calls.push(input);
          return Response.json({ code: 'NOT_FOUND' }, { status: 404 });
        })
      );

      const queryClient = createTestQueryClient();
      render(
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ReviewPage />
          </AuthProvider>
        </QueryClientProvider>
      );

      expect(await screen.findByText('IDENTITY_MAPPING_MISSING')).toBeDefined();
      expect(screen.queryByText('Trung tâm kiểm tra (Review Queues)')).toBeNull();
      const dataCalls = calls.filter((c) => !c.url.includes('/api/auth/'));
      expect(dataCalls.length).toBe(0);
    });

    it('never calls GET /api/runs/ (history list) for reviewer', async () => {
      const { calls } = await renderReviewPage('reviewer');

      await screen.findByText('Trung tâm kiểm tra (Review Queues)');

      const runsListCalls = calls.filter((c) => {
        const path = new URL(c.url).pathname;
        return path === '/api/runs/' && c.method === 'GET';
      });
      expect(runsListCalls.length).toBe(0);
    });

    it('stops data queries when run fetch returns 403 or 404', async () => {
      const { calls } = await renderReviewPage('reviewer', async (req) => {
        if (req.url.includes('/api/runs/12/')) {
          return Response.json(
            { code: 'FORBIDDEN', message: 'Bạn không có quyền xem Run này.' },
            { status: 403 }
          );
        }
        return null;
      });

      expect(await screen.findByText(/Không thể tải thông tin Run #12/i)).toBeDefined();

      // Assert no ranking query or queue mutation was dispatched
      const rankingCalls = calls.filter((c) => c.url.includes('/ranking/'));
      const claimCalls = calls.filter((c) => c.url.includes('/queues/'));
      expect(rankingCalls.length).toBe(0);
      expect(claimCalls.length).toBe(0);
    });
  });

  // --- AC A3: Claim & Resume Operations ---
  describe('A3: Claim & Resume Operations', () => {
    it('claims next frame successfully and displays lease context', async () => {
      const { calls } = await renderReviewPage('reviewer');

      await screen.findByText('Task #10 • Frame #100');

      const claimBtn = screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i });
      fireEvent.click(claimBtn);

      expect(await screen.findByText('Phiên kiểm tra đang giữ (Active Lease)')).toBeDefined();
      expect(screen.getByText('Lease #350')).toBeDefined();
      expect(screen.getByText('Mở frame trên CVAT')).toBeDefined();

      const claimCall = calls.find((c) => c.url.includes('/api/queues/risk/next/'));
      expect(claimCall).toBeDefined();
      expect(claimCall?.method).toBe('POST');
    });

    it('handles resumed lease grant and displays Resumed badge', async () => {
      await renderReviewPage('reviewer', async (req) => {
        if (req.url.includes('/api/queues/risk/next/')) {
          return Response.json({
            ...mockLeaseGrant,
            resumed: true,
          });
        }
        return null;
      });

      await screen.findByText('Task #10 • Frame #100');

      const claimBtn = screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i });
      fireEvent.click(claimBtn);

      expect(await screen.findByText('Khôi phục phiên (Resumed)')).toBeDefined();
      expect(screen.getByText('Phiên kiểm tra đang giữ (Active Lease)')).toBeDefined();
    });

    it('allows renewing an active lease via renew button', async () => {
      const { calls } = await renderReviewPage('reviewer');

      await screen.findByText('Task #10 • Frame #100');

      const claimBtn = screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i });
      fireEvent.click(claimBtn);

      const renewBtn = await screen.findByRole('button', { name: /Gia hạn lease/i });
      fireEvent.click(renewBtn);

      expect(await screen.findByText(/Đã gia hạn lease thành công/i)).toBeDefined();

      const renewCall = calls.find((c) => c.url.includes('/api/leases/350/renew/'));
      expect(renewCall).toBeDefined();
    });

    it('discards stale claim response if dataset changes while request is pending', async () => {
      let resolveClaim: (resp: Response) => void;
      const claimPromise = new Promise<Response>((resolve) => {
        resolveClaim = resolve;
      });

      const reviewerUser = MOCK_USERS.find((u) => u.role === 'reviewer')!;
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const originalFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request: Request) => {
        const url = new URL(request.url);
        const path = url.pathname;
        if (path === '/api/auth/session/') {
          return Response.json({
            ...toMockSession(reviewerUser),
            // User with access to two datasets
            roles: [
              { role: 'reviewer', dataset_id: 1 },
              { role: 'reviewer', dataset_id: 2 },
            ],
          });
        }
        if (path.startsWith('/api/auth/')) return originalFetch(request);
        if (path === '/api/runs/12/') return Response.json(mockRun12);
        if (path.includes('/ranking/')) {
          return Response.json({
            next: null,
            previous: null,
            source: 'risk',
            content_hash: 'c1',
            ranking_hash: 'r1',
            results: [mockRiskFrame1],
          });
        }
        if (path.includes('/queues/')) {
          return claimPromise;
        }
        return Response.json({ code: 'NOT_FOUND' }, { status: 404 });
      });

      const queryClient = createTestQueryClient();
      render(
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ReviewPage />
          </AuthProvider>
        </QueryClientProvider>
      );

      await screen.findByText('Task #10 • Frame #100');

      // Click claim for run 12 in dataset 1
      const claimBtn = screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i });
      fireEvent.click(claimBtn);

      // Now switch dataset from 1 to 2 via ReviewDatasetPicker
      const datasetSelect = screen.getByLabelText(/Bộ dữ liệu/i);
      fireEvent.change(datasetSelect, { target: { value: '2' } });
      expect((datasetSelect as HTMLSelectElement).value).toBe('2');

      // Resolve old pending claim promise with success
      resolveClaim!(Response.json(mockLeaseGrant));
      await claimPromise;

      // Old lease context MUST NOT be rendered in dataset 2
      await waitFor(() => {
        expect(screen.queryByText('Lease #350')).toBeNull();
        expect(screen.queryByText('Phiên kiểm tra đang giữ (Active Lease)')).toBeNull();
      });
    });

    it('discards late 409 LEASE_CONFLICT error when dataset changes while request is pending', async () => {
      let resolveClaim: (resp: Response) => void;
      const claimPromise = new Promise<Response>((resolve) => {
        resolveClaim = resolve;
      });

      const reviewerUser = MOCK_USERS.find((u) => u.role === 'reviewer')!;
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const originalFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request: Request) => {
        const url = new URL(request.url);
        const path = url.pathname;
        if (path === '/api/auth/session/') {
          return Response.json({
            ...toMockSession(reviewerUser),
            roles: [
              { role: 'reviewer', dataset_id: 1 },
              { role: 'reviewer', dataset_id: 2 },
            ],
          });
        }
        if (path.startsWith('/api/auth/')) return originalFetch(request);
        if (path === '/api/runs/12/') return Response.json(mockRun12);
        if (path.includes('/ranking/')) {
          return Response.json({
            next: null,
            previous: null,
            source: 'risk',
            content_hash: 'c1',
            ranking_hash: 'r1',
            results: [mockRiskFrame1],
          });
        }
        if (path.includes('/queues/')) {
          return claimPromise;
        }
        return Response.json({ code: 'NOT_FOUND' }, { status: 404 });
      });

      const queryClient = createTestQueryClient();
      render(
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ReviewPage />
          </AuthProvider>
        </QueryClientProvider>
      );

      await screen.findByText('Task #10 • Frame #100');

      const claimBtn = screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i });
      fireEvent.click(claimBtn);

      // Switch dataset from 1 to 2 via ReviewDatasetPicker while claim is pending
      const datasetSelect = screen.getByLabelText(/Bộ dữ liệu/i);
      fireEvent.change(datasetSelect, { target: { value: '2' } });
      expect((datasetSelect as HTMLSelectElement).value).toBe('2');

      // Resolve old claim request with 409 LEASE_CONFLICT
      resolveClaim!(
        Response.json(
          { code: 'LEASE_CONFLICT', message: 'Lease expired', request_id: 'late-409' },
          { status: 409 }
        )
      );
      await claimPromise;

      // Late error/conflict MUST NOT be surfaced in Dataset 2
      await waitFor(() => {
        expect(screen.queryByText('LEASE_CONFLICT')).toBeNull();
        expect(screen.queryByText(/Thao tác với lease cũ đã bị khóa/i)).toBeNull();
        expect(screen.queryByText(/Không thể nhận frame/i)).toBeNull();
      });
    });

    it('immediately hides old run ranking when switching dataset and loads new run upon explicit selection', async () => {
      const reviewerUser = MOCK_USERS.find((u) => u.role === 'reviewer')!;
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const originalFetch = api.fetchSpy.getMockImplementation()!;
      const calls: Request[] = [];

      const mockRiskFrame99: RankedFrame = {
        frame_id: 990,
        frame_key: { cvat_task_id: 99, frame_number: 200 },
        rank: 1,
        score: 0.95,
        baseline_score: 0.1,
        score_version: 'score_v0',
        queue: 'risk',
        source: 'risk',
        review_state: 'unreviewed',
        missing_evidence: false,
        issue_counts: {},
        explanation: { baseline: 0.1 },
        lease_holder_user_id: null,
      };

      api.fetchSpy.mockImplementation(async (request: Request) => {
        calls.push(request);
        const url = new URL(request.url);
        const path = url.pathname;
        if (path === '/api/auth/session/') {
          return Response.json({
            ...toMockSession(reviewerUser),
            roles: [
              { role: 'reviewer', dataset_id: 1 },
              { role: 'reviewer', dataset_id: 2 },
            ],
          });
        }
        if (path.startsWith('/api/auth/')) return originalFetch(request);
        if (path === '/api/runs/12/') return Response.json(mockRun12);
        if (path === '/api/runs/99/') return Response.json(mockRun99);
        if (path === '/api/runs/12/ranking/') {
          return Response.json({
            next: null,
            previous: null,
            source: 'risk',
            content_hash: 'c1',
            ranking_hash: 'r1',
            results: [mockRiskFrame1],
          });
        }
        if (path === '/api/runs/99/ranking/') {
          return Response.json({
            next: null,
            previous: null,
            source: 'risk',
            content_hash: 'c2',
            ranking_hash: 'r2',
            results: [mockRiskFrame99],
          });
        }
        return Response.json({ code: 'NOT_FOUND' }, { status: 404 });
      });

      const queryClient = createTestQueryClient();
      render(
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ReviewPage />
          </AuthProvider>
        </QueryClientProvider>
      );

      // 1. Initial load with Dataset 1 & Run 12
      await screen.findByText('Task #10 • Frame #100');
      expect(screen.getByText('Task #10 • Frame #100')).toBeDefined();

      const callsBeforeSwitch = calls.length;

      // 2. Switch dataset selector from 1 to 2
      const datasetSelect = screen.getByLabelText(/Bộ dữ liệu/i);
      fireEvent.change(datasetSelect, { target: { value: '2' } });
      expect((datasetSelect as HTMLSelectElement).value).toBe('2');

      // 3. Old ranking/table/lease context must be immediately absent
      expect(screen.queryByText('Task #10 • Frame #100')).toBeNull();
      expect(screen.queryByRole('table', { name: /Bảng danh sách frame xếp hạng/i })).toBeNull();
      expect(screen.queryByText('Phiên kiểm tra đang giữ (Active Lease)')).toBeNull();
      expect(
        screen.getByText(/Vui lòng nhập Mã QC Run để tải hàng đợi kiểm tra/i)
      ).toBeDefined();

      // No new ranking or claim requests for run 12 sent under dataset 2
      const newCallsForRun12 = calls.slice(callsBeforeSwitch).filter((c) =>
        c.url.includes('/api/runs/12/')
      );
      expect(newCallsForRun12).toHaveLength(0);

      // 4. Select a new run explicitly for dataset 2 (Run 99)
      const runInput = screen.getByLabelText(/Mã QC Run/i);
      fireEvent.change(runInput, { target: { value: '99' } });
      const submitBtn = screen.getByRole('button', { name: /Tải hàng đợi/i });
      fireEvent.click(submitBtn);

      // 5. Assert loading and rendering new run 99 works under dataset 2
      await screen.findByText('Task #99 • Frame #200');
      expect(screen.getByText('Task #99 • Frame #200')).toBeDefined();
    });
  });

  // --- AC A4: Statuses, 204, 403, 409 & Error Handling ---
  describe('A4: Edge Cases & Error Handling', () => {
    it('handles 204 No Content when queue is empty for claim', async () => {
      await renderReviewPage('reviewer', async (req) => {
        if (req.url.includes('/api/queues/risk/next/')) {
          return new Response(null, { status: 204 });
        }
        return null;
      });

      await screen.findByText('Task #10 • Frame #100');

      const claimBtn = screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i });
      fireEvent.click(claimBtn);

      expect(
        await screen.findByText(/Hàng đợi không còn frame phù hợp để nhận kiểm tra \(204 No Content\)/i)
      ).toBeDefined();
      expect(screen.queryByText('Phiên kiểm tra đang giữ (Active Lease)')).toBeNull();
    });

    it('handles 409 LEASE_CONFLICT on renew, locks actions, and offers server reload', async () => {
      await renderReviewPage('reviewer', async (req) => {
        if (req.url.includes('/api/queues/risk/next/')) {
          return Response.json(mockLeaseGrant);
        }
        if (req.url.includes('/api/leases/350/renew/')) {
          return Response.json(
            {
              code: 'LEASE_CONFLICT',
              message: 'Quyền giữ frame đã hết hạn hoặc thuộc người khác.',
              request_id: 'req-renew-409',
            },
            { status: 409 }
          );
        }
        return null;
      });

      await screen.findByText('Task #10 • Frame #100');

      const claimBtn = screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i });
      fireEvent.click(claimBtn);

      const renewBtn = await screen.findByRole('button', { name: /Gia hạn lease/i });
      fireEvent.click(renewBtn);

      expect(await screen.findByText('LEASE_CONFLICT')).toBeDefined();
      expect(screen.getByText(/Thao tác với lease cũ đã bị khóa/i)).toBeDefined();

      // Renew button is locked/disabled
      expect((renewBtn as HTMLButtonElement).disabled).toBe(true);

      // Server reload button is provided
      const reloadBtns = screen.getAllByRole('button', { name: /Tải lại từ server/i });
      expect(reloadBtns.length).toBeGreaterThan(0);
      fireEvent.click(reloadBtns[0]);

      // Stale lease banner is cleared
      await waitFor(() => {
        expect(screen.queryByText('Lease #350')).toBeNull();
      });
    });

    it('handles 403 business error (e.g. SELF_REVIEW_FORBIDDEN) without looping', async () => {
      await renderReviewPage('reviewer', async (req) => {
        if (req.url.includes('/api/queues/risk/next/')) {
          return Response.json(
            {
              code: 'SELF_REVIEW_FORBIDDEN',
              message: 'Bạn không được review annotation do chính mình thực hiện.',
              request_id: 'req-self-review',
            },
            { status: 403 }
          );
        }
        return null;
      });

      await screen.findByText('Task #10 • Frame #100');

      const claimBtn = screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i });
      fireEvent.click(claimBtn);

      expect(await screen.findByText('SELF_REVIEW_FORBIDDEN')).toBeDefined();
    });

    it('shows empty list message when ranking results are empty', async () => {
      await renderReviewPage('reviewer', async (req) => {
        if (req.url.includes('/api/runs/12/ranking/')) {
          return Response.json({
            next: null,
            previous: null,
            source: 'risk',
            content_hash: 'c_empty',
            ranking_hash: 'r_empty',
            results: [],
          });
        }
        return null;
      });

      expect(
        await screen.findByText(/Không có frame nào khớp với điều kiện lọc/i)
      ).toBeDefined();
    });

    it('shows error callout and retry button deterministically when ranking fetch fails with 500', async () => {
      let attempt = 0;
      await renderReviewPage('reviewer', async (req) => {
        if (req.url.includes('/api/runs/12/ranking/')) {
          attempt++;
          if (attempt === 1) {
            return Response.json(
              { code: 'INTERNAL_ERROR', message: 'Máy chủ lỗi' },
              { status: 500 }
            );
          }
          return Response.json({
            next: null,
            previous: null,
            source: 'risk',
            content_hash: 'c_retry',
            ranking_hash: 'r_retry',
            results: [mockRiskFrame1],
          });
        }
        return null;
      });

      expect(await screen.findByText(/Lỗi tải danh sách frame/i)).toBeDefined();

      const retryBtn = screen.getByRole('button', { name: 'Thử lại' });
      expect(retryBtn).toBeDefined();
      fireEvent.click(retryBtn);

      expect(await screen.findByText('Task #10 • Frame #100')).toBeDefined();
    });
  });
});
