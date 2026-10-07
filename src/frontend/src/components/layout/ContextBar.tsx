'use client';

import React from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { ROLE_LABELS } from '@/lib/auth/roles';
import { isMockAuth } from '@/lib/auth/config';

interface ContextBarProps {
  datasetName?: string;
  isReadOnly?: boolean;
  guidelineVersion?: string;
  taxonomyVersion?: string;
  activeRun?: string;
}

export function ContextBar({
  datasetName,
  isReadOnly = false,
  guidelineVersion = '—',
  taxonomyVersion = '—',
  activeRun = 'Chưa chọn',
}: ContextBarProps) {
  const { user, datasetId } = useAuth();
  const roleLabel = user?.role ? ROLE_LABELS[user.role] : 'Chưa có quyền trong phạm vi này';

  return (
    <div className="lx-ctxbar">
      <div className="lx-ctx">
        {/* Chip Dataset */}
        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Dataset:</span>
          <span className="lx-chip__v">{datasetId === null ? 'Chưa chọn' :
            (datasetName ?? `${isMockAuth ? 'Dataset mẫu' : 'Dataset'} #${datasetId}`)}</span>
          {isReadOnly && <span className="lx-tag lx-tag--ro">read-only</span>}
        </div>

        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Snapshot:</span>
          <span className="lx-chip__v">Chưa chọn</span>
        </div>

        {/* Chip Guideline */}
        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Guideline:</span>
          <span className="lx-chip__v">{guidelineVersion}</span>
        </div>

        {/* Chip Taxonomy */}
        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Taxonomy:</span>
          <span className="lx-chip__v">{taxonomyVersion}</span>
        </div>

        {/* Chip QC Run */}
        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Run:</span>
          <span className="lx-chip__v" style={{ color: 'var(--warning)' }}>{activeRun}</span>
        </div>

        {/* Chip Vai trò hiện tại */}
        <div className="lx-chip lx-chip--static" style={{ marginLeft: 'auto' }}>
          <span className="lx-chip__k">Vai trò:</span>
          <span className="lx-chip__v" style={{ color: 'var(--primary)' }}>{roleLabel}</span>
        </div>
      </div>
    </div>
  );
}
