'use client';

import React from 'react';
import { TopBar } from '@/components/layout/TopBar';
import { ContextBar } from '@/components/layout/ContextBar';
import { FlowNav, type FlowModule } from '@/components/layout/FlowNav';

interface AppShellProps {
  children: React.ReactNode;
  pageHeader?: React.ReactNode;
  activeKey?: string;
  flowStep?: number;
  showFlowNav?: boolean;
  context?: React.ComponentProps<typeof ContextBar>;
}

export function AppShell({
  children,
  pageHeader,
  activeKey,
  flowStep = 1,
  showFlowNav = true,
  context,
}: AppShellProps) {
  return (
    <div className="lx" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--canvas)' }}>
      <TopBar activeKey={activeKey} />
      <ContextBar {...context} />
      <main className="lx-app-content">
        {pageHeader}
        {showFlowNav && activeKey && ['analysis', 'review', 'reports'].includes(activeKey) &&
        <FlowNav flow={activeKey as FlowModule} currentStep={flowStep} />}
        {children}
      </main>
    </div>
  );
}
