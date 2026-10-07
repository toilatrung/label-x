'use client';

import React from 'react';
import Link from 'next/link';

interface FlowStep {
  n: number;
  title: string;
  href: string;
  current?: boolean;
}

interface FlowNavProps {
  flowLabel?: string;
  currentStep?: number;
}

export function FlowNav({ flowLabel = 'Quy trình kiểm soát chất lượng', currentStep = 1 }: FlowNavProps) {
  const steps: FlowStep[] = [
    { n: 1, title: 'Phân tích tự động', href: '/analysis', current: currentStep === 1 },
    { n: 2, title: 'Kiểm tra thủ công', href: '/review', current: currentStep === 2 },
    { n: 3, title: 'Phê duyệt phát hành', href: '/reports', current: currentStep === 3 },
  ];

  return (
    <nav className="lx-flow" aria-label={flowLabel}>
      <span className="lx-flow__k">{flowLabel}</span>

      <ol className="lx-flow__steps" style={{ display: 'flex', alignItems: 'center', listStyle: 'none', margin: 0, padding: 0, gap: 'var(--space-2)' }}>
        {steps.map((s, idx) => (
          <React.Fragment key={s.n}>
            <li className={s.current ? 'is-current' : ''}>
              <Link
                href={s.href}
                aria-current={s.current ? 'step' : undefined}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  textDecoration: 'none',
                  fontSize: '13px',
                  fontWeight: s.current ? 600 : 400,
                  color: s.current ? 'var(--ink)' : 'var(--ink-muted)',
                }}
              >
                <span
                  className="lx-flow__n"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '18px',
                    height: '18px',
                    borderRadius: '50%',
                    background: s.current ? 'var(--primary)' : 'var(--border)',
                    color: s.current ? 'var(--on-primary)' : 'var(--ink-muted)',
                    fontSize: '11px',
                    fontWeight: 600,
                  }}
                >
                  {s.n}
                </span>
                {s.title}
              </Link>
            </li>
            {idx < steps.length - 1 && (
              <li aria-hidden="true" style={{ display: 'flex', alignItems: 'center' }}>
                <svg className="lx-flow__sep" viewBox="0 0 12 12" style={{ width: 12, height: 12, color: 'var(--border-strong)' }}>
                  <path d="M4.5 3 7.5 6 4.5 9" fill="none" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </li>
            )}
          </React.Fragment>
        ))}
      </ol>

      <span className="lx-flow__pos" style={{ marginLeft: 'auto', fontSize: '12px', color: 'var(--ink-subtle)' }}>
        Bước {currentStep}/3
      </span>
    </nav>
  );
}
