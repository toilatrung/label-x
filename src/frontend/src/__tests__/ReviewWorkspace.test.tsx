import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth/auth-context';
import { ReviewWorkspace } from '@/components/review/ReviewWorkspace';
import { installMockAuthApi } from './helpers/mock-api';
import type { components } from '@/lib/api/contract';

type FrameIssues = components['schemas']['FrameIssues'];
type Lease = components['schemas']['Lease'];

const baseFrameIssues: FrameIssues = {
  frame: {
    id: 428,
    run_id: 1,
    frame_key: { cvat_task_id: 10, frame_number: 428 },
    review_state: 'in_review',
    missing_evidence: false,
    width: 960,
    height: 540,
    image_url: 'https://example.com/frame-428.jpg',
    cvat_deep_link: 'https://cvat.example.com/tasks/10/jobs/1?frame=428',
  },
  guideline_version: 'v1.0',
  engines: [
    {
      engine: 'detector',
      status: 'checked',
    },
    {
      engine: 'vlm',
      status: 'failed',
      failed_units: 1,
    },
  ],
  issues: [
    {
      id: 101,
      family: 'E2',
      origin: 'engine',
      state: 'in_review',
      n_i: 1,
      anchor: {
        kind: 'annotation',
        policy_version: 'v1.0',
        objects: [{ namespace: 'cvat_shape', id: 'shape-18' }],
        bbox: { x1: 300, y1: 200, x2: 450, y2: 350 },
      },
      evidence: [
        {
          engine: 'detector',
          prediction_class: 'truck',
          confidence: 0.85,
          iou: 0.75,
          prediction_bbox: { x1: 295, y1: 195, x2: 455, y2: 355 },
        },
      ],
      links: [],
      review_decisions: [],
    },
  ],
};

// Reviewer user in MOCK_USERS has id: 4
const activeLease: Lease = {
  id: 77,
  frame_id: 428,
  holder_user_id: 4,
  expires_at: new Date(Date.now() + 600000).toISOString(),
};

async function renderWorkspace(
  props: Partial<React.ComponentProps<typeof ReviewWorkspace>> = {},
  frameIssuesResponse: { status: number; body: unknown } = { status: 200, body: baseFrameIssues }
) {
  const api = installMockAuthApi();
  await api.signIn('reviewer');

  const defaultFetch = api.fetchSpy.getMockImplementation()!;
  api.fetchSpy.mockImplementation(async (request) => {
    const url = new URL(request.url);

    // Pass auth requests through to actual mock-server session handler
    if (url.pathname.startsWith('/api/auth/')) {
      return defaultFetch(request);
    }

    if (url.pathname === '/api/frames/428/issues/') {
      return Response.json(frameIssuesResponse.body, { status: frameIssuesResponse.status });
    }

    if (url.pathname === '/api/guidelines/rules/VEH-03/') {
      return Response.json({
        rule_id: 'VEH-03',
        section: '3.2',
        content: 'Nội dung quy tắc xe tải VEH-03',
        guideline_version: 'v1.0',
      });
    }

    if (url.pathname === '/api/decision-cases/') {
      return Response.json([{
        id: 301,
        issue_id: 101,
        outcome: 'confirm',
        actor_user_id: 2,
        rule_id: 'VEH-03',
        correct_label: 'truck',
        reason: 'Workspace shared Decision Case lookup',
        case_version: 'v2',
        created_at: '2026-10-11T02:00:00Z',
      }]);
    }

    return Response.json({ code: 'NOT_FOUND' }, { status: 404 });
  });

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ReviewWorkspace
          frameId={428}
          initialLease={activeLease}
          snapshotRevision="rev-snapshot-abc"
          anchorPolicyVersion="anchor-policy-v1"
          {...props}
        />
      </AuthProvider>
    </QueryClientProvider>
  );

  return { ...view, api };
}

