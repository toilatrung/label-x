'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth/auth-context';
import { ROLE_LABELS, canAccessAnalysis, canAccessReview, canAccessEscalations,
  canAccessReports, canAccessConfiguration, canAccessGuidelines } from '@/lib/auth/roles';
import { Icon } from '@/components/ui/Icon';

interface MenuItem { label: string; icon: string; href?: string; }
interface Module { key: string; label: string; href?: string; items?: MenuItem[]; }

export function TopBar({ activeKey }: { activeKey?: string }) {
  const { user, logout, hasPermission } = useAuth();
  const pathname = usePathname();
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const root = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const roleName = user?.role ? ROLE_LABELS[user.role] : 'Chưa có quyền trong phạm vi này';
  const initials = user?.fullName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || 'LX';
  const closeAll = () => setOpenMenu(null);
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpenMenu(null); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpenMenu(null); trigger.current?.focus(); } };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape); };
  }, []);

  const configItems: MenuItem[] = [];
  if (hasPermission(canAccessGuidelines)) configItems.push(
    { label: 'Rules & Thresholds', icon: 'rules', href: '/configuration/rules-thresholds' },
    { label: 'Models & Guidelines', icon: 'model', href: '/configuration/guidelines' });
  if (hasPermission(canAccessConfiguration)) configItems.push(
    { label: 'Workflow & Permissions', icon: 'users', href: '/configuration' });
  const modules: Module[] = [
    { key: 'overview', label: 'Overview', items: [{ label: 'Quality Control Home', icon: 'home', href: '/' },
      { label: 'Quality Summary', icon: 'chart' }] },
    ...(hasPermission(canAccessAnalysis) ? [{ key: 'analysis', label: 'Quality Analysis', href: '/analysis' }] : []),
    ...(hasPermission(canAccessReview, true) ? [{ key: 'review', label: 'Review Center', href: '/review' }] : []),
    ...(hasPermission(canAccessEscalations, true) ? [{ key: 'escalations', label: 'Escalations' }] : []),
    { key: 'calibration', label: 'Calibration & Audit', items: [
      { label: 'Performance Evaluation', icon: 'chart' }, { label: 'Ground Truth Benchmark', icon: 'target' },
      { label: 'Audit Sampling', icon: 'check' }, { label: 'Calibration', icon: 'scale' }] },
    ...(hasPermission(canAccessReports) ? [{ key: 'reports', label: 'Reports & Releases' }] : []),
    ...(configItems.length ? [{ key: 'configuration', label: 'Configuration', items: configItems }] : []),
  ];
  const active = pathname.startsWith('/configuration') ? 'configuration' : pathname.startsWith('/review') ? 'review'
    : pathname.startsWith('/analysis') ? 'analysis' : activeKey || 'overview';
  function toggle(key: string, event: React.MouseEvent<HTMLButtonElement>) {
    trigger.current = event.currentTarget;
    setOpenMenu(openMenu === key ? null : key);
  }
  function menuKey(event: React.KeyboardEvent<HTMLDivElement>) {
    const items = [...event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)')];
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (!items.length || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
      : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  }
  function triggerKey(event: React.KeyboardEvent<HTMLButtonElement>, key: string) {
    if (event.key !== 'ArrowDown') return;
    event.preventDefault(); trigger.current = event.currentTarget; setOpenMenu(key);
    requestAnimationFrame(() => root.current?.querySelector<HTMLElement>(`#nav-menu-${key} [role="menuitem"]:not(:disabled)`)?.focus());
  }
  return <header className="lx-topnav" ref={root}>
    <Link className="lx-logo" href="/" aria-label="Về Quality Control Home" onClick={closeAll}>Label<b>X</b></Link>
    <nav className="lx-nav" aria-label="Quality Control Navigation">
      {modules.map(module => <div className="lx-nav__group" key={module.key}>
        {module.items ? <>
          <button className={`lx-navbtn${active === module.key ? ' is-active' : ''}`} type="button"
            aria-haspopup="menu" aria-expanded={openMenu === module.key} aria-controls={`nav-menu-${module.key}`}
            onClick={event => toggle(module.key, event)} onKeyDown={event => triggerKey(event, module.key)}>
            {module.label}<Icon name="chevron" />
          </button>
          {openMenu === module.key && <div className="lx-menu" role="menu" id={`nav-menu-${module.key}`} onKeyDown={menuKey}>
            {module.items.map(item => item.href ? <Link key={item.label} href={item.href} role="menuitem"
              className={`lx-menu__item${pathname === item.href ? ' is-active' : ''}`} aria-current={pathname === item.href ? 'page' : undefined}
              onClick={closeAll}><span className="lx-menu__t">{item.label}</span><Icon name={item.icon} /></Link>
              : <button key={item.label} className="lx-menu__item" type="button" role="menuitem" disabled title="Chưa khả dụng">
                <span className="lx-menu__t">{item.label}</span><Icon name={item.icon} /></button>)}
          </div>}
        </> : module.href ? <Link href={module.href} onClick={closeAll}
          className={`lx-navbtn${active === module.key ? ' is-active' : ''}`} aria-current={active === module.key ? 'page' : undefined}>{module.label}</Link>
          : <button className="lx-navbtn" type="button" disabled title="Chưa khả dụng">{module.label}</button>}
      </div>)}
    </nav>
    <div className="lx-userwrap">
      <button className="lx-user lx-user--btn" type="button" aria-haspopup="menu" aria-expanded={openMenu === 'user'}
        aria-controls="nav-menu-user" onClick={event => toggle('user', event)} onKeyDown={event => triggerKey(event, 'user')}>
        <span className="lx-avatar" aria-hidden="true">{initials}</span>
        <span className="lx-user__meta"><span className="lx-user__name">{user?.fullName || 'Khách'}</span><span className="lx-user__role">{roleName}</span></span>
        <Icon name="chevron" />
      </button>
      {openMenu === 'user' && <div className="lx-menu lx-menu--user" id="nav-menu-user" role="menu" onKeyDown={menuKey}>
        <button className="lx-menu__item" type="button" role="menuitem" onClick={() => { void logout(); closeAll(); }}>
          <Icon name="logout" /><span className="lx-menu__t">Đăng xuất</span>
        </button>
      </div>}
    </div>
  </header>;
}
