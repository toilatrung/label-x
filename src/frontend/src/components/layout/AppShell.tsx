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
  flowNavVariant?: 'stepper' | 'tabs';
  context?: React.ComponentProps<typeof ContextBar>;
}

export function AppShell({
  children,
  pageHeader,
  activeKey,
  flowStep = 1,
  showFlowNav = true,
  flowNavVariant,
  context,
}: AppShellProps) {
  const resolvedVariant = flowNavVariant ?? (['analysis', 'reports'].includes(activeKey ?? '') ? 'tabs' : 'stepper');
  return (
    <div className="lx lx-shell">
      <TopBar activeKey={activeKey} />
      <ContextBar {...context} />
      <main className="lx-app-content">
        {pageHeader}
        {showFlowNav && activeKey && ['analysis', 'review', 'reports'].includes(activeKey) &&
        <FlowNav flow={activeKey as FlowModule} currentStep={flowStep} variant={resolvedVariant} />}
        {children}
      </main>
    </div>
  );
}
