import { apiClient, ApiRequestError } from '@/lib/api/client';
import type { components } from '@/lib/api/contract';

/** Một lần đánh giá AI của candidate (M04C-02). Kết quả chỉ là đề xuất, không tạo ReviewDecision. */
export type CandidateEvaluation = components['schemas']['CandidateEvaluation'];

export const TERMINAL_EVALUATION_STATUSES = ['completed', 'failed', 'cancelled'];
/** Backend giới hạn reason 500 ký tự (orchestration/evaluation_guard.py). */
export const MAX_EVALUATION_REASON = 500;

function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error || result.data === undefined) throw new ApiRequestError(result.response.status, result.error, result.response.headers);
  return result.data;
}

/**
 * POST /api/candidates/{id}/evaluations/ → 202. Cùng key + cùng nội dung trả lại đúng evaluation đã tạo,
 * nên khi lỗi mạng caller gửi lại với key cũ. expected_revision là revision Snapshot của run.
 */
export async function evaluateCandidate(candidateId: number, body: { reason: string; expected_revision: string }, key: string) {
  const csrf = await apiClient.GET('/api/auth/csrf/', { cache: 'no-store' });
  if (csrf.error || !csrf.response.ok) throw new ApiRequestError(csrf.response.status, csrf.error, csrf.response.headers);
  const reply = await apiClient.POST('/api/candidates/{id}/evaluations/', {
    params: { path: { id: candidateId }, header: { 'Idempotency-Key': key } }, body,
  });
  if (reply.response.status !== 202) throw new ApiRequestError(reply.response.status, reply.error, reply.response.headers);
  return unwrap(reply);
}

export async function getCandidateEvaluation(id: number, signal?: AbortSignal) {
  return unwrap(await apiClient.GET('/api/candidate-evaluations/{id}/', { params: { path: { id } }, signal, cache: 'no-store' }));
}

/** Thông báo lỗi riêng cho các mã backend trả ở thao tác đánh giá lại. */
export function evaluationErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiRequestError)) return fallback;
  if (error.status === 409 && error.detail?.details?.reason_code === 'stale_revision') {
    return 'Snapshot đã có revision mới hơn revision đang mở. Vui lòng tải lại trang rồi thử lại.';
  }
  // 422: run đã huỷ, VLM chưa bật hoặc thiếu taxonomy; message backend viết cho người dùng.
  if (error.status === 422 && error.detail?.message) return error.detail.message;
  return error.message;
}
