'use client';

import React from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, canAccessReview, canAccessReports } from '@/lib/auth/roles';
import type { UserRole } from '@/types/auth';

export type FlowModule = 'analysis' | 'review' | 'reports';

interface FlowStep { href: string; title: string; description?: string }

// Nhãn và liên kết lấy từ docs/design/screens/FlowNav.dc.html.
const FLOWS: Record<FlowModule, { title: string; steps: FlowStep[]; permission: (role: UserRole) => boolean }> = {
  analysis: { title: 'Quy trình phân tích', permission: canAccessAnalysis, steps: [
    { href: '/analysis/snapshots', title: 'Snapshot' },
    { href: '/analysis/config', title: 'Analysis Configuration' },
    { href: '/analysis/history', title: 'Execution History' }] },
  review: { title: 'Quy trình review', permission: canAccessReview, steps: [
    { href: '/review', title: 'Hàng đợi', description: 'Ảnh cần kiểm tra' },
    { href: '/review/workspace', title: 'Kiểm tra ảnh', description: 'Xem và đánh giá' },
    { href: '/review/rework', title: 'Theo dõi sửa', description: 'Kiểm tra lại sau khi sửa' }] },
  reports: { title: 'Quy trình nghiệm thu', permission: canAccessReports, steps: [
    { href: '/reports', title: 'Quality Report' },
    { href: '/reports/gate', title: 'Quality Gate' },
    { href: '/reports/releases', title: 'Release History' }] },
};

const ARROW_PREV = 'M10 3 5 8l5 5';
const ARROW_NEXT = 'M6 3l5 5-5 5';

function Arrow({ step, direction }: { step?: FlowStep; direction: 'prev' | 'next' }) {
  const tip = step ? `${direction === 'prev' ? 'Bước trước' : 'Bước sau'}: ${step.title}`
    : direction === 'prev' ? 'Đây là bước đầu tiên' : 'Đây là bước cuối cùng';
  const icon = <svg viewBox="0 0 16 16" aria-hidden="true"><path d={direction === 'prev' ? ARROW_PREV : ARROW_NEXT} /></svg>;
  if (!step) return <span className="lx-iconbtn lx-flow__arrow is-off" role="img" aria-label={tip} data-tip={tip}>{icon}</span>;
  return <Link className="lx-iconbtn lx-flow__arrow" href={step.href} aria-label={tip} data-tip={tip}>{icon}</Link>;
}

export function FlowNav({ flow, currentStep = 1 }: { flow: FlowModule; currentStep?: number }) {
  const { hasPermission } = useAuth();
  const definition = FLOWS[flow];
  if (!hasPermission(definition.permission, flow === 'review')) return null;
  const index = Math.min(Math.max(currentStep, 1), definition.steps.length) - 1;
  return <nav className="lx-flow" aria-label={definition.title}>
    <Arrow direction="prev" step={definition.steps[index - 1]} />
    <ol className="lx-flow__steps">
      {definition.steps.map((step, i) => <li key={step.href} className={`lx-flow__step${i === index ? ' is-active' : ''}`}>
        <Link href={step.href} aria-current={i === index ? 'step' : undefined}>
          <span className="lx-flow__n">{i + 1}</span>
          <span>{step.title}{step.description && <small className="lx-flow__description">{step.description}</small>}</span>
        </Link>
      </li>)}
    </ol>
    <span className="lx-flow__pos">Bước {index + 1} / {definition.steps.length}</span>
    <Arrow direction="next" step={definition.steps[index + 1]} />
  </nav>;
}
