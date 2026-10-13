'use client';

import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { cursorFrom, getDatasets, getSnapshot, getSnapshots, getTasks } from './api';
import { cursorFrom as runCursorFrom, listConfigs, listRuns, type Run } from '@/lib/execution/api';

const MAX_RUN_PAGES = 20;

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

/** Mọi Quality Control Run của Dataset (đọc hết các trang, tối đa 20 trang) để nối Snapshot với run. */
export function useDatasetRuns(userId: number | undefined, datasetId: number | null, allowed: boolean) {
  return useQuery({
    queryKey: ['snapshot-dataset-runs', userId, datasetId],
    enabled: userId !== undefined && datasetId !== null && allowed,
    queryFn: async ({ signal }) => {
      const runs: Run[] = [];
      let cursor: string | null = null;
      for (let page = 0; page < MAX_RUN_PAGES; page++) {
        const reply = await listRuns(datasetId!, cursor, signal);
        runs.push(...reply.results);
        cursor = runCursorFrom(reply.next);
        if (!cursor) break;
      }
      return runs;
    },
    retry: false,
  });
}

export function usePublishedConfigs(userId: number | undefined, allowed: boolean) {
  return useQuery({
    queryKey: ['snapshot-published-configs', userId], enabled: userId !== undefined && allowed,
    queryFn: ({ signal }) => listConfigs(null, signal), retry: false,
  });
}
