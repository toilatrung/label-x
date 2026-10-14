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
