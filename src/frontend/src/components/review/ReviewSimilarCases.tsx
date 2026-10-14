'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/lib/api/errors';
import { useAuth } from '@/lib/auth/auth-context';
import { getSimilarCases } from '@/lib/review/workspace-api';

const OUTCOME_LABELS: Record<string, string> = {
  confirm: 'Xác nhận lỗi',
  reject: 'Bác bỏ',
  guideline_gap: 'Thiếu hướng dẫn',
};

export interface ReviewSimilarCasesProps {
  issueId: number;
}

/**
 * Vùng "Case tương tự đã phân xử" của Review Workspace, nối `GET /api/issues/{id}/similar-cases/`
 * (MBE-02). Chỉ đọc; case là tham khảo, không thay quyết định của người review.
 */
export function ReviewSimilarCases({ issueId }: ReviewSimilarCasesProps) {
  const { session } = useAuth();
  const query = useQuery({
    queryKey: ['review-similar-cases', session?.user.id ?? null, issueId],
    queryFn: ({ signal }) => getSimilarCases(issueId, signal),
    retry: false,
  });

  const results = query.data?.results ?? [];
  const countLabel = query.isPending
    ? 'đang tải'
    : query.isError
      ? 'lỗi'
      : `${results.length}${query.data?.next ? '+' : ''}`;

  return (
    <details data-testid="review-similar-cases">
      <summary className="lx-ws__summary">Case tương tự đã phân xử ({countLabel})</summary>
      {query.isPending ? (
        <p className="lx-muted lx-ws__note" role="status">
          Đang tải case tương tự...
        </p>
      ) : query.isError ? (
        <div className="lx-callout lx-mt-2" role="alert">
          <span className="lx-callout__text">
            Không tải được case tương tự: {errorMessage(query.error)}
          </span>
          <button type="button" className="lx-btn lx-btn--sm lx-ml-3" onClick={() => void query.refetch()}>
            Thử lại
          </button>
        </div>
      ) : results.length === 0 ? (
        <p className="lx-muted lx-ws__note">Chưa có case đã phân xử cùng quy tắc hoặc cùng nhóm lỗi với issue này.</p>
      ) : (
        <div className="lx-mt-2">
          {results.map(({ case: item, similarity }) => (
            <p key={item.id} className="lx-muted lx-ws__note--tight">
              <span className="lx-mono">CASE-{String(item.id).padStart(3, '0')}</span>
              {' · '}
              {item.reason || `Quy tắc ${item.rule_id}`}
              {item.correct_label ? (
                <>
                  {' → '}
                  <b>{item.correct_label}</b>
                </>
              ) : null}
              <span className="lx-subtle">
                {' · '}
                {OUTCOME_LABELS[item.outcome] ?? item.outcome} · {item.rule_id} · độ giống{' '}
                {Number.isFinite(similarity) ? similarity.toFixed(2) : '—'}
              </span>
            </p>
          ))}
          {query.data?.next ? (
            <p className="lx-subtle lx-text-12 lx-ws__note--tight">
              Đang hiển thị {results.length} case giống nhất.
            </p>
          ) : null}
        </div>
      )}
    </details>
  );
}
