import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AnalysisPage from '@/app/analysis/page';
import * as api from '@/lib/snapshots/api';

const mockSearchParams = vi.fn();
const mockPush = vi.fn();
const mockReplace = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace, back: vi.fn(), forward: vi.fn() }),
  useSearchParams: () => mockSearchParams(),
  usePathname: () => '/analysis',
}));

const mockSetDatasetId = vi.fn();
let mockAuthContext = {
  user: { id: 1, username: 'tester', role: 'qa_lead' as const, fullName: 'QA Lead' },
  session: {
    user: { id: 1, username: 'tester' },
    roles: [
      { role: 'qa_lead' as const, dataset_id: 42 },
      { role: 'qa_lead' as const, dataset_id: 99 },
    ],
    identity_mapping: { status: 'mapped' as const, cvat_user_id: 1, cvat_username: 'tester' },
  },
  isLoading: false,
  datasetId: 42 as number | null,
  setDatasetId: mockSetDatasetId,
  logout: vi.fn(),
  hasPermission: () => true,
};

vi.mock('@/lib/auth/auth-context', () => ({
  useAuth: () => mockAuthContext,
}));

vi.mock('@/lib/snapshots/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/snapshots/api')>();
  return {
    ...actual,
    getDatasets: vi.fn(),
    getSnapshot: vi.fn(),
    getSnapshots: vi.fn().mockResolvedValue({ results: [], next: null, previous: null }),
    getTasks: vi.fn().mockResolvedValue([]),
  };
});

function renderWithClient(queryClient?: QueryClient) {
  const client = queryClient ?? new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <AnalysisPage />
    </QueryClientProvider>
  );
}

