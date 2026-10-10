'use client';

import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { cursorFrom, getDatasets, getSnapshot, getSnapshots, getTasks } from './api';

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
