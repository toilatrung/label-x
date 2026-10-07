'use client';

import React from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { ROLE_LABELS } from '@/lib/auth/roles';

interface ContextBarProps {
  datasetName?: string;
  isReadOnly?: boolean;
  guidelineVersion?: string;
  taxonomyVersion?: string;
  activeRun?: string;
}

export function ContextBar({
  datasetName = 'Road Vision Urban · v1.4',
  isReadOnly = false,
  guidelineVersion = 'v1.2',
  taxonomyVersion = 'v3',
  activeRun = '#QC-091 · PARTIAL',
}: ContextBarProps) {
  const { user } = useAuth();
  const roleLabel = user ? ROLE_LABELS[user.role] : 'Khách';

  return (
    <div className="lx-ctxbar">
      <div className="lx-ctx">
        {/* Chip Dataset */}
        <div className="lx-chip lx-chip--static">
          <span className="lx-chip__k">Dataset:</span>
          <span className="lx-chip__v">{datasetName}</span>
          {isReadOnly && <span className="lx-tag lx-tag--ro">read-only</span>}
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