describe('AnalysisPage regression tests (R-1, F-1, F-2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthContext = {
      user: { id: 1, username: 'tester', role: 'qa_lead' as const, fullName: 'QA Lead' },
      session: {
        user: { id: 1, username: 'tester' },
        roles: [
          { role: 'qa_lead' as const, dataset_id: 42 },
          { role: 'qa_lead' as const, dataset_id: 99 },
        ],
        identity_mapping: { status: 'mapped' as const, cvat_user_id: 1, cvat_username: 'tester' },
      },
      isLoading: false,
      datasetId: 42,
      setDatasetId: mockSetDatasetId,
      logout: vi.fn(),
      hasPermission: () => true,
    };
  });

  describe('F-1: Dataset context on deep-linked Snapshot', () => {
    it('resolves and displays Dataset name from snapshot (e.g. #99 "Private") even when session had #42 "Urban"', async () => {
      mockSearchParams.mockReturnValue(new URLSearchParams('snapshotId=99'));

      vi.mocked(api.getDatasets).mockImplementation(async (cursor) => {
        if (!cursor) {
          return {
            results: [{ id: 42, cvat_project_id: 42, name: 'Urban', taxonomy_version: 'v1', guideline_version: 'v1' }],
            next: 'http://localhost/api/datasets/?cursor=42',
            previous: null,
          };
        }
        return {
          results: [{ id: 99, cvat_project_id: 99, name: 'Private', taxonomy_version: 'v2', guideline_version: 'v2' }],
          next: null,
          previous: null,
        };
      });

      vi.mocked(api.getSnapshot).mockResolvedValue({
        id: 99,
        dataset_id: 99,
        status: 'locked',
        failure_reason: null,
        revision_hash: 'rev99',
        parent_snapshot_id: null,
        drift_jobs: [],
        out_of_scope_shapes: 0,
        taxonomy_version: 'v2',
        guideline_version: 'v2',
        created_by: 1,
        created_at: '2026-10-09T08:00:00Z',
        jobs: [],
      });

      renderWithClient();

      await waitFor(() => {
        expect(screen.getByText('Private')).toBeDefined();
      });

      expect(mockSetDatasetId).not.toHaveBeenCalled();
    });

    it('falls back to Dataset #99 if dataset is not found in user scope without using wrong session name', async () => {
      mockSearchParams.mockReturnValue(new URLSearchParams('snapshotId=99'));

      vi.mocked(api.getDatasets).mockResolvedValue({
        results: [{ id: 42, cvat_project_id: 42, name: 'Urban', taxonomy_version: 'v1', guideline_version: 'v1' }],
        next: null,
        previous: null,
      });

      vi.mocked(api.getSnapshot).mockResolvedValue({
        id: 99,
        dataset_id: 99,
        status: 'locked',
        failure_reason: null,
        revision_hash: 'rev99',
        parent_snapshot_id: null,
        drift_jobs: [],
        out_of_scope_shapes: 0,
        taxonomy_version: 'v2',
        guideline_version: 'v2',
        created_by: 1,
        created_at: '2026-10-09T08:00:00Z',
        jobs: [],
      });

      renderWithClient();

      await waitFor(() => {
        expect(screen.getByText(/Dataset.*#99/)).toBeDefined();
      });
      expect(screen.queryByText('Urban')).toBeNull();
    });
  });

  describe('R-1 / F-2: Latest locked snapshot pagination and boundary handling', () => {
    it('fetches subsequent pages until locked snapshot is found on page 21 without stopping at page 20', async () => {
      mockSearchParams.mockReturnValue(new URLSearchParams(''));

      vi.mocked(api.getDatasets).mockResolvedValue({
        results: [{ id: 42, cvat_project_id: 42, name: 'Urban', taxonomy_version: 'v1', guideline_version: 'v1' }],
        next: null,
        previous: null,
      });

      vi.mocked(api.getSnapshots).mockImplementation(async (_datasetId, cursor) => {
        const pageNum = cursor ? Number(cursor) : 1;
        if (pageNum < 21) {
          return {
            results: [{
              id: pageNum,
              dataset_id: 42,
              status: 'failed' as const,
              failure_reason: 'drift_detected' as const,
              revision_hash: null,
              parent_snapshot_id: null,
              drift_jobs: [],
              out_of_scope_shapes: 0,
              taxonomy_version: 'v1',
              guideline_version: 'v1',
              created_by: 1,
              created_at: '2026-10-09T08:00:00Z',
              jobs: [],
            }],
            next: `http://localhost/api/snapshots/?dataset_id=42&cursor=${pageNum + 1}`,
            previous: null,
          };
        }
        // Page 21 has the locked snapshot!
        return {
          results: [{
            id: 2100,
            dataset_id: 42,
            status: 'locked' as const,
            failure_reason: null,
            revision_hash: 'hash-page-21',
            parent_snapshot_id: null,
            drift_jobs: [],
            out_of_scope_shapes: 0,
            taxonomy_version: 'v1',
            guideline_version: 'v1',
            created_by: 1,
            created_at: '2026-10-09T09:00:00Z',
            jobs: [],
          }],
          next: null,
          previous: null,
        };
      });

      renderWithClient();

      await waitFor(() => {
        expect(screen.getByText('SNP-2100')).toBeDefined();
        expect(screen.getByText('hash-page-21')).toBeDefined();
      }, { timeout: 3000 });
    });

    it('safely handles repeating cursor loop without infinite requests and does not stay stuck in loading', async () => {
      mockSearchParams.mockReturnValue(new URLSearchParams(''));

      vi.mocked(api.getDatasets).mockResolvedValue({
        results: [{ id: 42, cvat_project_id: 42, name: 'Urban', taxonomy_version: 'v1', guideline_version: 'v1' }],
        next: null,
        previous: null,
      });

      let callCount = 0;
      vi.mocked(api.getSnapshots).mockImplementation(async () => {
        callCount++;
        return {
          results: [{
            id: 1,
            dataset_id: 42,
            status: 'failed' as const,
            failure_reason: 'drift_detected' as const,
            revision_hash: null,
            parent_snapshot_id: null,
            drift_jobs: [],
            out_of_scope_shapes: 0,
            taxonomy_version: 'v1',
            guideline_version: 'v1',
            created_by: 1,
            created_at: '2026-10-09T08:00:00Z',
            jobs: [],
          }],
          next: 'http://localhost/api/snapshots/?dataset_id=42&cursor=infinite-loop',
          previous: null,
        };
      });

      renderWithClient();

      // Detects loop and shows clear error message
      await waitFor(() => {
        expect(screen.getByText('Phát hiện vòng lặp cursor từ máy chủ.')).toBeDefined();
      });

      // Does not get stuck indefinitely loading
      expect(screen.queryByText('Đang tải…')).toBeNull();
      // Should stop after identifying the loop
      expect(callCount).toBeLessThanOrEqual(3);
    });

    it('displays "Chưa có Snapshot đã khóa." only after all pages are exhausted without finding locked snapshot', async () => {
      mockSearchParams.mockReturnValue(new URLSearchParams(''));

      vi.mocked(api.getDatasets).mockResolvedValue({
        results: [{ id: 42, cvat_project_id: 42, name: 'Urban', taxonomy_version: 'v1', guideline_version: 'v1' }],
        next: null,
        previous: null,
      });

      vi.mocked(api.getSnapshots).mockImplementation(async (_datasetId, cursor) => {
        if (!cursor) {
          return {
            results: [{
              id: 1,
              dataset_id: 42,
              status: 'failed' as const,
              failure_reason: 'drift_detected' as const,
              revision_hash: null,
              parent_snapshot_id: null,
              drift_jobs: [],
              out_of_scope_shapes: 0,
              taxonomy_version: 'v1',
              guideline_version: 'v1',
              created_by: 1,
              created_at: '2026-10-09T08:00:00Z',
              jobs: [],
            }],
            next: 'http://localhost/api/snapshots/?dataset_id=42&cursor=1',
            previous: null,
          };
        }
        return {
          results: [{
            id: 2,
            dataset_id: 42,
            status: 'pending' as const,
            failure_reason: null,
            revision_hash: null,
            parent_snapshot_id: null,
            drift_jobs: [],
            out_of_scope_shapes: 0,
            taxonomy_version: 'v1',
            guideline_version: 'v1',
            created_by: 1,
            created_at: '2026-10-09T08:30:00Z',
            jobs: [],
          }],
          next: null,
          previous: null,
        };
      });

      renderWithClient();

      await waitFor(() => {
        expect(screen.getByText('Chưa có Snapshot đã khóa.')).toBeDefined();
      });
    });

    it('does not display locked snapshot from previous dataset when switching dataset', async () => {
      mockSearchParams.mockReturnValue(new URLSearchParams(''));

      vi.mocked(api.getDatasets).mockResolvedValue({
        results: [
          { id: 42, cvat_project_id: 42, name: 'Urban', taxonomy_version: 'v1', guideline_version: 'v1' },
          { id: 99, cvat_project_id: 99, name: 'Private', taxonomy_version: 'v2', guideline_version: 'v2' },
        ],
        next: null,
        previous: null,
      });

      vi.mocked(api.getSnapshots).mockImplementation(async (targetDatasetId) => {
        if (targetDatasetId === 42) {
          return {
            results: [{
              id: 420,
              dataset_id: 42,
              status: 'locked' as const,
              failure_reason: null,
              revision_hash: 'hash-dataset-42',
              parent_snapshot_id: null,
              drift_jobs: [],
              out_of_scope_shapes: 0,
              taxonomy_version: 'v1',
              guideline_version: 'v1',
              created_by: 1,
              created_at: '2026-10-09T08:00:00Z',
              jobs: [],
            }],
            next: null,
            previous: null,
          };
        }
        // Dataset 99 has no locked snapshots
        return {
          results: [{
            id: 990,
            dataset_id: 99,
            status: 'pending' as const,
            failure_reason: null,
            revision_hash: null,
            parent_snapshot_id: null,
            drift_jobs: [],
            out_of_scope_shapes: 0,
            taxonomy_version: 'v2',
            guideline_version: 'v2',
            created_by: 1,
            created_at: '2026-10-09T08:30:00Z',
            jobs: [],
          }],
          next: null,
          previous: null,
        };
      });

      // Switch auth context to dataset 99
      mockAuthContext.datasetId = 99;

      renderWithClient();

      await waitFor(() => {
        expect(screen.getByText('Chưa có Snapshot đã khóa.')).toBeDefined();
      });

      // Must never display locked snapshot from dataset 42
      expect(screen.queryByText('SNP-420')).toBeNull();
      expect(screen.queryByText('hash-dataset-42')).toBeNull();
    });
  });
});
