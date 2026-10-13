import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components, operations } from '@/lib/api/contract';

export type EscalationIssue = components['schemas']['Issue'];
export type EscalationPage = components['schemas']['PaginatedIssueList'];
export type AdjudicationInput = components['schemas']['AdjudicationCreate'];
export type DecisionCase = components['schemas']['DecisionCase'];
export type DecisionCaseDetail = components['schemas']['DecisionCaseDetail'];

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
): Promise<DecisionCase> {
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
