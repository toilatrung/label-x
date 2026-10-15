import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import ReviewPage from '@/app/review/page';
import ReviewWorkspacePage from '@/app/review/workspace/page';
import { installMockAuthApi } from './helpers/mock-api';
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
  issue_counts: { E1: 1 },
  explanation: { baseline: 0.1 },
  lease_holder_user_id: null,
};

const mockGrant12: LeaseGrant = {
  lease: {
    id: 9901,
    frame_id: 340,
    holder_user_id: 4, // Matches 'reviewer' id: 4
    expires_at: new Date(Date.now() + 600000).toISOString(),
  },
  frame: {
    id: 340,
    run_id: 12,
    frame_key: { cvat_task_id: 10, frame_number: 100 },
    cvat_job_id: 101,
    rank: 1,
    review_state: 'incomplete',
    missing_evidence: false,
    cvat_deep_link: 'http://cvat.local/tasks/10/jobs/101?frame=100',
  },
  resumed: false,
};

const mockFrameIssues = {
  frame: {
    id: 340,
    run_id: 12,
    frame_key: { cvat_task_id: 10, frame_number: 100 },
    image_url: 'http://example.com/frame340.jpg',
    width: 1920,
    height: 1080,
    review_state: 'incomplete',
    cvat_deep_link: 'http://cvat.local/tasks/10/jobs/101?frame=100',
  },
  guideline_version: 'v1.0.0',
  engines: [{ engine: 'detector', status: 'checked' }],
  issues: [
    {
      id: 501,
      frame_id: 340,
      family: 'E1',
      origin: 'engine',
      anchor: { kind: 'box', objects: [{ namespace: 'cvat_shape', id: 'box-1' }], rule_id: 'R-DET-01' },
      rule_ids: ['R-DET-01'],
      review_decisions: [],
      evidence: [],
      state: 'in_review',
    },
  ],
};

