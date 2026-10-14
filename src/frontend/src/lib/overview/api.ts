/**
 * Nguồn dữ liệu thật cho Overview (Quality Control Home và Quality Summary).
 * Mỗi vùng màn hình đọc đúng endpoint của contract (docs/04-api/openapi.yaml); không dùng
 * response mẫu của API Explorer. Vùng chưa có API được đánh dấu TODO(backend) ở component.
 */
import { useQuery } from '@tanstack/react-query';
import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components } from '@/lib/api/contract';
import { getTasks, type CvatTask } from '@/lib/snapshots/api';
import { getLedger, getRun, type LedgerEntry, type Run } from '@/lib/execution/api';
import { getGate, type GateCondition, type GateConditionName, type GateResult } from '@/lib/reports/api';
import { getQueueSummary, type QueueSummary } from '@/lib/review/api';
import { getEscalations } from '@/lib/escalations/api';

export type { CvatTask, GateResult, LedgerEntry, QueueSummary, Run };
export type ReworkCounts = components['schemas']['PaginatedReworkList']['counts'];
export type DatasetSummary = components['schemas']['DatasetSummary'];
export type RunMetrics = components['schemas']['RunMetrics'];
export type RunEngineStat = components['schemas']['RunEngineStat'];
export type TaskQuality = components['schemas']['TaskQuality'];
export type CandidateCategories = components['schemas']['CandidateCategories'];
export type ReviewVolume = components['schemas']['ReviewVolume'];
export type ReviewVolumeQuery = { granularity: 'day' | 'week'; date_from: string; date_to: string };

/** Giới hạn số trang cursor khi gom hết một danh sách nhỏ (dataset, task); tránh lặp vô hạn nếu server trả cursor lặp. */
const MAX_PAGES = 20;

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || result.data === undefined) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}

function cursorOf(next: string | null | undefined): string | null {
  if (!next) return null;
  try { return new URL(next, 'http://localhost').searchParams.get('cursor'); } catch { return null; }
}

/** Gom mọi trang cursor; báo lỗi khi cursor lặp thay vì quay vòng. */
async function collectPages<T>(load: (cursor: string | null) => Promise<{ next?: string | null; results: T[] }>): Promise<T[]> {
  const rows: T[] = [];
  const seen = new Set<string>();
  let cursor: string | null = null;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const data = await load(cursor);
    rows.push(...data.results);
    const next = cursorOf(data.next);
    if (!next) return rows;
    if (seen.has(next)) throw new Error('Phát hiện vòng lặp phân trang từ server.');
    seen.add(next);
    cursor = next;
  }
  return rows;
}

/** `GET /api/datasets/summary/` (MBE-06): latest_run_id, open_issue_count… cho mọi dataset trong phạm vi, một lần thay vì N+1. */
export async function getDatasetSummaries(signal?: AbortSignal): Promise<DatasetSummary[]> {
  return collectPages((cursor) => apiClient.GET('/api/datasets/summary/', {
    params: { query: cursor ? { cursor } : {} }, signal, cache: 'no-store',
  }).then(unwrap));
}

export async function getRunMetrics(runId: number, signal?: AbortSignal): Promise<RunMetrics> {
  return unwrap(await apiClient.GET('/api/runs/{id}/metrics/', { params: { path: { id: runId } }, signal }));
}

export async function getReviewVolume(runId: number, query: ReviewVolumeQuery, signal?: AbortSignal): Promise<ReviewVolume> {
  return unwrap(await apiClient.GET('/api/runs/{id}/review-volume/', { params: { path: { id: runId }, query }, signal }));
}

export async function getRunEngines(runId: number, signal?: AbortSignal): Promise<RunEngineStat[]> {
  return unwrap(await apiClient.GET('/api/runs/{id}/engines/', { params: { path: { id: runId } }, signal })).engines;
}

export async function getTasksQuality(runId: number, signal?: AbortSignal): Promise<TaskQuality[]> {
  return collectPages((cursor) => apiClient.GET('/api/runs/{id}/tasks-quality/', {
    params: { path: { id: runId }, query: cursor ? { cursor } : {} }, signal,
  }).then(unwrap));
}

export async function getCandidateCategories(runId: number, signal?: AbortSignal): Promise<CandidateCategories> {
  return unwrap(await apiClient.GET('/api/runs/{id}/candidate-categories/', { params: { path: { id: runId } }, signal }));
}

export interface CandidateTotals {
  /** Số candidate sau gộp trùng của cả run (`dedup_count`). */
  dedup: number;
  /** Số bản ghi thô, null khi server chưa tính. */
  raw: number | null;
}

/** `GET /api/runs/{id}/candidates/?page_size=1`: chỉ lấy tổng dedup_count/raw_count, không tải danh sách. */
export async function getCandidateTotals(runId: number, signal?: AbortSignal): Promise<CandidateTotals> {
  const page = unwrap(await apiClient.GET('/api/runs/{id}/candidates/', {
    params: { path: { id: runId }, query: { page_size: 1 } }, signal,
  }));
  return { dedup: page.dedup_count, raw: page.raw_count ?? null };
}

