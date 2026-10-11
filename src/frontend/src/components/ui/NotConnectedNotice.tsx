import React from 'react';
import { Icon } from '@/components/ui/Icon';

export const NOT_CONNECTED_MESSAGE = 'Chức năng vẫn chưa được kết nối với server';

/**
 * Cảnh báo vùng giao diện đã dựng theo thiết kế nhưng chưa có API (M-FE01).
 * Một cảnh báo cho mỗi vùng. Gỡ khi vùng đó đã nối API thật.
 */
export function NotConnectedNotice({ detail, className = '' }: { detail?: string; className?: string }) {
  let cleanDetail = detail?.trim();
  if (cleanDetail) {
    if (cleanDetail.startsWith(NOT_CONNECTED_MESSAGE)) {
      cleanDetail = cleanDetail.slice(NOT_CONNECTED_MESSAGE.length).replace(/^[.\s]+/, '');
    }
    cleanDetail = cleanDetail
      .replace(/^Chức năng\s+(.*?)\s+chưa được kết nối(?: với server)?(?:\s+trong FE-01)?$/i, '$1')
      .replace(/\s+trong FE-01$/i, '')
      .replace(/^[.\s]+/, '')
      .trim();
  }

  return (
    <div className={`lx-notice lx-notice--warning ${className}`.trim()} role="status">
      <Icon name="alert" className="lx-notice__ico" />
      <span>{NOT_CONNECTED_MESSAGE}{cleanDetail ? `. ${cleanDetail}` : ''}</span>
    </div>
  );
}
