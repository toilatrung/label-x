import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '@/lib/auth/auth-context';
import { ReviewWorkspace, resolveAnchorPolicy } from '@/components/review/ReviewWorkspace';
import { ReviewDecisionForm, generateCanonicalUUID } from '@/components/review/ReviewDecisionForm';
import { ReviewManualIssueModal } from '@/components/review/ReviewManualIssueModal';
import { ReviewCanvas, getSvgScale } from '@/components/review/ReviewCanvas';
import { ReviewEvidenceTable } from '@/components/review/ReviewEvidenceTable';
import { ReviewGuidelineLookup } from '@/components/review/ReviewGuidelineLookup';
import { installMockAuthApi } from './helpers/mock-api';
import type { components } from '@/lib/api/contract';

type FrameIssues = components['schemas']['FrameIssues'];
type Lease = components['schemas']['Lease'];
type Issue = components['schemas']['Issue'];

const canonicalUuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const testIssueE2: Issue = {
  id: 201,
  family: 'E2',
  origin: 'engine',
  state: 'in_review',
  n_i: 1,
  anchor: {
    kind: 'annotation',
    policy_version: 'anchor-v1',
    objects: [{ namespace: 'cvat_shape', id: 'shape-99' }],
    bbox: { x1: 100, y1: 100, x2: 250, y2: 250 },
  },
  evidence: [
    {
      engine: 'detector',
      prediction_class: 'truck',
      confidence: 0.92,
      iou: 0.81,
      prediction_bbox: { x1: 95, y1: 95, x2: 255, y2: 255 },
    },
  ],
  links: [],
  review_decisions: [
    {
      id: 55,
      issue_id: 201,
      actor_user_id: 4,
      actor_role: 'reviewer',
      decision: 'uncertain',
      revision: 'rev-prior-1',
      reason: 'Cần kiểm tra thêm ánh sáng',
      rule_ids: [],
      reference_version: null,
      reference_match_status: 'not_evaluated',
      reference_error_ids: [],
      recorded_at: '2026-10-10T12:00:00Z',
    },
  ],
};

const baseFrameIssues: FrameIssues = {
  frame: {
    id: 500,
    run_id: 10,
    frame_key: { cvat_task_id: 2, frame_number: 500 },
    review_state: 'in_review',
    missing_evidence: false,
    width: 1280,
    height: 720,
    image_url: 'https://example.com/frame-500.jpg',
    cvat_deep_link: 'https://cvat.example.com/tasks/2/jobs/1?frame=500',
  },
  guideline_version: 'v2.1',
  engines: [
    { engine: 'detector', status: 'checked' },
    { engine: 'vlm', status: 'checked' },
  ],
  issues: [testIssueE2],
};

const activeLease: Lease = {
  id: 88,
  frame_id: 500,
  holder_user_id: 4,
  expires_at: new Date(Date.now() + 600000).toISOString(),
};

