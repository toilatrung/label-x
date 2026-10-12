'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { ROLE_LABELS } from '@/lib/auth/roles';
import { isMockAuth } from '@/lib/auth/config';

export type RunState = 'checked' | 'partial' | 'running' | 'failed';

// Chấm trạng thái Quality Control Run theo ContextBarStates.dc.html; tên trạng thái nằm ở tooltip và aria-label.
const RUN_STATES: Record<RunState, { label: string; tone: string }> = {
  checked: { label: 'Checked', tone: 'lx-dot--success' },
  partial: { label: 'Partial', tone: 'lx-dot--warning' },
  running: { label: 'Running', tone: 'lx-dot--info' },
  failed: { label: 'Failed', tone: 'lx-dot--danger' },
};

interface ContextBarProps {
  datasetName?: string;
  datasetIdOverride?: number;
  snapshotName?: string;
  /** Revision của Snapshot đã khoá, ví dụ "rev f02a6d". */
  snapshotRevision?: string;
  isReadOnly?: boolean;
  guidelineVersion?: string;
  taxonomyVersion?: string;
  activeRun?: string;
  runState?: RunState;
  scopeName?: string;
}

const Chevron = () => <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 4.5 6 7.5 9 4.5" /></svg>;

export function ContextBar({
  datasetName,
  datasetIdOverride,
  snapshotName = 'Chưa chọn',
  snapshotRevision,
  isReadOnly = false,
  guidelineVersion = '—',
  taxonomyVersion = '—',
  activeRun = 'Chưa chọn',
  runState,
  scopeName = 'Toàn dataset',
}: ContextBarProps) {
  const { user, session, datasetId, setDatasetId } = useAuth();
  const roleLabel = user?.role ? ROLE_LABELS[user.role] : 'Chưa có quyền trong phạm vi này';
  const effectiveDatasetId = datasetIdOverride ?? datasetId;
  const datasetLabel = effectiveDatasetId === null ? 'Chưa chọn'
    : (datasetName ?? `${isMockAuth ? 'Dataset mẫu' : 'Dataset'} #${effectiveDatasetId}`);
  // Dataset chọn được trong phạm vi quyền của phiên; vai trò toàn hệ thống chọn dataset ở màn hình làm việc.
  const options = [...new Set(session?.roles.flatMap((assignment) => (assignment.dataset_id === null ? [] : [assignment.dataset_id])) ?? [])];
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, [open]);

  const datasetContent = <>
    <span className="lx-chip__k">Dataset:</span>
    <span className="lx-chip__v">{datasetLabel}</span>
    {isReadOnly && <span className="lx-tag lx-tag--ro">read-only</span>}
  </>;
  const run = runState ? RUN_STATES[runState] : null;

  return (
    <div className="lx-ctxbar" aria-label="Ngữ cảnh làm việc">
      <div className="lx-row lx-context-items">
        {options.length > 1 && datasetIdOverride === undefined ? (
          <div className="lx-ctx" ref={root}>
            <button ref={trigger} type="button" className="lx-chip" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
              {datasetContent}<Chevron />
            </button>
            {open && <div className="lx-menu" role="menu">
              <div className="lx-menu__head">Dataset và Version</div>
              {options.map((id) => <button key={id} type="button" role="menuitem" className={`lx-menu__item${id === datasetId ? ' is-active' : ''}`}
                onClick={() => { setDatasetId(id); setOpen(false); }}>
                <span className="lx-menu__t">{isMockAuth ? 'Dataset mẫu' : 'Dataset'} #{id}</span>
              </button>)}
            </div>}
          </div>
        ) : <div className="lx-chip lx-chip--static">{datasetContent}</div>}

        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Quality Control Run:</span>
          <span className="lx-chip__v lx-mono">{activeRun}</span>
          {run && <span className={`lx-dot ${run.tone}`} role="img" aria-label={`Trạng thái run: ${run.label}`} title={`Trạng thái: ${run.label}`} />}
        </div>

        <div className="lx-chip lx-chip--static" title="Snapshot bất biến">
          <span className="lx-chip__k">Snapshot:</span>
          <span className="lx-chip__v lx-mono">{snapshotName}</span>
          {snapshotRevision && <span className="lx-chip__rev lx-mono">{snapshotRevision}</span>}
          {snapshotName !== 'Chưa chọn' && <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" role="img" aria-label="Đã khoá"><rect x="3.5" y="7" width="9" height="6.5" rx="1.5" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" /></svg>}
        </div>

        {effectiveDatasetId !== null && <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Phạm vi:</span>
          <span className="lx-chip__v">{scopeName}</span>
        </div>}

        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Guideline:</span>
          <span className="lx-chip__v">{guidelineVersion}</span>
        </div>

        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Taxonomy:</span>
          <span className="lx-chip__v">{taxonomyVersion}</span>
        </div>

        <div className="lx-chip lx-chip--static lx-chip--role">
          <span className="lx-chip__k">Vai trò:</span>
          <span className="lx-chip__v lx-chip__v--primary">{roleLabel}</span>
        </div>
      </div>
    </div>
  );
}
