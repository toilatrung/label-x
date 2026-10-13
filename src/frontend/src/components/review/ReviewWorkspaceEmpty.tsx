import React from 'react';
import Link from 'next/link';

/**
 * Trạng thái rỗng của Review Workspace khi route mở không có `frame_id`.
 * Workspace chỉ hiển thị dữ liệu thật từ `GET /api/frames/{id}/workspace/`; frame được nhận
 * qua hàng đợi Review Queues (lease), nên không dựng frame minh họa giả như thật ở đây.
 */
export function ReviewWorkspaceEmpty() {
  return (
    <div className="lx-card lx-card__body lx-ws__empty" data-testid="review-workspace-empty">
      <h2 className="lx-h2">Chưa có frame để review</h2>
      <p className="lx-muted">
        Nhận frame kế tiếp từ hàng đợi Review Queues để mở khung hình, annotation, bằng chứng và hướng dẫn liên quan.
        Lease giữ frame chỉ được cấp khi nhận từ hàng đợi.
      </p>
      <p className="lx-mt-3">
        <Link href="/review" className="lx-btn lx-btn--primary">
          Về hàng đợi
        </Link>
      </p>
    </div>
  );
}
