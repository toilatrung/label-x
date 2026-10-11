import React from 'react';
import { Icon } from '@/components/ui/Icon';

export const NOT_CONNECTED_MESSAGE = 'Chức năng vẫn chưa được kết nối với server';

/**
 * Cảnh báo vùng giao diện đã dựng theo thiết kế nhưng chưa có API (M-FE01).
 * Một cảnh báo cho mỗi vùng. Gỡ khi vùng đó đã nối API thật.
 */
export function NotConnectedNotice({ detail, className = '' }: { detail?: string; className?: string }) {
  return (
    <div className={`lx-notice lx-notice--warning ${className}`.trim()} role="status">
      <Icon name="alert" className="lx-notice__ico" />
      <span>{NOT_CONNECTED_MESSAGE}{detail ? `. ${detail}` : ''}</span>
    </div>
  );
}
