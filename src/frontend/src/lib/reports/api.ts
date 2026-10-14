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
// MBE-03: báo cáo chất lượng của run, export, release và manifest.
export type RunReport = components['schemas']['RunReport'];
export type ReportExport = components['schemas']['ReportExport'];
export type ReportExportFormat = components['schemas']['ReportExportFormat'];
export type LedgerEntry = components['schemas']['LedgerEntry'];
export type Release = components['schemas']['Release'];
export type ReleaseManifest = components['schemas']['ReleaseManifest'];

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

export async function getRunReport(runId: number, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/runs/{id}/report/', { params: { path: { id: runId } }, signal, cache: 'no-store' }));
}

/** Idempotent theo (run, format): server trả lại export đã có cho cùng run/format. */
export async function createReportExport(runId: number, format: ReportExportFormat, key: string) {
  await csrf();
  return unwrap(await apiClient.POST('/api/runs/{id}/report/export/', {
    body: { format }, params: { path: { id: runId }, header: { 'Idempotency-Key': key } },
  }));
}

export async function listReleases(cursor: string | null, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/releases/', { params: { query: cursor ? { cursor } : {} }, signal, cache: 'no-store' }));
}

export async function getReleaseManifest(id: number, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/releases/{id}/manifest/', { params: { path: { id } }, signal, cache: 'no-store' }));
}

export async function approveRelease(id: number, note: string, key: string) {
  await csrf();
  return unwrap(await apiClient.POST('/api/releases/{id}/approve/', {
    body: note ? { note } : {}, params: { path: { id }, header: { 'Idempotency-Key': key } },
  }));
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

export const EXPORT_FORMATS: ReadonlyArray<{ key: ReportExportFormat; label: string; note: string }> = [
  { key: 'pdf', label: 'PDF', note: 'Bản đọc, kèm biểu đồ' },
  { key: 'csv', label: 'CSV', note: 'Bảng số liệu' },
  { key: 'json', label: 'JSON', note: 'Gói báo cáo kèm manifest' },
];

export const EXPORT_STATUS_LABELS: Record<ReportExport['status'], string> = {
  queued: 'Đang xếp hàng',
  running: 'Đang tạo',
  completed: 'Sẵn sàng',
  failed: 'Lỗi',
};

/** IssueFamily (contract): E1 thiếu box, E2 sai lớp, E3 trùng box, structural cảnh báo cấu trúc. */
export const ISSUE_FAMILY_LABELS: Record<string, string> = {
  E1: 'Thiếu object',
  E2: 'Sai nhãn',
  E3: 'Trùng / chồng lấn',
  structural: 'Cảnh báo cấu trúc',
};

/** Trạng thái issue đã xác nhận nhưng chưa đóng (state-machines §3). */
export const OPEN_CONFIRMED_STATES = ['confirmed', 'fix_pending', 'recheck_pending', 'reopened'] as const;

/** Coverage của run = completed / eligible cộng trên các engine bắt buộc (LedgerEntry); null khi eligible = 0. */
export function requiredCoverage(entries: readonly LedgerEntry[]): number | null {
  const required = entries.filter((e) => e.required !== false);
  const eligible = required.reduce((sum, e) => sum + e.eligible, 0);
  return eligible ? required.reduce((sum, e) => sum + e.completed, 0) / eligible : null;
}

export function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export function formatDateTime(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' })} ${date.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}`;
}
