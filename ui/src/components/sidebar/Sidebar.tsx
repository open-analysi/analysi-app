import React, { useCallback, useState } from 'react';

import { ChevronDoubleLeftIcon, ChevronDoubleRightIcon } from '@heroicons/react/24/outline';
import { createPortal } from 'react-dom';
import { useLocation } from 'react-router';

import logo from '@/assets/images/logo.jpeg';
import { useSidebarCollapse } from '@/hooks/useSidebarCollapse';

import { SidebarAccountItem } from './SidebarAccountItem';
import { checkIsActive, getAdminItems, getNavSections, submenuConfigs } from './sidebarConfig';
import { SidebarNavItem } from './SidebarNavItem';
import { SidebarSubmenuItem } from './SidebarSubmenuItem';
import type { NavItem, TooltipState } from './types';

export const SIDEBAR_WIDTH_COLLAPSED = 64;

// Computed once at module load — safe because env vars (VITE_*) are static build-time values.
// If nav items ever become user-role-dependent, move these inside the component with useMemo.
const navSections = getNavSections();
const adminItems = getAdminItems();

export const Sidebar: React.FC = () => {
  const location = useLocation();
  const { collapsed, toggle } = useSidebarCollapse();
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const showTooltip = useCallback(
    (name: string, element: HTMLElement) => {
      if (!collapsed) return;
      const rect = element.getBoundingClientRect();
      setTooltip({ name, top: rect.top + rect.height / 2, left: rect.right + 8 });
    },
    [collapsed]
  );

  const hideTooltip = useCallback(() => setTooltip(null), []);

  const renderNavItem = useCallback(
    (item: NavItem) => {
      const submenu = submenuConfigs[item.name];

      if (submenu) {
        const isSubmenuParentActive = submenu.isParentActive
          ? submenu.isParentActive(location.pathname)
          : checkIsActive(item.href, location.pathname);

        return (
          <SidebarSubmenuItem
            key={item.name}
            item={item}
            submenu={submenu}
            isActive={isSubmenuParentActive}
            collapsed={collapsed}
            onMouseEnter={showTooltip}
            onMouseLeave={hideTooltip}
          />
        );
      }

      const isActive = checkIsActive(item.href, location.pathname);
      return (
        <SidebarNavItem
          key={item.name}
          item={item}
          isActive={isActive}
          collapsed={collapsed}
          onMouseEnter={showTooltip}
          onMouseLeave={hideTooltip}
        />
      );
    },
    [collapsed, location.pathname, showTooltip, hideTooltip]
  );

  return (
    <>
      <aside
        className="bg-dark-800 h-screen sticky top-0 flex flex-col overflow-hidden
        transition-[width] duration-200 ease-in-out shrink-0"
        style={{
          width: collapsed ? SIDEBAR_WIDTH_COLLAPSED : 'fit-content',
          // Enables smooth transition to/from keyword sizes like fit-content (Chrome 129+).
          // Falls back to an instant switch in older browsers — sidebar still works correctly.
          ...({ interpolateSize: 'allow-keywords' } as React.CSSProperties),
        }}
        aria-label="Main navigation"
      >
        {/* Header: Logo & Collapse Toggle */}
        <div
          className={`flex items-center shrink-0 ${
            collapsed ? 'flex-col gap-2 py-4 px-2' : 'justify-between px-4 py-4'
          }`}
        >
          <img
            src={logo}
            alt="Analysi"
            className="w-10 h-10 rounded-lg object-contain ring-2 ring-primary
            hover:scale-110 transition-transform duration-300 shrink-0"
          />
          <button
            onClick={toggle}
            className="p-2 rounded-md text-gray-500 hover:text-white hover:bg-dark-700
            transition-colors"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? (
              <ChevronDoubleRightIcon className="w-5 h-5" />
            ) : (
              <ChevronDoubleLeftIcon className="w-5 h-5" />
            )}
          </button>
        </div>

        {/* Navigation Sections */}
        <nav
          className="flex-1 flex flex-col px-2 py-2 overflow-y-auto overflow-x-hidden"
          aria-label="Primary"
        >
          <div className="flex flex-col gap-5">
            {navSections.map((section, index) => (
              <div key={section.id}>
                {/* Section header (expanded) or separator (collapsed) */}
                {!collapsed && (
                  <div className="px-3 mb-1.5 text-2xs font-semibold text-gray-500 uppercase tracking-widest">
                    {section.label}
                  </div>
                )}
                {collapsed && index > 0 && <div className="border-t border-dark-600 mx-2 mb-2" />}
                <div className="flex flex-col gap-0.5">{section.items.map(renderNavItem)}</div>
              </div>
            ))}
          </div>

          {/* Admin section pinned to bottom */}
          <div className="mt-auto pt-3">
            <div className="border-t border-dark-600 mx-1 mb-2" />
            <div className="flex flex-col gap-0.5">
              {adminItems.map((item) => {
                if (item.name === 'Account') {
                  return (
                    <SidebarAccountItem
                      key={item.name}
                      item={item}
                      isActive={checkIsActive(item.href, location.pathname)}
                      collapsed={collapsed}
                      onMouseEnter={showTooltip}
                      onMouseLeave={hideTooltip}
                    />
                  );
                }
                return renderNavItem(item);
              })}
            </div>
          </div>
        </nav>
      </aside>
      {/* Tooltip portaled to body so it's never clipped by the aside's overflow-hidden */}
      {tooltip &&
        createPortal(
          <div
            className="fixed z-50 px-2.5 py-1.5 bg-dark-700 text-white text-xs rounded-md
            shadow-lg border border-dark-600 whitespace-nowrap pointer-events-none
            -translate-y-1/2"
            style={{ left: tooltip.left, top: tooltip.top }}
          >
            {tooltip.name}
          </div>,
          document.body
        )}
    </>
  );
};
