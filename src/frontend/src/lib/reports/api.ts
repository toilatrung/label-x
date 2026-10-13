import type { components } from '@/lib/api/contract';
import { apiClient, ApiRequestError } from '@/lib/api/client';

// MBE-01: gate, waiver, reference, KPI evaluation và báo cáo hiệu quả (docs/04-api/openapi.yaml).
export type GateResult = components['schemas']['GateResult'];
export type GateCondition = components['schemas']['GateCondition'];
export type GateConditionName = components['schemas']['GateConditionName'];
export type Waiver = components['schemas']['Waiver'];
export type WaiverCreate = components['schemas']['WaiverCreate'];
export type WaiverDecision = components['schemas']['WaiverDecision'];
export type Evaluation = components['schemas']['Evaluation'];
export type EvaluationCreate = components['schemas']['EvaluationCreate'];
export type EffectivenessReport = components['schemas']['EffectivenessReport'];
export type MetricValue = components['schemas']['MetricValue'];

/** Contract: chỉ coverage và agreement được waiver trong pilot (WaiverCreate). */
export const WAIVABLE_CONDITIONS: readonly GateConditionName[] = ['coverage', 'agreement'];

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.data) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  return result.data;
}

async function csrf() {
  const result = await apiClient.GET('/api/auth/csrf/');
  if (!result.response.ok) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
}

export function newIdempotencyKey(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `fe-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function getGate(runId: number, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/runs/{id}/gate/', { params: { path: { id: runId } }, signal }));
}

export async function createWaiver(body: WaiverCreate, key: string) {
  await csrf();
  return unwrap(await apiClient.POST('/api/waivers/', { body, params: { header: { 'Idempotency-Key': key } } }));
}

export async function decideWaiver(id: number, body: WaiverDecision, key: string) {
  await csrf();
  return unwrap(await apiClient.POST('/api/waivers/{id}/approve/', { body, params: { path: { id }, header: { 'Idempotency-Key': key } } }));
}

export async function createEvaluation(body: EvaluationCreate, key: string) {
  await csrf();
  return unwrap(await apiClient.POST('/api/evaluations/', { body, params: { header: { 'Idempotency-Key': key } } }));
}

export async function getEvaluation(id: number, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/evaluations/{id}/', { params: { path: { id } }, signal }));
}

/** `id` của báo cáo hiệu quả là id KPI evaluation (backend ReportView tra KpiEvaluation theo pk). */
export async function getEffectivenessReport(evaluationId: number, signal?: AbortSignal): Promise<EffectivenessReport> {
  const result = await apiClient.GET('/api/reports/{id}/', { params: { path: { id: evaluationId }, query: { format: 'json' } }, signal });
  const data = unwrap(result);
  // format=json luôn trả object; nhánh string của contract chỉ dành cho pdf/csv.
  if (typeof data !== 'object' || data === null) throw new ApiRequestError(result.response.status, undefined, result.response.headers);
  return data;
}

export const GATE_CONDITION_LABELS: Record<GateConditionName, string> = {
  coverage: 'Coverage',
  open_critical_issues: 'Lỗi nghiêm trọng',
  rework_verified: 'Rework',
  residual: 'Lỗi còn sót',
  agreement: 'Mức thống nhất của reviewer',
};

export const SOURCE_REASON_LABELS: Record<string, string> = {
  selected_final: 'Theo run cuối đủ điều kiện',
  no_valid_final: 'Chưa có run cuối đủ điều kiện, dùng run gốc',
  origin_has_open_issue: 'Run gốc còn issue mở, dùng run gốc',
};

export function sourceReasonLabel(reason: string | null | undefined): string {
  if (!reason) return '';
  return SOURCE_REASON_LABELS[reason] ?? reason;
}

export function percent(value: number | null | undefined, digits = 1): string | null {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  return `${(value * 100).toFixed(digits)}%`;
}