describe('T-037 ReviewQueue & ReviewWorkspace Integration', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
        mutations: { retry: false },
      },
    });
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

      calls.push(request);

      if (customHandler) {
        const customResp = await customHandler(request);
        if (customResp) return customResp;
      }

      if (path === '/api/runs/12/') {
        return Response.json(mockRun12);
      }

      if (path === '/api/runs/12/ranking/') {
        return Response.json({
          next: null,
          previous: null,
          source: 'risk',
          content_hash: 'hash_1',
          ranking_hash: 'hash_2',
          results: [mockRiskFrame1],
        });
      }

      if (path === '/api/queues/risk/next/') {
        return Response.json(mockGrant12);
      }

      if (path === '/api/frames/340/issues/' || path === '/api/frames/340/workspace/') {
        return Response.json(mockFrameIssues);
      }

      if (path === '/api/guidelines/rules/R-DET-01/') {
        return Response.json({
          rule_id: 'R-DET-01',
          guideline_version: 'v1.0.0',
          section: 'Quy tắc phát hiện thiếu nhãn',
          content: 'Nội dung quy tắc',
        });
      }

      return Response.json({ detail: 'Not found' }, { status: 404 });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ReviewPage />
        </AuthProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Trung tâm kiểm tra')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i })).toBeInTheDocument();
    });

    return { api, calls };
  }

  it('claims next frame from queue and opens Workspace in memory without an extra claim', async () => {
    const { calls } = await renderReviewPage('reviewer');

    // Wait for ranking to load
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i })).toBeInTheDocument();
    });

    // Claim next frame
    fireEvent.click(screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i }));

    // Verify active lease banner appears with Workspace open button
    await waitFor(() => {
      expect(screen.getByText('Phiên kiểm tra đang giữ (Active Lease)')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i })).toBeInTheDocument();
    });

    // Count queue claim calls before entering workspace
    const claimCallsBefore = calls.filter((r) => r.url.includes('/api/queues/risk/next/')).length;
    expect(claimCallsBefore).toBe(1);

    // Open workspace
    fireEvent.click(screen.getByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i }));

    // ReviewWorkspace rendered inside AppShell
    await waitFor(() => {
      expect(screen.getByRole('region', { name: /Không gian kiểm tra Review Workspace/i })).toBeInTheDocument();
      expect(screen.getByText(/Quy tắc phát hiện thiếu nhãn/i)).toBeInTheDocument();
    });

    // Ensure NO second claim was called
    const claimCallsAfter = calls.filter((r) => r.url.includes('/api/queues/risk/next/')).length;
    expect(claimCallsAfter).toBe(1);

    // Click back to queue button
    fireEvent.click(screen.getByRole('button', { name: /Quay lại danh sách hàng đợi/i }));

    // Returned to queue view; active lease card remains present
    await waitFor(() => {
      expect(screen.getByText('Phiên kiểm tra đang giữ (Active Lease)')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i })).toBeInTheDocument();
    });
  });

  it('removes open Workspace immediately upon run or context change', async () => {
    await renderReviewPage('reviewer');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i })).toBeInTheDocument();
    });

    // Claim and enter workspace
    fireEvent.click(screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i }));

    await waitFor(() => {
      expect(screen.getByRole('region', { name: /Không gian kiểm tra Review Workspace/i })).toBeInTheDocument();
    });

    // Submit new run input
    const runInput = screen.getByPlaceholderText(/Nhập mã/i);
    fireEvent.change(runInput, { target: { value: '99' } });
    fireEvent.click(screen.getByRole('button', { name: /Tải hàng đợi/i }));

    // Workspace is immediately removed
    await waitFor(() => {
      expect(screen.queryByRole('region', { name: /Không gian kiểm tra Review Workspace/i })).not.toBeInTheDocument();
    });
  });

  it('prevents opening editable workspace when lease is expired, conflict or holder mismatch', async () => {
    // Custom grant with mismatched holder
    const customGrantMismatch: LeaseGrant = {
      lease: {
        id: 9902,
        frame_id: 340,
        holder_user_id: 999, // Mismatch (reviewer is id 4)
        expires_at: new Date(Date.now() + 600000).toISOString(),
      },
      frame: {
        id: 340,
        run_id: 12,
        frame_key: { cvat_task_id: 10, frame_number: 100 },
        review_state: 'incomplete',
        missing_evidence: false,
      },
    };

    await renderReviewPage('reviewer', async (req) => {
      if (req.url.includes('/api/queues/risk/next/')) {
        return Response.json(customGrantMismatch);
      }
      return null;
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i }));

    await waitFor(() => {
      expect(screen.getByText('Phiên kiểm tra đang giữ (Active Lease)')).toBeInTheDocument();
    });

    // "Vào kiểm tra frame (Workspace)" button must NOT be offered due to holder mismatch
    expect(screen.queryByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i })).not.toBeInTheDocument();
  });

  it('renders standalone /review/workspace in safe read-only inspection mode without grant', async () => {
    searchParamsState.current = 'frame_id=340';
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    const originalFetch = api.fetchSpy.getMockImplementation()!;

    api.fetchSpy.mockImplementation(async (request: Request) => {
      const url = new URL(request.url);
      if (url.pathname.startsWith('/api/auth/')) {
        return originalFetch(request);
      }
      if (url.pathname === '/api/frames/340/issues/' || url.pathname === '/api/frames/340/workspace/') {
        return Response.json(mockFrameIssues);
      }
      return Response.json({ detail: 'Not found' }, { status: 404 });
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ReviewWorkspacePage />
        </AuthProvider>
      </QueryClientProvider>
    );

    // Verify Read-Only Notice
    await waitFor(() => {
      expect(screen.getByText(/Chế độ chỉ xem/i)).toBeInTheDocument();
      expect(screen.getByText(/Frame được mở trực tiếp, không đi từ hàng đợi/i)).toBeInTheDocument();
    });

    // Decision form actions are disabled in read-only mode
    const confirmChoice = screen.getByLabelText(/Xác nhận có lỗi/i);
    expect(confirmChoice).toBeDisabled();
  });

  it('synchronizes 409 conflict from Workspace to Queue, disabling reopening', async () => {
    let leaseConflictTriggered = false;

    await renderReviewPage('reviewer', async (req) => {
      if (req.url.includes('/api/leases/9901/renew/')) {
        leaseConflictTriggered = true;
        return Response.json(
          { code: 'LEASE_CONFLICT', message: 'Lease expired or held by another user' },
          { status: 409 }
        );
      }
      return null;
    });

    // Claim and enter workspace
    fireEvent.click(screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i }));

    await waitFor(() => {
      expect(screen.getByRole('region', { name: /Không gian kiểm tra Review Workspace/i })).toBeInTheDocument();
    });

    // Trigger renewal inside Workspace which returns 409
    const renewBtn = screen.getByRole('button', { name: /Thử gia hạn lease/i });
    fireEvent.click(renewBtn);

    // Workspace shows conflict banner
    await waitFor(() => {
      expect(screen.getByText(/Xung đột lease \(409 Conflict\)/i)).toBeInTheDocument();
    });

    // Click back to queue
    fireEvent.click(screen.getByRole('button', { name: /Quay lại danh sách hàng đợi/i }));

    // Back in Queue: active lease card shows conflict badge and reopening is blocked
    await waitFor(() => {
      expect(screen.getByText(/Đã hết hạn \/ Xung đột/i)).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i })).not.toBeInTheDocument();
    });
    expect(leaseConflictTriggered).toBe(true);
  });

  it('synchronizes successful lease renewal from Workspace to Queue active grant card', async () => {
    const renewedExpiry = new Date(Date.now() + 3600000); // 1 hour ahead

    await renderReviewPage('reviewer', async (req) => {
      if (req.url.includes('/api/leases/9901/renew/')) {
        return Response.json({
          id: 9901,
          frame_id: 340,
          holder_user_id: 4,
          expires_at: renewedExpiry.toISOString(),
        });
      }
      return null;
    });

    // Claim and enter workspace
    fireEvent.click(screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i }));

    await waitFor(() => {
      expect(screen.getByRole('region', { name: /Không gian kiểm tra Review Workspace/i })).toBeInTheDocument();
    });

    // Renew lease inside Workspace
    const renewBtn = screen.getByRole('button', { name: /Thử gia hạn lease/i });
    fireEvent.click(renewBtn);

    // Wait for lease renewal countdown to update to ~60 minutes before navigating back
    await waitFor(() => {
      expect(screen.getByText(/Lease: (59|60):/)).toBeInTheDocument();
    });

    // Return to Queue
    fireEvent.click(screen.getByRole('button', { name: /Quay lại danh sách hàng đợi/i }));

    // Back in Queue: active lease card displays the updated expiration
    await waitFor(() => {
      expect(screen.getByText(renewedExpiry.toLocaleString())).toBeInTheDocument();
    });
  });

  it('treats NaN/invalid date expires_at as expired and blocks opening editable workspace', async () => {
    const customGrantInvalidExpiry: LeaseGrant = {
      lease: {
        id: 9903,
        frame_id: 340,
        holder_user_id: 4,
        expires_at: 'not-a-valid-date-nan',
      },
      frame: {
        id: 340,
        run_id: 12,
        frame_key: { cvat_task_id: 10, frame_number: 100 },
        review_state: 'incomplete',
        missing_evidence: false,
      },
    };

    await renderReviewPage('reviewer', async (req) => {
      if (req.url.includes('/api/queues/risk/next/')) {
        return Response.json(customGrantInvalidExpiry);
      }
      return null;
    });

    fireEvent.click(screen.getByRole('button', { name: /Nhận frame kế tiếp từ hàng đợi/i }));

    await waitFor(() => {
      expect(screen.getByText('Phiên kiểm tra đang giữ (Active Lease)')).toBeInTheDocument();
    });

    // Reopening is blocked because expires_at is not a finite date
    expect(screen.queryByRole('button', { name: /Vào kiểm tra frame \(Workspace\)/i })).not.toBeInTheDocument();
  });
});
