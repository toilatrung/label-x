import React from 'react';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { SampleDataBadge } from '@/components/ui/SampleDataBadge';

/** Một cảnh báo cho mỗi vùng: nhãn dữ liệu minh họa kèm "chưa kết nối server". */
export function DemoRegionNotice({ className = '' }: { className?: string }) {
  return (
    <div className={`lx-actions ${className}`.trim()}>
      <SampleDataBadge />
      <NotConnectedNotice />
    </div>
  );
}
