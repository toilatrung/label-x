'use client';

import React from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, canAccessReview, canAccessReports } from '@/lib/auth/roles';

export type FlowModule = 'analysis' | 'review' | 'reports';
const FLOWS = {
  analysis: { title: 'Phân tích chất lượng', steps: ['Snapshot', 'Cấu hình phân tích', 'Lịch sử thực thi'], permission: canAccessAnalysis },
  review: { title: 'Trung tâm kiểm tra', steps: ['Hàng đợi kiểm tra', 'Không gian kiểm tra', 'Theo dõi sửa nhãn'], permission: canAccessReview },
  reports: { title: 'Báo cáo và phát hành', steps: ['Báo cáo chất lượng', 'Cổng chất lượng', 'Lịch sử phát hành'], permission: canAccessReports },
};

export function FlowNav({ flow, currentStep = 1 }: { flow: FlowModule; currentStep?: number }) {
  const { hasPermission } = useAuth();
  const definition = FLOWS[flow];
  if (!hasPermission(definition.permission, flow === 'review')) return null;
  return <nav className="lx-flow" aria-label={definition.title}>
    <span className="lx-flow__k">{definition.title}</span>
    <ol className="lx-flow__steps" style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', listStyle: 'none', margin: 0, padding: 0 }}>
      {definition.steps.map((title, index) => <li key={title} className={index + 1 === currentStep ? 'is-current' : ''}>
        <span aria-current={index + 1 === currentStep ? 'step' : undefined}>
          <span className="lx-flow__n">{index + 1}</span> {title}
        </span>
      </li>)}
    </ol>
    <span className="lx-flow__pos">Bước {currentStep}/3</span>
  </nav>;
}
