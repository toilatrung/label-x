import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components } from '@/lib/api/contract';

/**
 * Evidence AI mới nhất của một issue (classifier hoặc Qwen), do backend MBE-01 trả trong
 * `GET /api/frames/{id}/workspace/` ở trường `ai_evidence`.
 *
 * Lệch contract: runtime (review/workspace.py, AiEvidenceSerializer) đã trả trường này nhưng
 * `docs/04-api/openapi.yaml` (FrameWorkspace) chưa khai báo, nên type được giữ cục bộ ở đây
 * và đọc phòng thủ. Khi contract bổ sung, thay bằng `components['schemas'][...]`.
 * Evidence AI chỉ là đề xuất; quyết định luôn thuộc người review.
 */
export interface AiEvidence {
  issue_id: number;
  candidate_id: number;
  evaluation_id: number;
  generation: number;
  evaluation_source: string;
  status: string;
  source: string;
  reason_code: string | null;
  reasons: string[];
  review_required: boolean;
  suggestion: {
    status?: string | null;
    class_name?: string | null;
    rationale?: string | null;
  } | null;
  evidence_refs: Record<string, unknown> | null;
  snapshot_revision: string;
  poll_url: string;
}

export type FrameWorkspace = components['schemas']['FrameWorkspace'] & {
  ai_evidence?: AiEvidence[];
};

type BBox = components['schemas']['BBox'];

/** Detector output uses xyxy arrays; the review API also accepts named coordinates. */
export function reviewBBox(value: unknown): BBox | null {
  const coords = Array.isArray(value) ? value : value && typeof value === 'object'
    ? ['x1', 'y1', 'x2', 'y2'].map(key => (value as Record<string, unknown>)[key]) : [];
  if (coords.length !== 4 || !coords.every(v => typeof v === 'number' && Number.isFinite(v))) return null;
  const [x1, y1, x2, y2] = coords as number[];
  return x2 > x1 && y2 > y1 ? { x1, y1, x2, y2 } : null;
}

export interface WorkspacePrediction {
  id: string;
  issueId: number | null;
  bbox: BBox;
  label: string;
  source: string;
  confidence?: number;
}

export function workspacePredictions(data: FrameWorkspace): WorkspacePrediction[] {
  const predictions: WorkspacePrediction[] = [];
  for (const candidate of data.predictions ?? []) {
    const issueId = data.ai_evidence?.find(e => e.candidate_id === candidate.candidate_id)?.issue_id ?? null;
    const evidence = Array.isArray(candidate.evidence) ? candidate.evidence : [candidate.evidence];
    evidence.forEach((raw: unknown, index: number) => {
      if (!raw || typeof raw !== 'object') return;
      const ev = raw as Record<string, unknown>;
      const bbox = reviewBBox(ev.prediction_bbox);
      if (!bbox) return;
      predictions.push({ id: `candidate-${candidate.candidate_id}-${index}`, issueId, bbox,
        label: String(ev.prediction_class ?? ev.class_name ?? 'object'), source: candidate.engine,
        confidence: typeof ev.confidence === 'number' && Number.isFinite(ev.confidence) ? ev.confidence : undefined });
    });
  }
  // Older workspace responses may only carry prediction evidence inside issues.
  if (!data.predictions?.length) {
    for (const issue of data.issues) {
      issue.evidence?.forEach((ev, index) => {
        const bbox = reviewBBox(ev.prediction_bbox);
        if (bbox) predictions.push({ id: `issue-${issue.id}-${index}`, issueId: issue.id, bbox,
          label: ev.prediction_class ?? 'object', source: ev.engine, confidence: ev.confidence ?? undefined });
      });
    }
  }
  for (const item of data.ai_evidence ?? []) {
    if (!['qwen', 'gemini'].includes(item.source) || item.status !== 'completed' || item.suggestion?.status !== 'checked'
      || !item.suggestion.class_name) continue;
    const issue = data.issues.find(i => i.id === item.issue_id);
    const evidenceBox = issue?.evidence?.map(ev => reviewBBox(ev.prediction_bbox)).find(Boolean);
    const bbox = evidenceBox ?? reviewBBox(issue?.anchor?.bbox);
    if (!bbox) continue;
    predictions.push({ id: `${item.source}-${item.evaluation_id}`, issueId: item.issue_id, bbox,
      label: item.suggestion.class_name, source: `${item.source === 'gemini' ? 'Gemini' : 'Qwen'} · mô hình 2` });
  }
  return predictions;
}
export type SimilarCase = components['schemas']['SimilarCase'];
export type PaginatedSimilarCaseList = components['schemas']['PaginatedSimilarCaseList'];

/**
 * Nguồn chuẩn của Review Workspace: superset của `GET /api/frames/{id}/issues/`
 * (frame + image_url presigned, annotation, prediction, engine, issue, snapshot_revision)
 * kèm lease đang mở, hàng đợi, số issue chưa quyết định và evidence AI.
 * Trả nguyên kết quả openapi-fetch để caller tự xử lý 403/404 và chống phản hồi cũ.
 */
export async function fetchFrameWorkspace(frameId: number, signal?: AbortSignal) {
  const result = await apiClient.GET('/api/frames/{id}/workspace/', {
    params: { path: { id: frameId } },
    signal,
  });
  return {
    ...result,
    data: result.data as FrameWorkspace | undefined,
  };
}

/** Lọc evidence AI hợp lệ của một issue; bỏ qua mục sai shape thay vì làm vỡ panel. */
export function aiEvidenceForIssue(
  list: unknown,
  issueId: number
): AiEvidence[] {
  if (!Array.isArray(list)) return [];
  return list.filter(
    (item): item is AiEvidence =>
      typeof item === 'object' &&
      item !== null &&
      (item as AiEvidence).issue_id === issueId &&
      typeof (item as AiEvidence).status === 'string' &&
      typeof (item as AiEvidence).source === 'string'
  );
}

/** Case tương tự đã phân xử của issue (MBE-02), giảm dần theo độ giống. */
export async function getSimilarCases(
  issueId: number,
  signal?: AbortSignal
): Promise<PaginatedSimilarCaseList> {
  const result = await apiClient.GET('/api/issues/{id}/similar-cases/', {
    params: { path: { id: issueId } },
    signal,
  });
  if (result.error || !result.data) {
    throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  }
  return result.data;
}
