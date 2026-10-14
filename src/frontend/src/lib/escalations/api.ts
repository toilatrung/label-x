import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components, operations } from '@/lib/api/contract';

export type EscalationIssue = components['schemas']['Issue'];
export type EscalationPage = components['schemas']['PaginatedIssueList'];
export type AdjudicationInput = components['schemas']['AdjudicationCreate'];
export type DecisionCase = components['schemas']['DecisionCase'];
export type DecisionCaseDetail = components['schemas']['DecisionCaseDetail'];
export type Adjudication = components['schemas']['Adjudication'];
export type GuidelineGap = components['schemas']['GuidelineGap'];
export type GuidelineGapPage = components['schemas']['PaginatedGuidelineGapList'];
export type GuidelineGapInput = components['schemas']['GuidelineGapCreate'];
export type GuidelineRule = components['schemas']['GuidelineRule'];

type EscalationsQuery = NonNullable<
  operations['escalations_list']['parameters']['query']
>;

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.data) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}

async function ensureCsrf(): Promise<void> {
  const result = await apiClient.GET('/api/auth/csrf/');
  if (!result.response.ok) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
}

export function cursorFrom(link: string | null | undefined): string | null {
  if (!link) return null;
  try {
    return new URL(link, 'http://localhost').searchParams.get('cursor');
  } catch {
    return null;
  }
}

export async function getEscalations(options: {
  runId?: number;
  cursor?: string | null;
  signal?: AbortSignal;
} = {}): Promise<EscalationPage> {
  const query: EscalationsQuery = {};
  if (options.runId) query.run = options.runId;
  if (options.cursor) query.cursor = options.cursor;
  const result = await apiClient.GET('/api/escalations/', {
    params: { query },
    signal: options.signal,
    cache: 'no-store',
  });
  return unwrap(result);
}

export async function adjudicateIssue(
  issueId: number,
  body: AdjudicationInput,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<Adjudication> {
  await ensureCsrf();
  const result = await apiClient.POST('/api/issues/{id}/adjudications/', {
    params: {
      path: { id: issueId },
      header: { 'Idempotency-Key': idempotencyKey },
    },
    body,
    signal,
  });
  return unwrap(result);
}

export interface DecisionCaseFilters {
  issueId?: number;
  ruleId?: string;
  version?: string;
}

export async function getDecisionCases(
  filters: DecisionCaseFilters,
  signal?: AbortSignal,
): Promise<DecisionCase[]> {
  const result = await apiClient.GET('/api/decision-cases/', {
    params: { query: {
      ...(filters.issueId ? { issue: filters.issueId } : {}),
      ...(filters.ruleId?.trim() ? { rule_id: filters.ruleId.trim() } : {}),
      ...(filters.version?.trim() ? { version: filters.version.trim() } : {}),
    } },
    signal,
    cache: 'no-store',
  });
  return unwrap(result).results;
}

export async function getDecisionCase(id: number, signal?: AbortSignal): Promise<DecisionCaseDetail> {
  return unwrap(await apiClient.GET('/api/decision-cases/{id}/', {
    params: { path: { id } },
    signal,
    cache: 'no-store',
  }));
}

type GuidelineGapsQuery = NonNullable<operations['guideline_gaps_list']['parameters']['query']>;

/** GET /api/guideline-gaps/ (MBE-02): một trang cursor, mới nhất trước. */
export async function getGuidelineGaps(options: {
  cursor?: string | null;
  status?: GuidelineGapsQuery['status'];
  ruleId?: string;
  signal?: AbortSignal;
} = {}): Promise<GuidelineGapPage> {
  const query: GuidelineGapsQuery = {};
  if (options.cursor) query.cursor = options.cursor;
  if (options.status) query.status = options.status;
  if (options.ruleId?.trim()) query.rule_id = options.ruleId.trim();
  return unwrap(await apiClient.GET('/api/guideline-gaps/', {
    params: { query },
    signal: options.signal,
    cache: 'no-store',
  }));
}

/** POST /api/guideline-gaps/ (MBE-02). Cùng key + cùng body trả lại gap cũ; gap open trùng (issue, rule) trả 409. */
export async function createGuidelineGap(
  body: GuidelineGapInput,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<GuidelineGap> {
  await ensureCsrf();
  return unwrap(await apiClient.POST('/api/guideline-gaps/', {
    params: { header: { 'Idempotency-Key': idempotencyKey } },
    body,
    signal,
  }));
}

const MAX_RULE_PAGES = 10;

/** GET /api/guidelines/rules/ theo guideline version mới nhất, gom các trang cursor (tối đa 10). */
export async function getGuidelineRules(signal?: AbortSignal): Promise<GuidelineRule[]> {
  const rules: GuidelineRule[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < MAX_RULE_PAGES; page += 1) {
    const data = unwrap(await apiClient.GET('/api/guidelines/rules/', {
      params: { query: cursor ? { cursor } : {} },
      signal,
      cache: 'no-store',
    }));
    rules.push(...data.results);
    cursor = cursorFrom(data.next);
    if (!cursor) break;
  }
  return rules;
}

export function makeIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `lx-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
