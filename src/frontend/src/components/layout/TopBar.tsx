'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth/auth-context';
import {
  ROLE_LABELS,
  ROLE_CODES,
  canAccessAnalysis,
  canAccessReview,
  canAccessEscalations,
  canAccessReports,
  canAccessConfiguration,
  canAccessGuidelines,
} from '@/lib/auth/roles';

interface TopBarProps {
  activeKey?: string;
}

export function TopBar({ activeKey }: TopBarProps) {
  const { user, logout, hasPermission } = useAuth();
  const pathname = usePathname();
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const role = user?.role;
  const roleName = role ? ROLE_LABELS[role] : 'Chưa có quyền trong phạm vi này';
  const roleCode = role ? ROLE_CODES[role] : '--';
  const initials = user
    ? user.fullName
        .split(' ')
        .map((n) => n[0])
        .join('')
        .slice(0, 2)
        .toUpperCase()
    : 'LX';

  const closeAll = () => {
    setOpenMenu(null);
    setUserMenuOpen(false);
  };

  const toggleMenu = (key: string) => {
    setUserMenuOpen(false);
    setOpenMenu(openMenu === key ? null : key);
  };

  const toggleUserMenu = () => {
    setOpenMenu(null);
    setUserMenuOpen(!userMenuOpen);
  };

  // Lọc menu theo quyền vai trò (Role-based access control)
  const showAnalysis = hasPermission(canAccessAnalysis);
  const showReview = hasPermission(canAccessReview, true);
  const showEscalations = hasPermission(canAccessEscalations, true);
  const showReports = hasPermission(canAccessReports);
  const showConfig = hasPermission(canAccessConfiguration);
  const showGuidelines = hasPermission(canAccessGuidelines);

  return (
    <>
      <header className="lx-topnav">
        <Link className="lx-logo" href="/" onClick={closeAll}>
          Label<b>X</b>
        </Link>

        <nav className="lx-nav" aria-label="Quality Control Navigation">
          {/* 1. Tổng quan (Overview) - Dành cho mọi vai trò */}
          <div className="lx-nav__group" style={{ position: 'relative' }}>
            <button
              type="button"
              className={`lx-navbtn ${pathname === '/' || activeKey === 'overview' ? 'is-active' : ''}`}
              aria-haspopup="menu"
              aria-expanded={openMenu === 'overview'}
              onClick={() => toggleMenu('overview')}
            >
              Tổng quan
              <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={{ width: 10, height: 10, marginLeft: 4 }}>
                <path d="M3 4.5 6 7.5 9 4.5" />
              </svg>
            </button>
            {openMenu === 'overview' && (
              <div className="lx-menu" role="menu">
                <div className="lx-menu__head">Tổng quan & Báo cáo chất lượng</div>
                <Link
                  className="lx-menu__item"
                  role="menuitem"
                  href="/"
                  onClick={closeAll}
                >
                  <span className="lx-menu__t">Trang chủ QC</span>
                  <span className="lx-menu__d">Chọn Dataset và Version để làm việc</span>
                </Link>
                <Link
                  className="lx-menu__item"
                  role="menuitem"
                  href="/"
                  onClick={closeAll}
                >
                  <span className="lx-menu__t">Tóm tắt chất lượng</span>
                  <span className="lx-menu__d">Tình trạng chất lượng, coverage, khối lượng review</span>
                </Link>
              </div>
            )}
          </div>

          {/* 2. Phân tích chất lượng (Quality Analysis) - Ẩn với Annotator, Reviewer */}
          {showAnalysis && (
            <div className="lx-nav__group">
              <Link
                className={`lx-navbtn ${pathname === '/analysis' || activeKey === 'analysis' ? 'is-active' : ''}`}
                href="/analysis"
                onClick={closeAll}
              >
                Phân tích chất lượng
              </Link>
            </div>
          )}

          {/* 3. Trung tâm kiểm tra (Review Center) - Ẩn với Annotator */}
          {showReview && (
            <div className="lx-nav__group">
              <Link
                className={`lx-navbtn ${pathname === '/review' || activeKey === 'review' ? 'is-active' : ''}`}
                href="/review"
                onClick={closeAll}
              >
                Trung tâm kiểm tra
              </Link>
            </div>
          )}

          {/* Guideline (UC-05) - Reviewer, QA Lead, QC Admin, Super Admin */}
          {showGuidelines && (
            <div className="lx-nav__group">
              <Link
                className={`lx-navbtn ${pathname.startsWith('/configuration/guidelines') || activeKey === 'guidelines' ? 'is-active' : ''}`}
                href="/configuration/guidelines"
                onClick={closeAll}
              >
                Guideline
              </Link>
            </div>
          )}

          {/* 4. Phân xử (Escalations) - Chỉ QA Lead, Super Admin */}
          {showEscalations && (
            <div className="lx-nav__group">
              <button type="button" disabled title="Chưa khả dụng"
                className={`lx-navbtn ${pathname === '/escalations' || activeKey === 'escalations' ? 'is-active' : ''}`}
              >
                Phân xử
              </button>
            </div>
          )}

          {/* 5. Hiệu chuẩn & Kiểm toán (Calibration & Audit) */}
          <div className="lx-nav__group" style={{ position: 'relative' }}>
            <button
              type="button"
              className={`lx-navbtn ${activeKey === 'calibration' ? 'is-active' : ''}`}
              aria-haspopup="menu"
              aria-expanded={openMenu === 'calibration'}
              onClick={() => toggleMenu('calibration')}
            >
              Hiệu chuẩn & Kiểm toán
              <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={{ width: 10, height: 10, marginLeft: 4 }}>
                <path d="M3 4.5 6 7.5 9 4.5" />
              </svg>
            </button>
            {openMenu === 'calibration' && (
              <div className="lx-menu" role="menu">
                <div className="lx-menu__head">Hiệu chuẩn & Kiểm toán</div>
                <Link className="lx-menu__item" role="menuitem" href="#" onClick={closeAll}>
                  <span className="lx-menu__t">Đánh giá quy trình</span>
                  <span className="lx-menu__d">Đánh giá chất lượng của chính quy trình kiểm tra</span>
                </Link>
                <Link className="lx-menu__item" role="menuitem" href="#" onClick={closeAll}>
                  <span className="lx-menu__t">Tập chuẩn chuyên gia</span>
                  <span className="lx-menu__d">Tập chuẩn đã được chuyên gia khoá</span>
                </Link>
                <Link className="lx-menu__item" role="menuitem" href="#" onClick={closeAll}>
                  <span className="lx-menu__t">Lấy mẫu kiểm toán</span>
                  <span className="lx-menu__d">Lấy mẫu ngẫu nhiên và lấy mẫu theo rủi ro</span>
                </Link>
                <Link className="lx-menu__item" role="menuitem" href="#" onClick={closeAll}>
                  <span className="lx-menu__t">Hiệu chuẩn</span>
                  <span className="lx-menu__d">Hiệu chỉnh reviewer và mô hình</span>
                </Link>
              </div>
            )}
          </div>

          {/* 6. Báo cáo & Phát hành - Các vai trò có quyền đọc báo cáo theo canAccessReports */}
          {showReports && (
            <div className="lx-nav__group">
              <button type="button" disabled title="Chưa khả dụng"
                className={`lx-navbtn ${pathname === '/reports' || activeKey === 'reports' ? 'is-active' : ''}`}
              >
                Báo cáo & Phát hành
              </button>
            </div>
          )}

          {/* 7. Cấu hình (Configuration) - QC Admin, Super Admin, QA Lead */}
          {showConfig && (
            <div className="lx-nav__group" style={{ position: 'relative' }}>
              <button
                type="button"
                className={`lx-navbtn ${(pathname.startsWith('/configuration') && !pathname.startsWith('/configuration/guidelines')) || activeKey === 'configuration' ? 'is-active' : ''}`}
                aria-haspopup="menu"
                aria-expanded={openMenu === 'configuration'}
                onClick={() => toggleMenu('configuration')}
              >
                Cấu hình
                <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={{ width: 10, height: 10, marginLeft: 4 }}>
                  <path d="M3 4.5 6 7.5 9 4.5" />
                </svg>
              </button>
              {openMenu === 'configuration' && (
                <div className="lx-menu" role="menu">
                  <div className="lx-menu__head">Cấu hình & Phân quyền</div>
                  <Link className="lx-menu__item" role="menuitem" href="/configuration" onClick={closeAll}>
                    <span className="lx-menu__t">Quy trình & Phân quyền</span>
                    <span className="lx-menu__d">Phân quyền theo vai trò và quy tắc kiểm soát</span>
                  </Link>
                  <span className="lx-menu__item" role="menuitem" aria-disabled="true" title="Chưa khả dụng">
                    <span className="lx-menu__t">Quy tắc & Ngưỡng</span>
                    <span className="lx-menu__d">Quy tắc kiểm tra và chính sách lấy mẫu (chưa khả dụng)</span>
                  </span>
                </div>
              )}
            </div>
          )}
        </nav>

        {/* User profile & actions */}
        <div className="lx-userwrap" style={{ position: 'relative' }}>
          <button
            type="button"
            className="lx-user lx-user--btn"
            aria-haspopup="menu"
            aria-expanded={userMenuOpen}
            onClick={toggleUserMenu}
            style={{ background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'inherit' }}
          >
            <span className="lx-user__meta">
              <span className="lx-user__name">{user?.fullName || 'Khách'}</span>
              <span className="lx-user__role">{roleName} ({roleCode})</span>
            </span>
            <span className="lx-avatar" role="img" aria-label={user?.fullName || 'User'}>
              {initials}
            </span>
            <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={{ width: 12, height: 12 }}>
              <path d="M3 4.5 6 7.5 9 4.5" />
            </svg>
          </button>

          {userMenuOpen && (
            <div className="lx-menu lx-menu--user" role="menu" style={{ right: 0, left: 'auto', minWidth: '220px' }}>
              <div className="lx-menu__head">Tài khoản</div>

              <div style={{ borderTop: '1px solid var(--border)', margin: '4px 0' }} />

              <button
                type="button"
                className="lx-menu__item"
                style={{ width: '100%', border: 'none', background: 'transparent', cursor: 'pointer', textAlign: 'left', color: 'var(--danger)' }}
                onClick={() => {
                  void logout();
                  closeAll();
                }}
              >
                <span className="lx-menu__t">Đăng xuất</span>
              </button>
            </div>
          )}
        </div>
      </header>

      {(openMenu || userMenuOpen) && (
        <div className="lx-backdrop" onClick={closeAll} />
      )}
    </>
  );
}
