import { apiClient, ApiRequestError, AUTH_EXPIRED_EVENT } from '@/lib/api/client';
import { apiBaseUrl } from '@/lib/auth/config';
import { readErrorDetail } from '@/lib/api/errors';
import type { components, operations } from '@/lib/api/contract';

export type EscalationIssue = components['schemas']['Issue'];
export type EscalationPage = components['schemas']['PaginatedIssueList'];
export type AdjudicationInput = components['schemas']['AdjudicationCreate'];
export type DecisionCase = components['schemas']['Adjudication'];

type EscalationsQuery = NonNullable<
  operations['escalations_list']['parameters']['query']
>;

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || !result.data) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}

function normalizeDecisionCase(value: DecisionCase): DecisionCase {
  // T-038 currently uses guideline_missing on the wire while the approved
  // OpenAPI baseline names the same deferred outcome guideline_gap.
  if ((value.outcome as string) === 'guideline_missing') {
    return { ...value, outcome: 'guideline_gap' };
  }
  return value;
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
): Promise<DecisionCase> {
  await ensureCsrf();
  const wireBody = body.outcome === 'guideline_gap'
    ? { ...body, outcome: 'guideline_missing' }
    : body;
  const result = await apiClient.POST('/api/issues/{id}/adjudications/', {
    params: {
      path: { id: issueId },
      header: { 'Idempotency-Key': idempotencyKey },
    },
    // Compatibility seam for T-038; remove when its wire value matches OpenAPI.
    body: wireBody as AdjudicationInput,
    signal,
  });
  return normalizeDecisionCase(unwrap(result));
}

export interface DecisionCaseFilters {
  issueId?: number;
  ruleId?: string;
  version?: string;
}

/**
 * T-038 exposes Decision Case lookup before the endpoint is added to the
 * approved OpenAPI baseline. Keep this small adapter isolated so Workspace can
 * reuse the component and remove the adapter once the contract catches up.
 */
export async function getDecisionCases(
  filters: DecisionCaseFilters,
  signal?: AbortSignal,
): Promise<DecisionCase[]> {
  const url = new URL('/api/decision-cases/', apiBaseUrl());
  if (filters.issueId) url.searchParams.set('issue', String(filters.issueId));
  if (filters.ruleId?.trim()) url.searchParams.set('rule_id', filters.ruleId.trim());
  if (filters.version?.trim()) url.searchParams.set('version', filters.version.trim());

  let response: Response;
  try {
    response = await fetch(new Request(url, { credentials: 'include', cache: 'no-store', signal }));
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiRequestError(0);
  }

  const payload: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    const detail = readErrorDetail(payload);
    if (
      typeof window !== 'undefined' &&
      (response.status === 401 ||
        (response.status === 403 && detail?.code === 'NOT_AUTHENTICATED'))
    ) {
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail }));
    }
    throw new ApiRequestError(response.status, payload, response.headers);
  }
  if (!Array.isArray(payload)) throw new ApiRequestError(500);
  return (payload as DecisionCase[]).map(normalizeDecisionCase);
}