describe('T-035 PR130 Interface Integration Tests (T-037 Preparation)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('RFC 4122 v4 Canonical UUID Generator', () => {
    it('generates a valid canonical v4 UUID without Date.now or custom prefix', () => {
      const uuid1 = generateCanonicalUUID();
      const uuid2 = generateCanonicalUUID();

      expect(uuid1).toMatch(canonicalUuidRegex);
      expect(uuid2).toMatch(canonicalUuidRegex);
      expect(uuid1).not.toBe(uuid2);
      expect(uuid1).not.toMatch(/^dec-/);
      expect(uuid1).not.toMatch(/^manual-/);
    });
  });

  describe('resolveAnchorPolicy unit logic', () => {
    it('returns anchor-v1 when propPolicy is anchor-v1 and issues match', () => {
      const res = resolveAnchorPolicy('anchor-v1', [testIssueE2]);
      expect(res.policy).toBe('anchor-v1');
      expect(res.error).toBeUndefined();
    });

    it('rejects unsupported propPolicy', () => {
      const res = resolveAnchorPolicy('anchor-v2-experimental', [testIssueE2]);
      expect(res.policy).toBeNull();
      expect(res.error).toMatch(/không được hỗ trợ/);
    });

    it('infers anchor-v1 from consistent server issues when propPolicy is omitted', () => {
      const res = resolveAnchorPolicy(null, [testIssueE2]);
      expect(res.policy).toBe('anchor-v1');
      expect(res.error).toBeUndefined();
    });

    it('locks manual policy on zero-issue frame when propPolicy is omitted', () => {
      const res = resolveAnchorPolicy(null, []);
      expect(res.policy).toBeNull();
      expect(res.error).toMatch(/frame chưa có issue để lấy phiên bản/);
    });

    it('locks manual policy when server issues have conflicting policy versions', () => {
      const conflictingIssue: Issue = {
        ...testIssueE2,
        id: 202,
        anchor: { ...testIssueE2.anchor, policy_version: 'anchor-v2' },
      };
      const res = resolveAnchorPolicy(null, [testIssueE2, conflictingIssue]);
      expect(res.policy).toBeNull();
      expect(res.error).toMatch(/xung đột phiên bản chính sách/);
    });
  });

  describe('ReviewDecisionForm T-035 contract behavior', () => {
    it('renders 4 direct actions and keeps request_fix visible but disabled (T-040 rework)', () => {
      render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={vi.fn()}
        />
      );

      expect(screen.getByLabelText('Xác nhận lỗi')).toBeInTheDocument();
      expect(screen.getByLabelText('Bác bỏ')).toBeInTheDocument();
      expect(screen.getByLabelText('Chưa chắc chắn')).toBeInTheDocument();
      expect(screen.getByLabelText('Chuyển cấp trên')).toBeInTheDocument();

      const reworkRadio = screen.getByLabelText(/Yêu cầu sửa/i);
      expect(reworkRadio).toBeInTheDocument();
      expect(reworkRadio).toBeDisabled();
      expect(reworkRadio).toHaveAttribute('aria-disabled', 'true');
    });

    it('dispatches canonical RFC 4122 v4 UUID in Idempotency-Key header', async () => {
      let capturedIdempotencyKey: string | null = null;
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/') {
          capturedIdempotencyKey = request.headers.get('Idempotency-Key');
          return Response.json(
            { id: 1, issue_id: 201, action: 'confirm', revision: 'sha256:abc' },
            { status: 201 }
          );
        }
        if (url.pathname === '/api/issues/201/') {
          return Response.json(testIssueE2);
        }
        return Response.json({}, { status: 404 });
      });

      render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={vi.fn()}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: 'Lưu quyết định' }));

      await waitFor(() => {
        expect(screen.getByText(/Quyết định đã được lưu thành công trên máy chủ/i)).toBeInTheDocument();
      });

      expect(capturedIdempotencyKey).not.toBeNull();
      expect(capturedIdempotencyKey!).toMatch(canonicalUuidRegex);
    });

    it('reuses the exact same Idempotency-Key on uncertain network retry', async () => {
      const keysUsed: string[] = [];
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      let attempt = 0;
      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/') {
          keysUsed.push(request.headers.get('Idempotency-Key')!);
          attempt++;
          if (attempt === 1) {
            // First attempt fails with network error
            throw new Error('Network failure');
          }
          return Response.json(
            { id: 1, issue_id: 201, action: 'confirm', revision: 'sha256:abc' },
            { status: 201 }
          );
        }
        if (url.pathname === '/api/issues/201/') {
          return Response.json(testIssueE2);
        }
        return Response.json({}, { status: 404 });
      });

      render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={vi.fn()}
        />
      );

      // Attempt 1: fails
      fireEvent.click(screen.getByRole('button', { name: 'Lưu quyết định' }));
      await waitFor(() => {
        expect(screen.getByText(/Lỗi kết nối mạng khi gửi quyết định/i)).toBeInTheDocument();
      });

      // Attempt 2: retry same operation
      fireEvent.click(screen.getByRole('button', { name: 'Lưu quyết định' }));
      await waitFor(() => {
        expect(screen.getByText(/Quyết định đã được lưu thành công trên máy chủ/i)).toBeInTheDocument();
      });

      expect(keysUsed.length).toBe(2);
      expect(keysUsed[0]).toBe(keysUsed[1]);
      expect(keysUsed[0]).toMatch(canonicalUuidRegex);
    });

    it('handles 409 INVALID_TRANSITION without invalidating lease', async () => {
      const onLeaseConflict = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/') {
          return Response.json(
            {
              code: 'INVALID_TRANSITION',
              message: 'Revision mismatch: snapshot revision does not match issue state.',
            },
            { status: 409 }
          );
        }
        return Response.json({}, { status: 404 });
      });

      render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:stale-rev"
          isLeaseExpired={false}
          onDecisionSaved={vi.fn()}
          onLeaseConflict={onLeaseConflict}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: 'Lưu quyết định' }));

      await waitFor(() => {
        expect(screen.getByText(/INVALID_TRANSITION/i)).toBeInTheDocument();
      });

      // Crucial: Lease conflict handler must NOT be called on INVALID_TRANSITION
      expect(onLeaseConflict).not.toHaveBeenCalled();
      // Form button should still be enabled (lease remains valid)
      expect(screen.getByRole('button', { name: 'Lưu quyết định' })).not.toBeDisabled();
    });

    it('handles 409 IDEMPOTENCY_KEY_REUSED without invalidating lease', async () => {
      const onLeaseConflict = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/') {
          return Response.json(
            {
              code: 'IDEMPOTENCY_KEY_REUSED',
              message: 'Khóa Idempotency-Key đã được tái sử dụng.',
            },
            { status: 409 }
          );
        }
        return Response.json({}, { status: 404 });
      });

      render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc"
          isLeaseExpired={false}
          onDecisionSaved={vi.fn()}
          onLeaseConflict={onLeaseConflict}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: 'Lưu quyết định' }));

      await waitFor(() => {
        expect(screen.getByText(/IDEMPOTENCY_KEY_REUSED/i)).toBeInTheDocument();
      });

      expect(onLeaseConflict).not.toHaveBeenCalled();
    });

    it('requires mandatory override_reason for Super Admin', async () => {
      render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc"
          isLeaseExpired={false}
          isSuperAdmin={true}
          onDecisionSaved={vi.fn()}
        />
      );

      expect(screen.getByLabelText(/Lý do Super Admin can thiệp/i)).toBeInTheDocument();

      // Submit without entering override_reason
      fireEvent.click(screen.getByRole('button', { name: 'Lưu quyết định' }));

      expect(
        screen.getByText(/Super Admin bắt buộc phải nhập lý do can thiệp/i)
      ).toBeInTheDocument();
    });

    it('preserves successful server save even if subsequent GET refresh fails', async () => {
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/') {
          return Response.json(
            { id: 1, issue_id: 201, action: 'confirm', revision: 'sha256:abc' },
            { status: 201 }
          );
        }
        if (url.pathname === '/api/issues/201/') {
          return Response.json({ code: 'SERVER_ERROR' }, { status: 500 });
        }
        return Response.json({}, { status: 404 });
      });

      render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc"
          isLeaseExpired={false}
          onDecisionSaved={vi.fn()}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: 'Lưu quyết định' }));

      await waitFor(() => {
        // Success message must stay preserved honestly
        expect(
          screen.getByText(/Quyết định đã được lưu thành công trên máy chủ/i)
        ).toBeInTheDocument();
        // Server refresh warning shown without destroying state
        expect(
          screen.getByText(/không thể làm mới dữ liệu issue/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe('ReviewManualIssueModal validations', () => {
    it('rejects description exceeding 2000 characters', async () => {
      render(
        <ReviewManualIssueModal
          frameId={500}
          leaseId={88}
          anchorPolicyVersion="anchor-v1"
          selectedObject={{ namespace: 'cvat_shape', id: 'shape-1' }}
          onClose={vi.fn()}
          onCreated={vi.fn()}
        />
      );

      const textarea = screen.getByLabelText(/Mô tả chi tiết/i);
      fireEvent.change(textarea, { target: { value: 'a'.repeat(2001) } });
      fireEvent.click(screen.getByRole('button', { name: 'Tạo issue' }));

      expect(
        screen.getByText(/Mô tả chi tiết không được vượt quá 2000 ký tự/i)
      ).toBeInTheDocument();
    });

    it('rejects non-cvat_shape object namespace (e.g. detector)', async () => {
      render(
        <ReviewManualIssueModal
          frameId={500}
          leaseId={88}
          anchorPolicyVersion="anchor-v1"
          selectedObject={{ namespace: 'detector', id: '10:0' }}
          onClose={vi.fn()}
          onCreated={vi.fn()}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: 'Tạo issue' }));

      expect(
        screen.getByText(/Chỉ đối tượng cvat_shape từ khung hình mới hợp lệ làm neo manual_object/i)
      ).toBeInTheDocument();
    });

    it('handles 409 ISSUE_EXISTS without invalidating lease', async () => {
      const onLeaseConflict = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/') {
          return Response.json(
            { code: 'ISSUE_EXISTS', message: 'Issue đã tồn tại trên khung hình.' },
            { status: 409 }
          );
        }
        return Response.json({}, { status: 404 });
      });

      render(
        <ReviewManualIssueModal
          frameId={500}
          leaseId={88}
          anchorPolicyVersion="anchor-v1"
          selectedObject={{ namespace: 'cvat_shape', id: 'shape-1' }}
          onClose={vi.fn()}
          onCreated={vi.fn()}
          onLeaseConflict={onLeaseConflict}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: 'Tạo issue' }));

      await waitFor(() => {
        expect(screen.getByText(/ISSUE_EXISTS/i)).toBeInTheDocument();
      });

      expect(onLeaseConflict).not.toHaveBeenCalled();
    });
  });

  describe('ReviewWorkspace Snapshot Resolution by Role', () => {
    it('does NOT request snapshot endpoint for plain Reviewer and shows clear gap message', async () => {
      let snapshotEndpointHit = false;
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/frames/500/issues/') return Response.json(baseFrameIssues);
        if (url.pathname.startsWith('/api/snapshots/')) {
          snapshotEndpointHit = true;
          return Response.json({}, { status: 403 });
        }
        return Response.json({}, { status: 404 });
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ReviewWorkspace frameId={500} initialLease={activeLease} runId={10} />
          </AuthProvider>
        </QueryClientProvider>
      );

      await screen.findByText('QC-00201');

      // Crucial: Snapshot endpoint must NOT be called for plain Reviewer
      expect(snapshotEndpointHit).toBe(false);

      expect(
        screen.getByText(/tài khoản Reviewer chưa được cấp quyền đọc Snapshot/i)
      ).toBeInTheDocument();
    });

    it('retrieves locked revision for eligible QA Lead session', async () => {
      let snapshotEndpointHit = false;
      const api = installMockAuthApi();
      await api.signIn('qalead');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/frames/500/issues/') return Response.json(baseFrameIssues);
        if (url.pathname === '/api/runs/10/') {
          return Response.json({ id: 10, snapshot_id: 42 });
        }
        if (url.pathname === '/api/snapshots/42/') {
          snapshotEndpointHit = true;
          return Response.json({
            id: 42,
            dataset_id: 1,
            status: 'locked',
            revision_hash: 'sha256:locked-hash-999',
          });
        }
        return Response.json({}, { status: 404 });
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ReviewWorkspace
              frameId={500}
              initialLease={{ ...activeLease, holder_user_id: 2 }}
              runId={10}
              datasetId={1}
            />
          </AuthProvider>
        </QueryClientProvider>
      );

      await screen.findByText('QC-00201');

      await waitFor(() => {
        expect(snapshotEndpointHit).toBe(true);
      });

      // Decision button should be enabled once locked revision is resolved
      await waitFor(() => {
        const submitBtn = screen.getByRole('button', { name: 'Lưu quyết định' });
        expect(submitBtn).not.toBeDisabled();
      });
    });

    it('rejects frame response with mismatched frame id or run id', async () => {
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/frames/500/issues/') {
          // Returns frame with run_id 99 instead of expected 10
          return Response.json({
            ...baseFrameIssues,
            frame: { ...baseFrameIssues.frame, run_id: 99 },
          });
        }
        return Response.json({}, { status: 404 });
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ReviewWorkspace frameId={500} initialLease={activeLease} runId={10} />
          </AuthProvider>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(
          screen.getByText(/Dữ liệu khung hình không thuộc run đang chọn/i)
        ).toBeInTheDocument();
      });

      // Editable workspace must not be rendered
      expect(screen.queryByText('QC-00201')).not.toBeInTheDocument();
    });
  });

  describe('Non-in_review state enforcement and Save & Next behavior', () => {
    it.each([
      'confirmed',
      'rejected',
      'escalated',
      'resolved',
      'pending_review',
      'fix_pending',
    ] as const)('blocks direct decision submission and forbids POST when issue.state is "%s"', async (nonInReviewState) => {
      let postDispatched = false;
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname.includes('/decisions/')) {
          postDispatched = true;
          return Response.json({ id: 1, action: 'confirm' }, { status: 201 });
        }
        return Response.json({}, { status: 404 });
      });

      const issueInState: Issue = {
        ...testIssueE2,
        state: nonInReviewState,
      };

      const { container } = render(
        <ReviewDecisionForm
          issue={issueInState}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={vi.fn()}
        />
      );

      // Warning callout must be shown
      expect(
        screen.getByText(new RegExp(`Chỉ issue ở trạng thái.*Đang review.*mới lưu được quyết định`, 'i'))
      ).toBeInTheDocument();

      // Submit button must be disabled
      const submitBtn = screen.getByRole('button', { name: 'Lưu quyết định' });
      expect(submitBtn).toBeDisabled();

      // Form submission attempt must be blocked by validation
      const form = container.querySelector('form');
      if (form) {
        fireEvent.submit(form);
      }

      // Meaningful regression check: POST decisions endpoint must NEVER be called
      expect(postDispatched).toBe(false);

      // Authoritative saved decision history must remain visible
      expect(screen.getByText('Cần kiểm tra thêm ánh sáng')).toBeInTheDocument();
    });

    it('advances via onNextIssue only after successful authoritative save and reconciliation', async () => {
      const onDecisionSaved = vi.fn();
      const onNextIssue = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/') {
          return Response.json(
            { id: 99, issue_id: 201, action: 'confirm', revision: 'sha256:abc123rev' },
            { status: 201 }
          );
        }
        if (url.pathname === '/api/issues/201/') {
          return Response.json({
            ...testIssueE2,
            state: 'in_review',
            review_decisions: [
              ...testIssueE2.review_decisions,
              {
                id: 99,
                issue_id: 201,
                actor_user_id: 4,
                actor_role: 'reviewer',
                decision: 'confirm',
                revision: 'sha256:abc123rev',
                reason: '',
                rule_ids: [],
                reference_version: null,
                reference_match_status: 'not_evaluated',
                reference_error_ids: [],
                recorded_at: '2026-10-11T12:00:00Z',
              },
            ],
          });
        }
        return Response.json({}, { status: 404 });
      });

      render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={onDecisionSaved}
          onNextIssue={onNextIssue}
          hasNext={true}
        />
      );

      const saveAndNextBtn = screen.getByRole('button', { name: 'Lưu và chuyển issue tiếp ›' });
      fireEvent.click(saveAndNextBtn);

      await waitFor(() => {
        expect(onDecisionSaved).toHaveBeenCalled();
        expect(onNextIssue).toHaveBeenCalledTimes(1);
      });
    });

    it('does NOT advance via onNextIssue if decision POST fails', async () => {
      const onDecisionSaved = vi.fn();
      const onNextIssue = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/') {
          return Response.json(
            { code: 'LEASE_CONFLICT', message: 'Lease expired.' },
            { status: 409 }
          );
        }
        return Response.json({}, { status: 404 });
      });

      render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={onDecisionSaved}
          onNextIssue={onNextIssue}
          hasNext={true}
        />
      );

      const saveAndNextBtn = screen.getByRole('button', { name: 'Lưu và chuyển issue tiếp ›' });
      fireEvent.click(saveAndNextBtn);

      await waitFor(() => {
        expect(screen.getByText(/Xung đột lease/i)).toBeInTheDocument();
      });

      // Crucial: Must NOT advance when save failed
      expect(onDecisionSaved).not.toHaveBeenCalled();
      expect(onNextIssue).not.toHaveBeenCalled();
    });

    it('saves decision without advancing when clicking secondary "Lưu quyết định"', async () => {
      const onDecisionSaved = vi.fn();
      const onNextIssue = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/') {
          return Response.json(
            { id: 101, issue_id: 201, action: 'confirm', revision: 'sha256:abc123rev' },
            { status: 201 }
          );
        }
        if (url.pathname === '/api/issues/201/') {
          return Response.json(testIssueE2);
        }
        return Response.json({}, { status: 404 });
      });

      render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={onDecisionSaved}
          onNextIssue={onNextIssue}
          hasNext={true}
        />
      );

      // Click the plain "Lưu quyết định" button
      const saveOnlyBtn = screen.getByRole('button', { name: 'Lưu quyết định' });
      fireEvent.click(saveOnlyBtn);

      await waitFor(() => {
        expect(onDecisionSaved).toHaveBeenCalled();
      });

      // Must NOT advance
      expect(onNextIssue).not.toHaveBeenCalled();
    });

    it('discards in-flight decision submission when lease changes without another submit', async () => {
      const onDecisionSaved = vi.fn();
      const onLeaseConflict = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      let resolvePost: (resp: Response) => void;
      const postPromise = new Promise<Response>((resolve) => {
        resolvePost = resolve;
      });

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/') {
          return postPromise;
        }
        return Response.json({}, { status: 404 });
      });

      const { rerender } = render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={onDecisionSaved}
          onLeaseConflict={onLeaseConflict}
          hasNext={false}
        />
      );

      const submitBtn = screen.getByRole('button', { name: 'Lưu quyết định' });
      fireEvent.click(submitBtn);

      // Now lease changes to a NEW lease ID while request is in flight
      const newLease: Lease = {
        id: 999,
        frame_id: 500,
        holder_user_id: 4,
        expires_at: new Date(Date.now() + 600000).toISOString(),
      };
      rerender(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={newLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={onDecisionSaved}
          onLeaseConflict={onLeaseConflict}
          hasNext={false}
        />
      );

      // Late resolve with 409 LEASE_CONFLICT from the old lease request
      resolvePost!(
        Response.json(
          { code: 'LEASE_CONFLICT', message: 'Old lease expired.' },
          { status: 409 }
        )
      );
      await postPromise;

      // Old lease 409 MUST NOT trigger conflict callback on new lease
      expect(onLeaseConflict).not.toHaveBeenCalled();
      expect(onDecisionSaved).not.toHaveBeenCalled();
    });

    it('discards in-flight complete request when lease changes before complete resolves', async () => {
      const onFrameCompleted = vi.fn();
      const onLeaseConflict = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      let resolveComplete: (resp: Response) => void;
      const completePromise = new Promise<Response>((resolve) => {
        resolveComplete = resolve;
      });

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/frames/500/issues/') return Response.json(baseFrameIssues);
        if (url.pathname === '/api/frames/500/complete/') {
          return completePromise;
        }
        return Response.json({}, { status: 404 });
      });

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ReviewWorkspace
              frameId={500}
              initialLease={activeLease}
              snapshotRevision="rev-1"
              onFrameCompleted={onFrameCompleted}
              onLeaseConflict={onLeaseConflict}
            />
          </AuthProvider>
        </QueryClientProvider>
      );

      await screen.findByText('QC-00201');

      // Click complete button
      const completeBtn = screen.getByRole('button', { name: /Hoàn tất review frame/i });
      fireEvent.click(completeBtn);

      // Now lease changes while complete request is in flight
      const newLease: Lease = {
        ...activeLease,
        id: 9999,
      };

      rerender(
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <ReviewWorkspace
              frameId={500}
              initialLease={newLease}
              snapshotRevision="rev-1"
              onFrameCompleted={onFrameCompleted}
              onLeaseConflict={onLeaseConflict}
            />
          </AuthProvider>
        </QueryClientProvider>
      );

      // Resolve old complete request with 409 LEASE_CONFLICT
      resolveComplete!(
        Response.json(
          { code: 'LEASE_CONFLICT', message: 'Old lease expired.' },
          { status: 409 }
        )
      );
      await completePromise;

      // Stale completion response MUST NOT trigger completion callback or conflict on new lease
      expect(onFrameCompleted).not.toHaveBeenCalled();
      expect(onLeaseConflict).not.toHaveBeenCalled();
    });

    it('enables submit on new issue after meaningful context switch during slow POST without applying old response', async () => {
      const onDecisionSaved = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      let resolvePost201: (resp: Response) => void;
      const postPromise201 = new Promise<Response>((resolve) => {
        resolvePost201 = resolve;
      });

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/') {
          return postPromise201;
        }
        return Response.json({}, { status: 404 });
      });

      const { rerender } = render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={onDecisionSaved}
          hasNext={true}
        />
      );

      // Start submitting on issue 201
      const saveBtn201 = screen.getByRole('button', { name: 'Lưu quyết định' });
      fireEvent.click(saveBtn201);

      // Issue 201 is submitting
      screen.getAllByRole('button', { name: 'Đang lưu...' }).forEach((button) => {
        expect(button).toBeDisabled();
      });

      // Switch context to issue 202 while issue 201 POST is in flight
      const issue202: Issue = {
        ...testIssueE2,
        id: 202,
        state: 'in_review',
      };

      rerender(
        <ReviewDecisionForm
          issue={issue202}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={onDecisionSaved}
          hasNext={true}
        />
      );

      // Meaningful context switch must reset submitMode: new issue 202 must NOT be permanently busy!
      const saveBtn202 = screen.getByRole('button', { name: 'Lưu quyết định' });
      expect(saveBtn202).not.toBeDisabled();
      expect(saveBtn202.textContent).toBe('Lưu quyết định');

      // Now resolve the late slow POST for issue 201
      resolvePost201!(
        Response.json(
          { id: 991, issue_id: 201, action: 'confirm', revision: 'sha256:abc123rev', created_at: '2026-10-11T14:59:00Z' },
          { status: 201 }
        )
      );
      await postPromise201;

      // Old response from issue 201 MUST NOT be applied to issue 202
      expect(onDecisionSaved).not.toHaveBeenCalled();
    });

    it('displays server receipt with timestamp on POST success + GET failure, prevents duplicate POST, and retains receipt on lease expiry', async () => {
      let postCount = 0;
      let getCount = 0;
      const onDecisionSaved = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      const serverReceiptCreatedAt = '2026-10-11T14:30:45.000Z';
      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/201/decisions/' && request.method === 'POST') {
          postCount++;
          return Response.json(
            {
              id: 888,
              issue_id: 201,
              action: 'confirm',
              revision: 'sha256:abc123rev',
              created_at: serverReceiptCreatedAt,
            },
            { status: 201 }
          );
        }
        if (url.pathname === '/api/issues/201/' && request.method === 'GET') {
          getCount++;
          // First GET fails after successful POST
          if (getCount === 1) {
            return Response.json({ code: 'INTERNAL_ERROR', message: 'Failed to fetch issue.' }, { status: 500 });
          }
          // Second GET succeeds (from retry refresh)
          return Response.json({
            ...testIssueE2,
            id: 201,
            state: 'in_review',
            review_decisions: [
              ...testIssueE2.review_decisions,
              {
                id: 888,
                issue_id: 201,
                actor_user_id: 4,
                actor_role: 'reviewer',
                decision: 'confirm',
                revision: 'sha256:abc123rev',
                reason: '',
                rule_ids: [],
                reference_version: null,
                reference_match_status: 'not_evaluated',
                reference_error_ids: [],
                recorded_at: serverReceiptCreatedAt,
              },
            ],
          });
        }
        return Response.json({}, { status: 404 });
      });

      const { rerender } = render(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={false}
          onDecisionSaved={onDecisionSaved}
          hasNext={false}
        />
      );

      const submitBtn = screen.getByRole('button', { name: 'Lưu quyết định' });
      fireEvent.click(submitBtn);

      // Wait for POST to succeed and GET to fail
      await waitFor(() => {
        expect(screen.getByText(/Biên nhận máy chủ \(POST Receipt #888\)/i)).toBeInTheDocument();
      });

      // 1. Raw decision delivered to collector callback even when GET fails
      expect(onDecisionSaved).toHaveBeenCalledWith(
        testIssueE2,
        expect.objectContaining({ id: 888, action: 'confirm', created_at: serverReceiptCreatedAt })
      );

      // 2. Real server timestamp is visible in the receipt
      expect(screen.getAllByText(new RegExp(serverReceiptCreatedAt)).length).toBeGreaterThan(0);

      // 3. Authoritative history count is unchanged (no fabricated ReviewDecision added to history list)
      expect(screen.getByText('Cần kiểm tra thêm ánh sáng')).toBeInTheDocument();
      expect(screen.getByText(/Đã có 1 quyết định/i)).toBeInTheDocument();

      // 4. Duplicate POST resubmission is blocked while receipt is active
      expect(screen.getByRole('button', { name: 'Lưu quyết định' })).toBeDisabled();

      // 5. Expiry retains the saved receipt for the same issue
      rerender(
        <ReviewDecisionForm
          issue={testIssueE2}
          lease={activeLease}
          snapshotRevision="sha256:abc123rev"
          isLeaseExpired={true}
          onDecisionSaved={onDecisionSaved}
          hasNext={false}
        />
      );

      expect(screen.getByText(/Biên nhận máy chủ \(POST Receipt #888\)/i)).toBeInTheDocument();
      expect(screen.getAllByText(new RegExp(serverReceiptCreatedAt)).length).toBeGreaterThan(0);

      // 6. Explicit retry refresh executes GET only, never repeats POST
      const retryRefreshBtn = screen.getByRole('button', { name: /Thử làm mới lại dữ liệu issue/i });
      fireEvent.click(retryRefreshBtn);

      await waitFor(() => {
        expect(getCount).toBe(2);
      });
      expect(postCount).toBe(1); // Crucial: POST was NOT repeated!
    });

    it('re-fetches frame issues under new authenticated user context and skips API for null user', async () => {
      let frameIssuesFetchCount = 0;
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/frames/500/issues/') {
          frameIssuesFetchCount++;
          return Response.json(baseFrameIssues);
        }
        return Response.json({}, { status: 404 });
      });

      function TestAuthControls() {
        const { login, logout } = useAuth();
        return (
          <div>
            <button onClick={() => void login({ username: 'qalead', password: 'password123' })}>Switch User</button>
            <button onClick={() => void logout()}>Logout User</button>
          </div>
        );
      }

      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <TestAuthControls />
            <ReviewWorkspace
              frameId={500}
              initialLease={activeLease}
              snapshotRevision="rev-1"
            />
          </AuthProvider>
        </QueryClientProvider>
      );

      await screen.findByText('QC-00201');
      expect(frameIssuesFetchCount).toBe(1);

      // Switching user context to QA Lead (user id: 2)
      fireEvent.click(screen.getByRole('button', { name: 'Switch User' }));

      // Frame issues should be re-fetched under the new authenticated context
      await waitFor(() => {
        expect(frameIssuesFetchCount).toBe(2);
      });

      // Now logout (unauthenticated / null user)
      fireEvent.click(screen.getByRole('button', { name: 'Logout User' }));

      // For null user: API must NOT be called
      await waitFor(() => {
        expect(frameIssuesFetchCount).toBe(2);
      });
    });
  });

  describe('ReviewManualIssueModal context guards', () => {
    it('discards in-flight manual issue creation when frame changes while pending', async () => {
      const onCreated = vi.fn();
      const onClose = vi.fn();
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      let resolveCreate: (resp: Response) => void;
      const createPromise = new Promise<Response>((resolve) => {
        resolveCreate = resolve;
      });

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/issues/' && request.method === 'POST') {
          return createPromise;
        }
        return Response.json({}, { status: 404 });
      });

      const { rerender } = render(
        <ReviewManualIssueModal
          frameId={500}
          leaseId={77}
          anchorPolicyVersion="anchor-v1"
          drawnRegion={{ x1: 50, y1: 50, x2: 150, y2: 150 }}
          frameWidth={960}
          frameHeight={540}
          onClose={onClose}
          onCreated={onCreated}
        />
      );

      const submitBtn = screen.getByRole('button', { name: /Tạo issue/i });
      fireEvent.click(submitBtn);

      // Frame changes to 600 while request is in flight
      rerender(
        <ReviewManualIssueModal
          frameId={600}
          leaseId={77}
          anchorPolicyVersion="anchor-v1"
          drawnRegion={{ x1: 50, y1: 50, x2: 150, y2: 150 }}
          frameWidth={960}
          frameHeight={540}
          onClose={onClose}
          onCreated={onCreated}
        />
      );

      // Resolve old creation request
      resolveCreate!(
        Response.json(
          { id: 999, frame_id: 500, family: 'E2', origin: 'reviewer', state: 'in_review' },
          { status: 201 }
        )
      );
      await createPromise;

      // Must NOT invoke onCreated or onClose for old frame
      expect(onCreated).not.toHaveBeenCalled();
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  describe('ReviewCanvas pan scaling and drawing boundaries', () => {
    it('calculates SVG letterbox scale correctly for responsive viewports', () => {
      // 960x540 viewBox rendered in a 480x270 rect -> scale is 0.5
      const rect = { width: 480, height: 270, left: 0, top: 0, right: 480, bottom: 270 } as DOMRect;
      const scale = getSvgScale(rect, 960, 540);
      expect(scale).toBe(0.5);
    });

    it('cancels region drawing when mouse is released outside SVG viewport', () => {
      const onCreateRegion = vi.fn();
      render(
        <ReviewCanvas
          frame={{
            id: 500,
            run_id: 1,
            frame_key: { cvat_task_id: 1, frame_number: 1 },
            review_state: 'in_review',
            missing_evidence: false,
            width: 960,
            height: 540,
            image_url: 'https://example.com/frame.jpg',
          }}
          issues={[]}
          selectedIssueId={null}
          reviewMode="frame"
          showAnnotations={true}
          showPredictions={true}
          onSelectIssue={vi.fn()}
          zoom={1}
          pan={{ x: 0, y: 0 }}
          onZoomChange={vi.fn()}
          onPanChange={vi.fn()}
          onCreateRegionManualIssue={onCreateRegion}
        />
      );

      const svg = screen.getByRole('img', { name: /Khung hình annotation và prediction/i });

      // Mouse down inside SVG to start drawing
      fireEvent.mouseDown(svg, { button: 0, clientX: 100, clientY: 100 });

      // Move mouse
      fireEvent(window, new MouseEvent('mousemove', { clientX: 200, clientY: 200 }));

      // Release mouse WAY OUTSIDE SVG (e.g. at x: -500, y: -500)
      fireEvent(window, new MouseEvent('mouseup', { clientX: -500, clientY: -500 }));

      // Region creation should be cancelled, NOT created
      expect(onCreateRegion).not.toHaveBeenCalled();
    });

    it('disables region drawing and warns when frame dimensions are missing/invalid', () => {
      const onCreateRegion = vi.fn();
      render(
        <ReviewCanvas
          frame={{
            id: 500,
            run_id: 1,
            frame_key: { cvat_task_id: 1, frame_number: 1 },
            review_state: 'in_review',
            missing_evidence: false,
            width: 0, // Invalid width
            height: 0, // Invalid height
            image_url: 'https://example.com/frame.jpg',
          }}
          issues={[]}
          selectedIssueId={null}
          reviewMode="frame"
          showAnnotations={true}
          showPredictions={true}
          onSelectIssue={vi.fn()}
          zoom={1}
          pan={{ x: 0, y: 0 }}
          onZoomChange={vi.fn()}
          onPanChange={vi.fn()}
          onCreateRegionManualIssue={onCreateRegion}
        />
      );

      // Warning overlay must be displayed
      expect(screen.getByText(/Kích thước khung hình chưa xác định từ API/i)).toBeInTheDocument();

      const svg = screen.getByRole('img', { name: /Khung hình annotation và prediction/i });
      fireEvent.mouseDown(svg, { button: 0, clientX: 100, clientY: 100 });
      fireEvent(window, new MouseEvent('mousemove', { clientX: 200, clientY: 200 }));
      fireEvent(window, new MouseEvent('mouseup', { clientX: 200, clientY: 200 }));

      // Must NOT create region with fallback coordinates
      expect(onCreateRegion).not.toHaveBeenCalled();
    });
  });

  describe('ReviewEvidenceTable schema completeness', () => {
    it('displays prediction_bbox, rule_id, 0 confidence, 0 iou, and independent actual', () => {
      render(
        <ReviewEvidenceTable
          evidenceList={[
            {
              engine: 'detector',
              prediction_class: 'bicycle',
              confidence: 0,
              iou: 0,
              prediction_bbox: { x1: 12, y1: 34, x2: 56, y2: 78 },
              rule_id: 'RULE-VEH-01',
              actual: 'bicycle_detected',
            },
          ]}
          engineStatuses={[
            { engine: 'vlm', status: 'failed', failed_units: 3 },
            { engine: 'schema', status: 'not_checked', reason: 'disabled' },
          ]}
        />
      );

      expect(screen.getByText('bicycle')).toBeInTheDocument();
      expect(screen.getByText(/độ tin cậy 0.00/i)).toBeInTheDocument();
      expect(screen.getByText(/Intersection over Union \(IoU\) 0.00/i)).toBeInTheDocument();
      expect(screen.getByText(/Quy tắc: RULE-VEH-01/i)).toBeInTheDocument();
      expect(screen.getByText(/Prediction bbox: \[12, 34, 56, 78\]/i)).toBeInTheDocument();
      expect(screen.getByText(/Thực tế:/i)).toBeInTheDocument();
      expect(screen.getByText('bicycle_detected')).toBeInTheDocument();
      expect(screen.getByText('Failed')).toBeInTheDocument();
      expect(screen.getByText(/3 đơn vị lỗi/i)).toBeInTheDocument();
      expect(screen.getByText('Not checked')).toBeInTheDocument();
      expect(screen.getByText('disabled')).toBeInTheDocument();
    });
  });

  describe('ReviewGuidelineLookup race invalidation', () => {
    it('invalidates in-flight lookup when props transition to empty and rejects rule ID mismatch', async () => {
      const api = installMockAuthApi();
      await api.signIn('reviewer');
      const defaultFetch = api.fetchSpy.getMockImplementation()!;

      let resolveLookup: (resp: Response) => void;
      const lookupPromise = new Promise<Response>((resolve) => {
        resolveLookup = resolve;
      });

      api.fetchSpy.mockImplementation(async (request) => {
        const url = new URL(request.url);
        if (url.pathname.startsWith('/api/auth/')) return defaultFetch(request);
        if (url.pathname === '/api/guidelines/rules/RULE-01/') {
          return lookupPromise;
        }
        return Response.json({}, { status: 404 });
      });

      const { rerender } = render(
        <ReviewGuidelineLookup ruleId="RULE-01" guidelineVersion="v1.0" />
      );

      // Now props become empty (issue without rule) while request is in flight
      rerender(<ReviewGuidelineLookup ruleId={null} guidelineVersion={null} />);

      // Old lookup resolves
      resolveLookup!(
        Response.json({
          rule_id: 'RULE-01',
          section: '1.0',
          content: 'Nội dung quy tắc 01',
          guideline_version: 'v1.0',
        })
      );
      await lookupPromise;

      // Stale rule content MUST NOT be displayed
      expect(screen.queryByText('Nội dung quy tắc 01')).toBeNull();
      expect(screen.getByText(/Issue không gắn với mã quy tắc guideline cụ thể/i)).toBeInTheDocument();
    });
  });
});
