'use client';

import React from 'react';
import { TopBar } from '@/components/layout/TopBar';
import { ContextBar } from '@/components/layout/ContextBar';
import { FlowNav, type FlowModule } from '@/components/layout/FlowNav';

interface AppShellProps {
  children: React.ReactNode;
  pageHeader?: React.ReactNode;
  activeKey?: string;
  activeItem?: string;
  flowStep?: number;
  showFlowNav?: boolean;
  context?: React.ComponentProps<typeof ContextBar>;
}

export function AppShell({
  children,
  pageHeader,
  activeKey,
  activeItem,
  flowStep = 1,
  showFlowNav = true,
  context,
}: AppShellProps) {
  const [openMenu, setOpenMenu] = React.useState<string | null>(null);
  const closeAll = React.useCallback(() => setOpenMenu(null), []);

  return (
    <div className="lx" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--canvas)', position: 'relative' }}>
      <TopBar
        activeKey={activeKey}
        activeItem={activeItem}
        openMenuId={openMenu}
        onOpenMenuChange={setOpenMenu}
        variant={activeKey === 'overview' ? 'canonical' : 'default'}
      />
      <ContextBar
        {...context}
        openMenuId={openMenu}
        onOpenMenuChange={setOpenMenu}
      />
      {openMenu && <div className="lx-backdrop" onClick={closeAll} />}
      <main
        className={activeKey === 'overview' ? 'lx-page' : 'lx-app-content'}
        style={activeKey === 'overview' ? { width: '100%', boxSizing: 'border-box' } : undefined}
      >
        {pageHeader}
        {showFlowNav && activeKey && ['analysis', 'review', 'reports'].includes(activeKey) &&
        <FlowNav flow={activeKey as FlowModule} currentStep={flowStep} />}
        {children}
      </main>
    </div>
  );
}
