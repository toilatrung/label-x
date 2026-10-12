'use client';

import React, { useEffect, useRef, useState } from 'react';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { SampleDataBadge } from '@/components/ui/SampleDataBadge';

const ATTENTION_EVENT = 'lx:notice-attention';

/** Nút ghi nằm ngoài vùng (vd tiêu đề trang) gọi hàm này để nhấn mạnh cảnh báo sẵn có, không thêm cảnh báo mới. */
export function signalNoticeAttention() {
  window.dispatchEvent(new Event(ATTENTION_EVENT));
}

/**
 * Một cảnh báo cho mỗi vùng: nhãn dữ liệu minh họa kèm "chưa kết nối server".
 * `pulse` tăng lên khi nút ghi trong vùng được bấm; `listenGlobal` cho vùng nhận tín hiệu từ nút ngoài vùng.
 * Nhấn mạnh bằng viền và chuyển focus tới cảnh báo.
 */
export function DemoRegionNotice({ className = '', pulse = 0, listenGlobal = false }: { className?: string; pulse?: number; listenGlobal?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const [signalled, setSignalled] = useState(false);
  useEffect(() => {
    if (!listenGlobal) return;
    const onSignal = () => { setSignalled(true); ref.current?.focus(); };
    window.addEventListener(ATTENTION_EVENT, onSignal);
    return () => window.removeEventListener(ATTENTION_EVENT, onSignal);
  }, [listenGlobal]);
  useEffect(() => { if (pulse > 0) ref.current?.focus(); }, [pulse]);
  const active = pulse > 0 || signalled;
  return (
    <div className={`lx-actions ${className}`.trim()}>
      <SampleDataBadge />
      <div ref={ref} tabIndex={-1} className={active ? 'lx-attn' : undefined} data-attention={active || undefined}><NotConnectedNotice /></div>
    </div>
  );
}
