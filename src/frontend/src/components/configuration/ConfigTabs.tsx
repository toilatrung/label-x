'use client';

import React from 'react';

export interface ConfigTab<K extends string> { key: K; label: string }

/** Thanh tab của màn Configuration, khớp `lx-tabs` trong thiết kế. */
export function ConfigTabs<K extends string>({ tabs, current, onPick, label }: {
  tabs: ConfigTab<K>[]; current: K; onPick: (key: K) => void; label: string;
}) {
  return (
    <div className="lx-tabs lx-tabs--inset" role="tablist" aria-label={label}>
      {tabs.map(tab => (
        <button key={tab.key} type="button" role="tab" aria-selected={current === tab.key}
          className={`lx-tab${current === tab.key ? ' is-active' : ''}`} onClick={() => onPick(tab.key)}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

/** Nút sửa dạng icon (bút chì). Hành động ghi chưa có API: bấm gọi onBlocked để hiện cảnh báo, không gọi API. */
export function EditIconButton({ label, onBlocked, disabled = false }: { label: string; onBlocked: () => void; disabled?: boolean }) {
  return (
    <button type="button" className="lx-iconbtn" data-tip={label} aria-label={label} disabled={disabled} onClick={onBlocked}>
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13l.7-3L10.5 3.2a1.4 1.4 0 0 1 2 2L5.7 12 3 13z" /></svg>
    </button>
  );
}