describe('ReviewWorkspace (T-037 Core Workspace Component)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('reuses the T-039 Decision Case lookup for the active issue', async () => {
    const { api } = await renderWorkspace();

    expect(await screen.findByText('Workspace shared Decision Case lookup')).toBeDefined();
    expect(api.fetchSpy.mock.calls.some(([request]) => {
      const url = new URL((request as Request).url);
      return url.pathname === '/api/decision-cases/' && url.searchParams.get('issue') === '101';
    })).toBe(true);
  });

  it('blocks decision submission when snapshotRevision is missing without inventing fallbacks', async () => {
    await renderWorkspace({ snapshotRevision: null });

    await screen.findByText('QC-00101');
    expect(
      screen.getByText(/Chưa có revision của Snapshot đã xác thực/)
    ).toBeDefined();

    const submitBtn = screen.getByRole('button', { name: 'Lưu quyết định' });
    expect(submitBtn).toBeDefined();
    expect((submitBtn as HTMLButtonElement).disabled).toBe(true);
  });

  it('blocks manual issue creation when anchorPolicyVersion is missing (T-035 interface gap)', async () => {
    await renderWorkspace({ anchorPolicyVersion: null });

    await screen.findByText('QC-00101');
    fireEvent.click(screen.getByRole('button', { name: 'Frame Review' }));

    expect(
      screen.getByText(/Tạo issue thủ công tạm khoá: thiếu phiên bản chính sách neo đã duyệt/)
    ).toBeDefined();
  });

  it('parses 403 error codes accurately without misidentifying OUT_OF_SCOPE as self-review', async () => {
    await renderWorkspace(
      {},
      {
        status: 403,
        body: {
          code: 'OUT_OF_SCOPE',
          message: 'Dataset nằm ngoài phạm vi được cấp quyền của bạn.',
        },
      }
    );

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    // Verifies OUT_OF_SCOPE message is shown and user is NOT accused of self-review
    expect(
      screen.getByText(/Dataset nằm ngoài phạm vi được cấp quyền của bạn/)
    ).toBeDefined();
    expect(screen.queryByText(/Anti-self-review/)).toBeNull();
  });

  it('parses 403 error codes accurately without misidentifying IDENTITY_MAPPING_MISSING as self-review', async () => {
    await renderWorkspace(
      {},
      {
        status: 403,
        body: {
          code: 'IDENTITY_MAPPING_MISSING',
          message: 'Tài khoản của bạn chưa được liên kết định danh CVAT.',
        },
      }
    );

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    expect(
      screen.getByText(/Tài khoản của bạn chưa được liên kết định danh CVAT/)
    ).toBeDefined();
    expect(screen.queryByText(/Anti-self-review/)).toBeNull();
  });

  it('displays Anti-self-review message when 403 error is SELF_REVIEW_FORBIDDEN', async () => {
    await renderWorkspace(
      {},
      {
        status: 403,
        body: {
          code: 'SELF_REVIEW_FORBIDDEN',
          message: 'Bạn không được review annotation do chính mình thực hiện.',
        },
      }
    );

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    expect(
      screen.getByText(/Anti-self-review FR-REV-03/)
    ).toBeDefined();
  });

  it('invalidates writable lease immediately upon receiving 409 LEASE_CONFLICT from mutation', async () => {
    const { api } = await renderWorkspace();

    await screen.findByText('QC-00101');

    const prevFetch = api.fetchSpy.getMockImplementation()!;
    api.fetchSpy.mockImplementation(async (request) => {
      const url = new URL(request.url);
      if (url.pathname === '/api/issues/101/decisions/') {
        return Response.json(
          { code: 'LEASE_CONFLICT', message: 'Lease đã hết hạn' },
          { status: 409 }
        );
      }
      return prevFetch(request);
    });

    const submitBtn = screen.getByRole('button', { name: 'Lưu quyết định' });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/Xung đột lease \(409 Conflict\)/)).toBeDefined();
    });

    // Lease warning banner is rendered and mutation buttons are locked
    expect(screen.getAllByText(/Quyền giữ frame đã hết hạn hoặc thuộc người khác/).length).toBeGreaterThan(0);
    expect((screen.getByRole('button', { name: 'Lưu quyết định' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('operates in read-only inspection mode when initialLease is null', async () => {
    await renderWorkspace({ initialLease: null });

    await screen.findByText('QC-00101');

    // Read-only notice displayed
    expect(screen.getByText(/Chế độ chỉ xem/)).toBeDefined();
    expect(screen.queryByText(/LeaseGrant|T-034|T-035|Plain Reviewer/)).toBeNull();

    // Mutations are locked
    expect((screen.getByRole('button', { name: 'Lưu quyết định' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Hoàn tất review frame' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('blocks completion with 422 and renders navigation buttons for undecided issue IDs', async () => {
    const { api } = await renderWorkspace();

    await screen.findByText('QC-00101');

    const prevFetch = api.fetchSpy.getMockImplementation()!;
    api.fetchSpy.mockImplementation(async (request) => {
      const url = new URL(request.url);
      if (url.pathname === '/api/frames/428/complete/') {
        return Response.json(
          {
            code: 'BUSINESS_RULE_UNMET',
            message: 'Còn issue chưa có quyết định',
            details: { undecided_issue_ids: [101] },
          },
          { status: 422 }
        );
      }
      return prevFetch(request);
    });

    const completeBtn = screen.getByRole('button', { name: 'Hoàn tất review frame' });
    fireEvent.click(completeBtn);

    await waitFor(() => {
      expect(screen.getByText(/Còn issue chưa có quyết định/)).toBeDefined();
    });

    // Jump link to undecided issue #101 is rendered
    expect(screen.getByRole('button', { name: 'Issue #101' })).toBeDefined();
  });

  it('displays genuine CVAT link and does not fabricate localhost URLs', async () => {
    await renderWorkspace();
    await screen.findByText('QC-00101');

    const cvatLink = screen.getByRole('link', { name: /Mở trong CVAT/ });
    expect((cvatLink as HTMLAnchorElement).href).toBe(
      'https://cvat.example.com/tasks/10/jobs/1?frame=428'
    );
  });

  it('blocks writes and displays lease warning when user identity does not match lease holder (holder mismatch)', async () => {
    // Lease held by user 999 while logged in user is reviewer (id 4)
    await renderWorkspace({
      initialLease: { ...activeLease, holder_user_id: 999 },
    });

    await screen.findByText('QC-00101');

    expect(
      screen.getByText(/Lease thuộc về người dùng khác \(holder mismatch\)/)
    ).toBeDefined();

    expect((screen.getByRole('button', { name: 'Lưu quyết định' }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: 'Hoàn tất review frame' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('blocks immediate writes when initial lease is already expired', async () => {
    const expiredLease: Lease = {
      ...activeLease,
      expires_at: new Date(Date.now() - 60000).toISOString(),
    };

    await renderWorkspace({ initialLease: expiredLease });

    await screen.findByText('QC-00101');

    expect(
      screen.getByText(/Lease đã hết hạn ngay từ khi khởi tạo/)
    ).toBeDefined();

    expect((screen.getByRole('button', { name: 'Lưu quyết định' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('prevents cross-frame mutation when lease frame_id does not match workspace frameId', async () => {
    const crossFrameLease: Lease = {
      ...activeLease,
      frame_id: 99999, // Mismatch with workspace frameId (428)
    };

    await renderWorkspace({ initialLease: crossFrameLease });

    await screen.findByText('QC-00101');

    expect(
      screen.getByText(/cross-frame lease forbidden/)
    ).toBeDefined();

    expect((screen.getByRole('button', { name: 'Lưu quyết định' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('discards out-of-order frame responses to prevent stale frame overwriting', async () => {
    const api = installMockAuthApi();
    await api.signIn('reviewer');

    let resolveStale: ((value: unknown) => void) | null = null;
    const stalePromise = new Promise((resolve) => {
      resolveStale = resolve;
    });

    const defaultFetch = api.fetchSpy.getMockImplementation()!;
    api.fetchSpy.mockImplementation(async (request) => {
      const url = new URL(request.url);
      if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);

      if (url.pathname === '/api/frames/428/issues/') {
        await stalePromise;
        return Response.json(baseFrameIssues);
      }
      if (url.pathname === '/api/frames/429/issues/') {
        return Response.json({
          ...baseFrameIssues,
          frame: { ...baseFrameIssues.frame, id: 429 },
          issues: [{ ...baseFrameIssues.issues[0], id: 999 }],
        });
      }
      return Response.json({}, { status: 404 });
    });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ReviewWorkspace frameId={428} initialLease={activeLease} snapshotRevision="rev-1" />
        </AuthProvider>
      </QueryClientProvider>
    );

    // Switch to frame 429 before frame 428 resolves
    rerender(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ReviewWorkspace frameId={429} initialLease={{ ...activeLease, frame_id: 429 }} snapshotRevision="rev-1" />
        </AuthProvider>
      </QueryClientProvider>
    );

    // Wait for frame 429 to render
    await screen.findByText('QC-00999');

    // Now resolve the stale 428 response
    resolveStale!(true);

    // Ensure stale frame 428 did NOT overwrite frame 429
    expect(screen.queryByText('QC-00101')).toBeNull();
    expect(screen.getByText('QC-00999')).toBeDefined();
  });

  it('synchronously treats NaN/invalid date expires_at as expired and blocks mutation', async () => {
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    const defaultFetch = api.fetchSpy.getMockImplementation()!;

    api.fetchSpy.mockImplementation(async (request) => {
      const url = new URL(request.url);
      if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
      if (url.pathname === '/api/frames/428/issues/') return Response.json(baseFrameIssues);
      return Response.json({}, { status: 404 });
    });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ReviewWorkspace
            frameId={428}
            initialLease={{ ...activeLease, expires_at: 'not-a-valid-date-nan' }}
            snapshotRevision="rev-1"
          />
        </AuthProvider>
      </QueryClientProvider>
    );

    // Should display lease warning about invalid date / expired
    await waitFor(() => {
      expect(screen.getByText(/Thời hạn lease không hợp lệ/i)).toBeInTheDocument();
    });

    // Form mutation should be blocked
    const confirmChoice = screen.getByLabelText(/Xác nhận lỗi/i);
    expect(confirmChoice).toBeDisabled();
  });

  it('discards stale issue refresh response when active issue changes while GET refresh is in flight', async () => {
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    const defaultFetch = api.fetchSpy.getMockImplementation()!;

    let resolveRefreshPromise: () => void;
    const refreshPromise = new Promise<void>((resolve) => {
      resolveRefreshPromise = resolve;
    });

    const issuesData = {
      ...baseFrameIssues,
      issues: [
        { ...baseFrameIssues.issues[0], id: 101, review_decisions: [] },
        { ...baseFrameIssues.issues[0], id: 102, review_decisions: [] },
      ],
    };

    api.fetchSpy.mockImplementation(async (request) => {
      const url = new URL(request.url);
      if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
      if (url.pathname === '/api/frames/428/issues/') return Response.json(issuesData);

      if (url.pathname === '/api/issues/101/decide/' || url.pathname === '/api/issues/101/decisions/') {
        return Response.json({
          id: 1,
          issue_id: 101,
          decision: 'confirm',
          recorded_at: new Date().toISOString(),
        }, { status: 201 });
      }

      if (url.pathname === '/api/issues/101/') {
        await refreshPromise;
        return Response.json({
          ...issuesData.issues[0],
          id: 101,
          review_decisions: [
            { id: 1, decision: 'confirm', recorded_at: new Date().toISOString() },
          ],
        });
      }

      return Response.json({}, { status: 404 });
    });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ReviewWorkspace frameId={428} initialLease={activeLease} snapshotRevision="rev-1" />
        </AuthProvider>
      </QueryClientProvider>
    );

    await screen.findByText('QC-00101');

    // Submit decision on issue 101
    fireEvent.click(screen.getByRole('button', { name: /Lưu quyết định/i }));

    // Switch to issue 102 before GET /api/issues/101/ resolves
    const nextBtn = screen.getByRole('button', { name: /Issue tiếp/i });
    fireEvent.click(nextBtn);

    // Active issue is now 102
    await screen.findByText('QC-00102');

    // Now resolve the GET /api/issues/101/ refresh response
    resolveRefreshPromise!();

    // Verify issue 102 remains the active issue without being corrupted by issue 101 refresh
    expect(screen.getByText('QC-00102')).toBeInTheDocument();
  });

  it('preserves selected issue and does not reload frame when legitimate renewal updates initialLease', async () => {
    let frameLoadCount = 0;
    const api = installMockAuthApi();
    await api.signIn('reviewer');
    const defaultFetch = api.fetchSpy.getMockImplementation()!;

    const issuesData = {
      ...baseFrameIssues,
      issues: [
        { ...baseFrameIssues.issues[0], id: 101, review_decisions: [] },
        { ...baseFrameIssues.issues[0], id: 102, review_decisions: [] },
      ],
    };

    api.fetchSpy.mockImplementation(async (request) => {
      const url = new URL(request.url);
      if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);

      if (url.pathname === '/api/frames/428/issues/') {
        frameLoadCount++;
        return Response.json(issuesData);
      }

      return Response.json({}, { status: 404 });
    });

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ReviewWorkspace frameId={428} initialLease={activeLease} snapshotRevision="rev-1" />
        </AuthProvider>
      </QueryClientProvider>
    );

    await screen.findByText('QC-00101');
    expect(frameLoadCount).toBe(1);

    // Switch to issue 102
    const nextBtn = screen.getByRole('button', { name: /^Issue tiếp/i });
    fireEvent.click(nextBtn);
    await screen.findByText('QC-00102');

    // Now simulate renewal: activeGrant updates lease with new expires_at, same lease id 77
    const renewedLease: Lease = {
      ...activeLease,
      expires_at: new Date(Date.now() + 1200000).toISOString(),
    };

    rerender(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ReviewWorkspace frameId={428} initialLease={renewedLease} snapshotRevision="rev-1" />
        </AuthProvider>
      </QueryClientProvider>
    );

    // Frame must NOT be reloaded
    expect(frameLoadCount).toBe(1);

    // Selected issue must remain QC-00102, not reset to QC-00101!
    expect(screen.getByText('QC-00102')).toBeInTheDocument();
  });
});
