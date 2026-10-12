'use client';

import React from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { ROLE_LABELS } from '@/lib/auth/roles';
import { isMockAuth } from '@/lib/auth/config';

interface ContextBarProps {
  datasetName?: string;
  datasetIdOverride?: number;
  snapshotName?: string;
  isReadOnly?: boolean;
  guidelineVersion?: string;
  taxonomyVersion?: string;
  activeRun?: string;
}

export function ContextBar({
  datasetName,
  datasetIdOverride,
  snapshotName = 'Chưa chọn',
  isReadOnly = false,
  guidelineVersion = '—',
  taxonomyVersion = '—',
  activeRun = 'Chưa chọn',
}: ContextBarProps) {
  const { user, datasetId } = useAuth();
  const roleLabel = user?.role ? ROLE_LABELS[user.role] : 'Chưa có quyền trong phạm vi này';

  return (
    <div className="lx-ctxbar" aria-label="Ngữ cảnh làm việc">
      <div className="lx-row lx-context-items">
        {/* Chip Dataset */}
        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Dataset:</span>
          <span className="lx-chip__v">{(datasetIdOverride ?? datasetId) === null ? 'Chưa chọn' :
            (datasetName ?? `${isMockAuth ? 'Dataset mẫu' : 'Dataset'} #${datasetIdOverride ?? datasetId}`)}</span>
          {isReadOnly && <span className="lx-tag lx-tag--ro">read-only</span>}
        </div>

        {/* Chip QC Run */}
        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Quality Control Run:</span>
          <span className="lx-chip__v" style={{ color: 'var(--warning)' }}>{activeRun}</span>
        </div>

        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Snapshot:</span>
          <span className="lx-chip__v">{snapshotName}</span>
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

        {/* Chip Vai trò hiện tại */}
        <div className="lx-chip lx-chip--static" style={{ marginLeft: 'auto' }}>
          <span className="lx-chip__k">Vai trò:</span>
          <span className="lx-chip__v" style={{ color: 'var(--primary)' }}>{roleLabel}</span>
        </div>
      </div>
    </div>
  );
}