export interface EscalationTally {
  /** Số issue chờ phân xử trên trang đầu. */
  loaded: number;
  /** Còn trang sau: tổng thực tế ≥ loaded (endpoint không trả tổng). */
  hasMore: boolean;
}

export async function getEscalationTally(runId: number, signal?: AbortSignal): Promise<EscalationTally> {
  const page = await getEscalations({ runId, signal });
  return { loaded: page.results?.length ?? 0, hasMore: Boolean(page.next) };
}

/** `GET /api/rework/?dataset_id=` trả `counts` theo trạng thái cho toàn dataset (không phụ thuộc bộ lọc status). */
export async function getReworkCounts(datasetId: number, signal?: AbortSignal): Promise<ReworkCounts> {
  const page = unwrap(await apiClient.GET('/api/rework/', {
    params: { query: { dataset_id: datasetId } }, signal, cache: 'no-store',
  }));
  return page.counts;
}

export const overviewKeys = {
  tasks: (datasetId: number) => ['overview', 'tasks', datasetId] as const,
  summaries: ['overview', 'dataset-summaries'] as const,
  metrics: (runId: number) => ['overview', 'metrics', runId] as const,
  engines: (runId: number) => ['overview', 'engines', runId] as const,
  tasksQuality: (runId: number) => ['overview', 'tasks-quality', runId] as const,
  categories: (runId: number) => ['overview', 'candidate-categories', runId] as const,
  run: (runId: number) => ['overview', 'run', runId] as const,
  gate: (runId: number) => ['overview', 'gate', runId] as const,
  ledger: (runId: number) => ['overview', 'ledger', runId] as const,
  candidates: (runId: number) => ['overview', 'candidates', runId] as const,
  queue: (name: 'risk' | 'random', runId: number) => ['overview', 'queue', name, runId] as const,
  escalations: (runId: number) => ['overview', 'escalations', runId] as const,
  rework: (datasetId: number) => ['overview', 'rework', datasetId] as const,
  reviewVolume: (runId: number, query: ReviewVolumeQuery) => ['overview', 'review-volume', runId, query] as const,
};

const STALE = 30_000;

export function useDatasetTasks(datasetId: number | null) {
  return useQuery({
    queryKey: overviewKeys.tasks(datasetId ?? 0),
    queryFn: ({ signal }) => getTasks(datasetId as number, signal),
    enabled: datasetId !== null, staleTime: STALE,
  });
}

export function useDatasetSummaries(enabled = true) {
  return useQuery({
    queryKey: overviewKeys.summaries,
    queryFn: ({ signal }) => getDatasetSummaries(signal),
    enabled, staleTime: STALE,
  });
}

export interface LatestRunState {
  data: Run | null | undefined;
  isPending: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => unknown;
}

/**
 * Quality Control Run mới nhất của dataset: `latest_run_id` từ GET /api/datasets/summary/ rồi
 * GET /api/runs/{id}/. `data` = null khi dataset chưa có run (hoặc không thuộc phạm vi summary).
 */
export function useLatestRun(datasetId: number | null): LatestRunState {
  const summaries = useDatasetSummaries(datasetId !== null);
  const summary = datasetId === null ? undefined : summaries.data?.find((row) => row.dataset_id === datasetId);
  const runId = summary?.latest_run_id ?? null;
  const run = useRunDetail(runId);
  if (datasetId === null) return { data: undefined, isPending: false, isError: false, error: null, refetch: () => undefined };
  if (summaries.isError) return { data: undefined, isPending: false, isError: true, error: summaries.error, refetch: summaries.refetch };
  if (summaries.isPending) return { data: undefined, isPending: true, isError: false, error: null, refetch: summaries.refetch };
  if (runId === null) return { data: null, isPending: false, isError: false, error: null, refetch: summaries.refetch };
  return { data: run.data, isPending: run.isPending, isError: run.isError, error: run.error, refetch: run.refetch };
}

export function useRunMetrics(runId: number | null) {
  return useQuery({
    queryKey: overviewKeys.metrics(runId ?? 0),
    queryFn: ({ signal }) => getRunMetrics(runId as number, signal),
    enabled: runId !== null, staleTime: STALE,
  });
}

export function useReviewVolume(runId: number | null, query: ReviewVolumeQuery) {
  return useQuery({
    queryKey: overviewKeys.reviewVolume(runId ?? 0, query),
    queryFn: ({ signal }) => getReviewVolume(runId as number, query, signal),
    enabled: runId !== null && query.date_from <= query.date_to, staleTime: STALE,
  });
}

export function useRunEngines(runId: number | null) {
  return useQuery({
    queryKey: overviewKeys.engines(runId ?? 0),
    queryFn: ({ signal }) => getRunEngines(runId as number, signal),
    enabled: runId !== null, staleTime: STALE,
  });
}

