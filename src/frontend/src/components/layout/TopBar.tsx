'use client';

import React, { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth/auth-context';
import { ROLE_LABELS, canAccessAnalysis, canAccessReview, canAccessEscalations, canAccessCalibration,
  canAccessReports, canAccessConfiguration, canAccessGuidelines } from '@/lib/auth/roles';
import { Icon } from '@/components/ui/Icon';

interface MenuItem { label: string; icon: string; href?: string; desc?: string; }
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
    { label: 'Rules & Thresholds', icon: 'rules', href: '/configuration/rules-thresholds', desc: 'Quy tắc kiểm tra và chính sách lấy mẫu' },
    { label: 'Models & Guidelines', icon: 'model', href: '/configuration/guidelines', desc: 'Cấu hình mô hình và ánh xạ phiên bản guideline' });
  if (hasPermission(canAccessConfiguration)) configItems.push(
    { label: 'Workflow & Permissions', icon: 'users', href: '/configuration', desc: 'Quy trình làm việc và phân quyền theo vai trò' });
  const modules: Module[] = [
    { key: 'overview', label: 'Overview', items: [{ label: 'Quality Control Home', icon: 'home', href: '/', desc: 'Chọn Dataset và Version để làm việc' },
      { label: 'Quality Summary', icon: 'chart', desc: 'Tình trạng chất lượng, coverage, khối lượng review' }] },
    ...(hasPermission(canAccessAnalysis) ? [{ key: 'analysis', label: 'Quality Analysis', href: '/analysis' }] : []),
    ...(hasPermission(canAccessReview, true) ? [{ key: 'review', label: 'Review Center', href: '/review' }] : []),
    ...(hasPermission(canAccessEscalations, true) ? [{ key: 'escalations', label: 'Escalations', href: '/escalations' }] : []),
    ...(hasPermission(canAccessCalibration) ? [{ key: 'calibration', label: 'Calibration & Audit', items: [
      { label: 'Performance Evaluation', icon: 'chart', href: '/calibration/performance', desc: 'Đánh giá chất lượng của chính quy trình kiểm tra' },
      { label: 'Ground Truth Benchmark', icon: 'target', href: '/calibration/benchmark', desc: 'Tập chuẩn đã được chuyên gia khoá' },
      { label: 'Audit Sampling', icon: 'check', href: '/calibration/audit-sampling', desc: 'Lấy mẫu ngẫu nhiên và lấy mẫu theo rủi ro' },
      { label: 'Calibration', icon: 'scale', href: '/calibration/calibration', desc: 'Hiệu chỉnh reviewer và mô hình' }] }] : []),
    ...(hasPermission(canAccessReports) ? [{ key: 'reports', label: 'Reports & Releases', href: '/reports' }] : []),
    ...(configItems.length ? [{ key: 'configuration', label: 'Configuration', items: configItems }] : []),
  ];
  const active = pathname.startsWith('/configuration') ? 'configuration' : pathname.startsWith('/escalations') ? 'escalations' : pathname.startsWith('/review') ? 'review'
    : pathname.startsWith('/analysis') ? 'analysis' : pathname.startsWith('/calibration') ? 'calibration'
    : pathname.startsWith('/reports') ? 'reports' : activeKey || 'overview';
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
            {module.items.map(item => item.href ? <Link key={item.label} href={item.href} role="menuitem" aria-label={item.label}
              className={`lx-menu__item${pathname === item.href ? ' is-active' : ''}`} aria-current={pathname === item.href ? 'page' : undefined}
              onClick={closeAll}><span className="lx-menu__t">{item.label}</span><Icon name={item.icon} />
                {item.desc && <span className="lx-menu__d">{item.desc}</span>}</Link>
              : <button key={item.label} className="lx-menu__item" type="button" role="menuitem" aria-label={item.label} disabled title="Chưa khả dụng">
                <span className="lx-menu__t">{item.label}</span><Icon name={item.icon} />
                {item.desc && <span className="lx-menu__d">{item.desc}</span>}</button>)}
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
        <button className="lx-menu__item" type="button" role="menuitem" disabled title="Chưa khả dụng">
          <Icon name="user" /><span className="lx-menu__t">Hồ sơ</span>
        </button>
        <button className="lx-menu__item" type="button" role="menuitem" disabled title="Chưa khả dụng">
          <Icon name="settings" /><span className="lx-menu__t">Cài đặt</span>
        </button>
        <button className="lx-menu__item" type="button" role="menuitem" onClick={() => { void logout(); closeAll(); }}>
          <Icon name="logout" /><span className="lx-menu__t">Đăng xuất</span>
        </button>
      </div>}
    </div>
  </header>;
}
