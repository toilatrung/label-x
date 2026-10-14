'use client';

import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import { getGate, getReleaseManifest, getRunReport, listReleases } from '@/lib/reports/api';

const EXPORT_POLL_MS = 5000;

/** Gate của run; cùng key với Quality Gate để header/body/các trang dùng chung cache. */
export function useRunGate(runId: number | null) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['report-gate', session?.user.id, runId],
    queryFn: ({ signal }) => getGate(runId!, signal),
    enabled: runId !== null && !!session,
    retry: false,
  });
}

/** GET /api/runs/{id}/report/; tự tải lại khi còn export đang xếp hàng hoặc đang tạo. */
export function useRunReport(runId: number | null) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['run-report', session?.user.id, runId],
    queryFn: ({ signal }) => getRunReport(runId!, signal),
    enabled: runId !== null && !!session,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.exports.some((e) => e.status === 'queued' || e.status === 'running') ? EXPORT_POLL_MS : false,
  });
}

/** Trang release đầu tiên (mới nhất trước, server phân trang 50). */
export function useReleases() {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['releases', session?.user.id],
    queryFn: ({ signal }) => listReleases(null, signal),
    enabled: !!session,
    retry: false,
  });
}

export function useReleaseManifest(releaseId: number | null) {
  const { session } = useAuth();
  return useQuery({
    queryKey: ['release-manifest', session?.user.id, releaseId],
    queryFn: ({ signal }) => getReleaseManifest(releaseId!, signal),
    enabled: releaseId !== null && !!session,
    retry: false,
  });
}