export function useTasksQuality(runId: number | null) {
  return useQuery({
    queryKey: overviewKeys.tasksQuality(runId ?? 0),
    queryFn: ({ signal }) => getTasksQuality(runId as number, signal),
    enabled: runId !== null, staleTime: STALE,
  });
}

export function useCandidateCategories(runId: number | null) {
  return useQuery({
    queryKey: overviewKeys.categories(runId ?? 0),
    queryFn: ({ signal }) => getCandidateCategories(runId as number, signal),
    enabled: runId !== null, staleTime: STALE,
  });
}

export function useRunDetail(runId: number | null) {
  return useQuery({
    queryKey: overviewKeys.run(runId ?? 0),
    queryFn: ({ signal }) => getRun(runId as number, signal),
    enabled: runId !== null, staleTime: STALE,
  });
}

export function useRunGate(runId: number | null) {
  return useQuery({
    queryKey: overviewKeys.gate(runId ?? 0),
    queryFn: ({ signal }) => getGate(runId as number, signal),
    enabled: runId !== null, staleTime: STALE,
  });
}

export function useRunLedger(runId: number | null) {
  return useQuery({
    queryKey: overviewKeys.ledger(runId ?? 0),
    queryFn: ({ signal }) => getLedger(runId as number, signal),
    enabled: runId !== null, staleTime: STALE,
  });
}

export function useCandidateTotals(runId: number | null) {
  return useQuery({
    queryKey: overviewKeys.candidates(runId ?? 0),
    queryFn: ({ signal }) => getCandidateTotals(runId as number, signal),
    enabled: runId !== null, staleTime: STALE,
  });
}

/** Hàng đợi của run; `null` khi server trả 404 "Run chưa có queue đã lưu" (run chưa sinh hàng đợi review). */
export async function getRunQueue(name: 'risk' | 'random', runId: number, signal?: AbortSignal): Promise<QueueSummary | null> {
  try {
    return await getQueueSummary(name, runId, signal);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) return null;
    throw error;
  }
}

export function useQueueSummary(name: 'risk' | 'random', runId: number | null) {
  return useQuery({
    queryKey: overviewKeys.queue(name, runId ?? 0),
    queryFn: ({ signal }) => getRunQueue(name, runId as number, signal),
    enabled: runId !== null, staleTime: STALE,
  });
}

export function useEscalationTally(runId: number | null) {
  return useQuery({
    queryKey: overviewKeys.escalations(runId ?? 0),
    queryFn: ({ signal }) => getEscalationTally(runId as number, signal),
    enabled: runId !== null, staleTime: STALE,
  });
}

export function useReworkCounts(datasetId: number | null) {
  return useQuery({
    queryKey: overviewKeys.rework(datasetId ?? 0),
    queryFn: ({ signal }) => getReworkCounts(datasetId as number, signal),
    enabled: datasetId !== null, staleTime: STALE,
  });
}

/* ------------------------------------------------------------------ helpers */

export function gateCondition(gate: GateResult | undefined, name: GateConditionName): GateCondition | undefined {
  return gate?.conditions.find((condition) => condition.name === name);
}

export type Tone = 'success' | 'warning' | 'danger' | 'info' | '';

export function percentText(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

export function runStatusTone(status: Run['status']): Tone {
  return ({ completed: 'success', partial: 'warning', running: 'info', queued: 'info', failed: 'danger', cancelled: '' } as const)[status] ?? '';
}

export function gateBadge(status: GateResult['status'] | undefined): { label: string; tone: Tone } {
  if (status === 'passed') return { label: 'Đạt', tone: 'success' };
  if (status === 'failed') return { label: 'Blocked', tone: 'danger' };
  return { label: 'Not checked', tone: '' };
}

export function taskFrameCount(task: CvatTask): number {
  return task.jobs.reduce((sum, job) => sum + (job.frame_count ?? 0), 0);
}

/** Tổng frame đã review xong trong một hàng đợi (reviewed + chờ follow-up + completed). */
export function reviewedCount(summary: QueueSummary): number {
  const counts = summary.counts as Partial<Record<string, number>>;
  return (counts.reviewed ?? 0) + (counts.awaiting_followup ?? 0) + (counts.completed ?? 0);
}

/** IssueFamily (contract): E1 thiếu box, E2 sai lớp, E3 trùng box, structural cảnh báo cấu trúc. */
export const FAMILY_LABELS: Record<string, string> = {
  E1: 'Thiếu object',
  E2: 'Sai nhãn',
  E3: 'Trùng / chồng lấn',
  structural: 'Cảnh báo cấu trúc',
};

/** Trạng thái issue từ khi được xác nhận trở đi (state-machines §3): đếm "Lỗi đã xác nhận". */
export const CONFIRMED_ISSUE_STATES = ['confirmed', 'fix_pending', 'recheck_pending', 'resolved', 'reopened'] as const;

export function confirmedIssueCount(metrics: RunMetrics): number {
  const byState = metrics.issues_by_state as Record<string, number>;
  return CONFIRMED_ISSUE_STATES.reduce((sum, state) => sum + (byState[state] ?? 0), 0);
}
