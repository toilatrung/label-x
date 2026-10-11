'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth/auth-context';
import { ROLE_LABELS, canAccessAnalysis, canAccessReview, canAccessEscalations,
  canAccessReports, canAccessConfiguration, canAccessGuidelines } from '@/lib/auth/roles';
import { Icon } from '@/components/ui/Icon';

import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';

interface MenuItem { label: string; icon?: string; iconPath?: string; desc?: string; href?: string; key?: string; }
interface Module { key: string; label: string; href?: string; items?: MenuItem[]; }

interface TopBarProps {
  activeKey?: string;
  activeItem?: string;
  openMenuId?: string | null;
  onOpenMenuChange?: (id: string | null) => void;
  variant?: 'canonical' | 'default';
}

export function TopBar({
  activeKey,
  activeItem,
  openMenuId,
  onOpenMenuChange,
  variant = 'default',
}: TopBarProps) {
  const { user, logout, hasPermission } = useAuth();
  const pathname = usePathname();
  const isControlled = openMenuId !== undefined;
  const [internalOpenMenu, setInternalOpenMenu] = useState<string | null>(null);
  const currentOpenMenu = isControlled ? openMenuId : internalOpenMenu;
  const [userNotice, setUserNotice] = useState<string | null>(null);

  const setMenu = useCallback(
    (menu: string | null) => {
      if (onOpenMenuChange) onOpenMenuChange(menu);
      if (!isControlled) setInternalOpenMenu(menu);
    },
    [isControlled, onOpenMenuChange]
  );
  const closeAll = useCallback(() => setMenu(null), [setMenu]);

  const root = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const roleName = user?.role ? ROLE_LABELS[user.role] : 'Chưa có quyền trong phạm vi này';
  const initials = user?.fullName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || 'LX';

  useEffect(() => {
    const isTopMenuOpen = isControlled ? currentOpenMenu?.startsWith('top:') : !!internalOpenMenu;
    if (!isTopMenuOpen) return;

    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) closeAll();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeAll();
        trigger.current?.focus();
      }
    };
    document.addEventListener('pointerdown', outside);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', outside);
      document.removeEventListener('keydown', escape);
    };
  }, [isControlled, currentOpenMenu, internalOpenMenu, closeAll]);

  const configItems: MenuItem[] = [];
  if (hasPermission(canAccessGuidelines))
    configItems.push(
      {
        key: 'rules',
        label: 'Rules & Thresholds',
        desc: 'Quy tắc kiểm tra và chính sách lấy mẫu',
        icon: 'rules',
        iconPath: 'M3 4h10M3 8h10M3 12h6',
        href: '/configuration/rules-thresholds',
      },
      {
        key: 'models',
        label: 'Models & Guidelines',
        desc: 'Cấu hình mô hình và ánh xạ phiên bản guideline',
        icon: 'model',
        iconPath: 'M8 2l5 2.5v5L8 12 3 9.5v-5zM3 4.5 8 7l5-2.5M8 7v5',
        href: '/configuration/guidelines',
      }
    );
  if (hasPermission(canAccessConfiguration))
    configItems.push({
      key: 'permissions',
      label: 'Workflow & Permissions',
      desc: 'Quy trình làm việc và phân quyền theo vai trò',
      icon: 'users',
      iconPath: 'M8 8a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM3 13.5c.5-2.5 2.5-3.5 5-3.5s4.5 1 5 3.5',
      href: '/configuration',
    });

  const modules: Module[] = [
    {
      key: 'overview',
      label: 'Overview',
      items: [
        {
          key: 'home',
          label: 'Quality Control Home',
          desc: 'Chọn Dataset và Version để làm việc',
          icon: 'home',
          iconPath: 'M2.5 7.5 8 3l5.5 4.5V13a.5.5 0 0 1-.5.5H3a.5.5 0 0 1-.5-.5zM6.5 13.5v-4h3v4',
          href: '/',
        },
        {
          key: 'summary',
          label: 'Quality Summary',
          desc: 'Tình trạng chất lượng, coverage, khối lượng review',
          icon: 'chart',
          iconPath: 'M3 13V8M8 13V3M13 13V6',
          href: '/?view=summary',
        },
      ],
    },
    ...(hasPermission(canAccessAnalysis)
      ? [{ key: 'analysis', label: 'Quality Analysis', href: '/analysis' }]
      : []),
    ...(hasPermission(canAccessReview, true)
      ? [{ key: 'review', label: 'Review Center', href: '/review' }]
      : []),
    ...(hasPermission(canAccessEscalations, true)
      ? [{ key: 'escalations', label: 'Escalations', href: '/escalations' }]
      : []),
    {
      key: 'calibration',
      label: 'Calibration & Audit',
      items: [
        {
          key: 'performance',
          label: 'Performance Evaluation',
          desc: 'Đánh giá chất lượng của chính quy trình kiểm tra',
          icon: 'chart',
          iconPath: 'M2 12l4-4 3 3 5-6',
        },
        {
          key: 'benchmark',
          label: 'Ground Truth Benchmark',
          desc: 'Tập chuẩn đã được chuyên gia khoá',
          icon: 'target',
          iconPath: 'M4 14V2.5M4 3h8l-1.5 3L12 9H4',
        },
        {
          key: 'audit',
          label: 'Audit Sampling',
          desc: 'Lấy mẫu ngẫu nhiên và lấy mẫu theo rủi ro',
          icon: 'check',
          iconPath: 'M5.5 2.5h5v2h-5zM4 4H3.5v9.5h9V4H12M6 9l1.5 1.5L10.5 7.5',
        },
        {
          key: 'calibrate',
          label: 'Calibration',
          desc: 'Hiệu chỉnh reviewer và mô hình',
          icon: 'scale',
          iconPath: 'M3 5h6M11 5h2M3 11h2M7 11h6M9 3.5v3M5 9.5v3',
        },
      ],
    },
    ...(hasPermission(canAccessReports)
      ? [{ key: 'reports', label: 'Reports & Releases' }]
      : []),
    ...(configItems.length
      ? [{ key: 'configuration', label: 'Configuration', items: configItems }]
      : []),
  ];
  const active = pathname.startsWith('/configuration') ? 'configuration' : pathname.startsWith('/escalations') ? 'escalations' : pathname.startsWith('/review') ? 'review'
    : pathname.startsWith('/analysis') ? 'analysis' : activeKey || 'overview';

  function toggle(key: string, event: React.MouseEvent<HTMLButtonElement>) {
    trigger.current = event.currentTarget;
    setMenu(currentOpenMenu === `top:${key}` ? null : `top:${key}`);
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
    event.preventDefault(); trigger.current = event.currentTarget; setMenu(`top:${key}`);
    requestAnimationFrame(() => root.current?.querySelector<HTMLElement>(`#nav-menu-${key} [role="menuitem"]:not(:disabled)`)?.focus());
  }

  return <header className="lx-topnav" ref={root}>
    <Link className="lx-logo" href="/" aria-label="Về Quality Control Home" onClick={closeAll}>Label<b>X</b></Link>
    <nav className="lx-nav" aria-label="Quality Control Navigation">
      {modules.map(module => <div className="lx-nav__group" key={module.key}>
        {module.items ? <>
          <button className={`lx-navbtn${active === module.key ? ' is-active' : ''}`} type="button"
            aria-haspopup="menu" aria-expanded={currentOpenMenu === `top:${module.key}`} aria-controls={`nav-menu-${module.key}`}
            onClick={event => toggle(module.key, event)} onKeyDown={event => triggerKey(event, module.key)}>
            {module.label}<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M3 4.5 6 7.5 9 4.5" /></svg>
          </button>
          {currentOpenMenu === `top:${module.key}` && <div className="lx-menu" role="menu" id={`nav-menu-${module.key}`} onKeyDown={menuKey}>
            {module.items.map(item => {
              const isItemActive = (() => {
                if (active !== module.key) return false;
                if (module.key === 'overview') {
                  if (activeItem) return item.key === activeItem;
                  if (typeof window !== 'undefined') {
                    const searchParams = new URLSearchParams(window.location.search);
                    return searchParams.get('view') === 'summary' ? item.key === 'summary' : item.key === 'home';
                  }
                  return item.key === 'home';
                }
                return pathname === item.href;
              })();

              const itemInner = (
                <>
                  <span className="lx-menu__t">{item.label}</span>
                  {isItemActive && (
                    <svg className="lx-menu__check" viewBox="0 0 16 16" role="img" aria-label="Đang xem" style={{ width: 14, height: 14, stroke: 'currentColor', fill: 'none', strokeWidth: 2 }}>
                      <path d="M3 8.5 6.5 12 13 4.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                  {item.iconPath ? (
                    <svg className="lx-menu__ico" viewBox="0 0 16 16" aria-hidden="true">
                      <path d={item.iconPath} />
                    </svg>
                  ) : item.icon ? (
                    <Icon name={item.icon} />
                  ) : null}
                  {item.desc && <span className="lx-menu__d">{item.desc}</span>}
                </>
              );

              return item.href ? (
                <Link
                  key={item.label}
                  href={item.href}
                  role="menuitem"
                  aria-label={item.label}
                  className={`lx-menu__item${isItemActive ? ' is-active' : ''}`}
                  aria-current={isItemActive ? 'page' : undefined}
                  onClick={closeAll}
                >
                  {itemInner}
                </Link>
              ) : variant === 'canonical' ? (
                <button
                  key={item.label}
                  className="lx-menu__item"
                  type="button"
                  role="menuitem"
                  aria-label={item.label}
                  onClick={() => {
                    setUserNotice(item.label);
                    closeAll();
                  }}
                >
                  {itemInner}
                </button>
              ) : (
                <button
                  key={item.label}
                  className="lx-menu__item"
                  type="button"
                  role="menuitem"
                  aria-label={item.label}
                  disabled
                  title="Chưa khả dụng"
                >
                  {itemInner}
                </button>
              );
            })}
          </div>}
        </> : module.href ? <Link href={module.href} onClick={closeAll}
          className={`lx-navbtn${active === module.key ? ' is-active' : ''}`} aria-current={active === module.key ? 'page' : undefined}>{module.label}</Link>
          : variant === 'canonical' ? (
            <button className="lx-navbtn" type="button"
              onClick={() => { setUserNotice(`Module ${module.label}`); closeAll(); }}>
              {module.label}
            </button>
          ) : (
            <button className="lx-navbtn" type="button" disabled title="Chưa khả dụng">{module.label}</button>
          )}
      </div>)}
    </nav>
    <div className="lx-userwrap">
      {variant === 'canonical' ? (
        <button className="lx-user lx-user--btn" type="button" aria-haspopup="menu" aria-expanded={currentOpenMenu === 'top:user'}
          aria-controls="nav-menu-user" onClick={event => toggle('user', event)} onKeyDown={event => triggerKey(event, 'user')}>
          <span className="lx-avatar" aria-hidden="true">{initials}</span>
          <span className="lx-user__role">{roleName}</span>
          <svg className="lx-user__chev" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M3 4.5 6 7.5 9 4.5" />
          </svg>
        </button>
      ) : (
        <button className="lx-user lx-user--btn" type="button" aria-haspopup="menu" aria-expanded={currentOpenMenu === 'top:user'}
          aria-controls="nav-menu-user" onClick={event => toggle('user', event)} onKeyDown={event => triggerKey(event, 'user')}>
          <span className="lx-avatar" aria-hidden="true">{initials}</span>
          <span className="lx-user__meta"><span className="lx-user__name">{user?.fullName || 'Khách'}</span><span className="lx-user__role">{roleName}</span></span>
          <svg className="lx-user__chev" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M3 4.5 6 7.5 9 4.5" />
          </svg>
        </button>
      )}
      {currentOpenMenu === 'top:user' && <div className="lx-menu lx-menu--user" id="nav-menu-user" role="menu" onKeyDown={menuKey}>
        {variant === 'canonical' && <>
          <button className="lx-menu__item" type="button" role="menuitem" onClick={() => { setUserNotice('Hồ sơ'); closeAll(); }}>
            <svg className="lx-menu__ico lx-menu__ico--l" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M8 8a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM3 13.5c.5-2.5 2.5-3.5 5-3.5s4.5 1 5 3.5" />
            </svg>
            <span className="lx-menu__t">Hồ sơ</span>
          </button>
          <button className="lx-menu__item" type="button" role="menuitem" onClick={() => { setUserNotice('Cài đặt'); closeAll(); }}>
            <svg className="lx-menu__ico lx-menu__ico--l" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M8 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM8 2v1.5M8 12.5V14M2 8h1.5M12.5 8H14M3.8 3.8l1 1M11.2 11.2l1 1M12.2 3.8l-1 1M4.8 11.2l-1 1" />
            </svg>
            <span className="lx-menu__t">Cài đặt</span>
          </button>
        </>}
        <button className="lx-menu__item" type="button" role="menuitem" onClick={() => { void logout(); closeAll(); }}>
          <svg className="lx-menu__ico lx-menu__ico--l" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M6 3H3.5v10H6M10 5.5 12.5 8 10 10.5M12.5 8H6.5" />
          </svg>
          <span className="lx-menu__t">Đăng xuất</span>
        </button>
      </div>}
    </div>
    {userNotice && (
      <div style={{ position: 'fixed', top: 56, right: 16, zIndex: 100 }} role="status">
        <NotConnectedNotice detail={userNotice} />
      </div>
    )}
  </header>;
}
