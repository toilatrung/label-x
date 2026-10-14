'use client';

import { useInfiniteQuery, useQueries, useQuery } from '@tanstack/react-query';
import { cursorFrom, getDatasetRevisions, getDatasets, getSnapshot, getSnapshotRuns, getSnapshots, getTasks } from './api';
import { listConfigs } from '@/lib/execution/api';

export function useDatasets(userId?: number) {
  return useInfiniteQuery({
    queryKey: ['datasets', userId], enabled: userId !== undefined,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getDatasets(pageParam, signal),
    getNextPageParam: page => page?.next ? cursorFrom(page.next) : undefined, retry: false,
  });
}

export function useTasks(userId: number | undefined, datasetId: number | null, allowed: boolean) {
  return useQuery({
    queryKey: ['dataset-tasks', userId, datasetId],
    enabled: userId !== undefined && datasetId !== null && allowed,
    queryFn: ({ signal }) => getTasks(datasetId!, signal), retry: false,
  });
}

export function useSnapshot(userId: number | undefined, id: number | null) {
  return useQuery({
    queryKey: ['snapshot', userId, id], enabled: userId !== undefined && id !== null,
    queryFn: ({ signal }) => getSnapshot(id!, signal), retry: false,
    refetchInterval: query => ['pending', 'exporting'].includes(query.state.data?.status ?? '') ? 3000 : false,
  });
}

export function useSnapshotHistory(userId: number | undefined, datasetId: number | null) {
  return useInfiniteQuery({
    queryKey: ['snapshot-history', userId, datasetId],
    enabled: userId !== undefined && datasetId !== null,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getSnapshots(datasetId!, pageParam, signal),
    getNextPageParam: page => page?.next ? cursorFrom(page.next) : undefined, retry: false,
  });
}

/** Quality Control Run mới nhất của Snapshot: phần tử đầu trang đầu (backend sắp id giảm dần); null khi chưa có run. */
function latestRunQuery(userId: number | undefined, snapshotId: number | null, allowed: boolean) {
  return {
    queryKey: ['snapshot-latest-run', userId, snapshotId],
    enabled: userId !== undefined && snapshotId !== null && allowed,
    queryFn: async ({ signal }: { signal: AbortSignal }) => (await getSnapshotRuns(snapshotId!, undefined, signal)).results[0] ?? null,
    retry: false,
  };
}

export function useLatestSnapshotRun(userId: number | undefined, snapshotId: number | null, allowed: boolean) {
  return useQuery(latestRunQuery(userId, snapshotId, allowed));
}

/** Một lời gọi GET /api/snapshots/{id}/runs/ cho mỗi Snapshot đang hiện trên trang. */
export function useLatestSnapshotRuns(userId: number | undefined, snapshotIds: number[], allowed: boolean) {
  return useQueries({ queries: snapshotIds.map(id => latestRunQuery(userId, id, allowed)) });
}

export function useDatasetRevisions(userId: number | undefined, datasetId: number | null, allowed: boolean) {
  return useInfiniteQuery({
    queryKey: ['dataset-revisions', userId, datasetId],
    enabled: userId !== undefined && datasetId !== null && allowed,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => getDatasetRevisions(datasetId!, pageParam, signal),
    getNextPageParam: page => page?.next ? cursorFrom(page.next) : undefined, retry: false,
  });
}

export function usePublishedConfigs(userId: number | undefined, allowed: boolean) {
  return useQuery({
    queryKey: ['snapshot-published-configs', userId], enabled: userId !== undefined && allowed,
    queryFn: ({ signal }) => listConfigs(null, signal), retry: false,
  });
}
