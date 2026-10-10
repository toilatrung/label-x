import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AnalysisPage from '@/app/analysis/page';
import * as api from '@/lib/snapshots/api';

const mockSearchParams = vi.fn();
const mockRouterReplace = vi.fn();
const mockSetDatasetId = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/analysis',
  useRouter: () => ({ replace: mockRouterReplace, push: vi.fn() }),
  useSearchParams: () => mockSearchParams(),
}));

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

function renderWithClient() {
  const client = new QueryClient({
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

describe('AnalysisPage regression tests (F-1 & F-2)', () => {
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

      // Dataset page 1 has Urban (#42), page 2 has Private (#99)
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

      // Chip Dataset in ContextBar must resolve to "Private", NOT "Urban"
      await waitFor(() => {
        expect(screen.getByText('Private')).toBeDefined();
      });

      // Does not silently overwrite session datasetId
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

      // Must display Dataset #99, NOT "Urban"
      await waitFor(() => {
        expect(screen.getByText(/Dataset.*#99/)).toBeDefined();
      });
      expect(screen.queryByText('Urban')).toBeNull();
    });
  });

  describe('F-2: Latest locked snapshot pagination', () => {
    it('fetches subsequent pages until locked snapshot is found when page 1 has 50 non-locked snapshots', async () => {
      mockSearchParams.mockReturnValue(new URLSearchParams(''));

      vi.mocked(api.getDatasets).mockResolvedValue({
        results: [{ id: 42, cvat_project_id: 42, name: 'Urban', taxonomy_version: 'v1', guideline_version: 'v1' }],
        next: null,
        previous: null,
      });

      // Page 1: 50 failed snapshots with next cursor
      const fiftyFailed = Array.from({ length: 50 }, (_, i) => ({
        id: i + 1,
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
      }));

      vi.mocked(api.getSnapshots).mockImplementation(async (_datasetId, cursor) => {
        if (!cursor) {
          return {
            results: fiftyFailed,
            next: 'http://localhost/api/snapshots/?dataset_id=42&cursor=50',
            previous: null,
          };
        }
        return {
          results: [{
            id: 100,
            dataset_id: 42,
            status: 'locked' as const,
            failure_reason: null,
            revision_hash: 'locked-hash-100',
            parent_snapshot_id: null,
            drift_jobs: [],
            out_of_scope_shapes: 2,
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

      // Automatically finds SNP-100 from page 2
      await waitFor(() => {
        expect(screen.getByText('SNP-100')).toBeDefined();
        expect(screen.getByText('locked-hash-100')).toBeDefined();
      });
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
  });
});
