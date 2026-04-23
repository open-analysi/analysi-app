import React, { useCallback, useEffect, useRef, useState } from 'react';

import { ChevronRightIcon } from '@heroicons/react/24/outline';
import { createPortal } from 'react-dom';
import { Link, useLocation } from 'react-router';

import { checkIsSubmenuActive } from './sidebarConfig';
import { navItemClasses } from './types';
import type { NavItem, SubmenuConfig } from './types';

interface SidebarSubmenuItemProps {
  item: NavItem;
  submenu: SubmenuConfig;
  isActive: boolean;
  collapsed: boolean;
  onMouseEnter?: (name: string, element: HTMLElement) => void;
  onMouseLeave?: () => void;
}

export const SidebarSubmenuItem: React.FC<SidebarSubmenuItemProps> = ({
  item,
  submenu,
  isActive,
  collapsed,
  onMouseEnter,
  onMouseLeave,
}) => {
  const location = useLocation();
  const locationKey = `${location.pathname}${location.search}`;

  // Track which location key the popover was opened for.
  // When the route changes, `open` derives to false automatically — no effect needed.
  const [openForLocation, setOpenForLocation] = useState<string | null>(null);
  const open = openForLocation === locationKey;

  const [popoverPos, setPopoverPos] = useState({ left: 0, top: 0 });
  const triggerRef = useRef<HTMLAnchorElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const handleToggle = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      if (triggerRef.current) {
        const rect = triggerRef.current.getBoundingClientRect();
        setPopoverPos({ left: rect.right + 8, top: rect.top });
      }
      setOpenForLocation((prev) => (prev === locationKey ? null : locationKey));
    },
    [locationKey]
  );

  const closePopover = useCallback(() => setOpenForLocation(null), []);

  // Close popover on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        triggerRef.current &&
        !triggerRef.current.contains(e.target as Node)
      ) {
        closePopover();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [closePopover]);

  // Close popover on Escape key and return focus to trigger
  useEffect(() => {
    if (!open) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === 'Esc') {
        e.preventDefault();
        e.stopPropagation();
        closePopover();
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('keydown', handleEscape, true);
    return () => document.removeEventListener('keydown', handleEscape, true);
  }, [open, closePopover]);

  return (
    <React.Fragment>
      <Link
        ref={triggerRef}
        to={item.href}
        onClick={handleToggle}
        onMouseEnter={(e) => !open && onMouseEnter?.(item.name, e.currentTarget)}
        onMouseLeave={onMouseLeave}
        className={navItemClasses(collapsed, isActive)}
        aria-current={isActive ? 'page' : undefined}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <item.icon className="w-5 h-5 shrink-0 transition-transform duration-150 group-hover/navitem:scale-110" />
        {!collapsed && (
          <>
            <span className="ml-3 text-sm whitespace-nowrap overflow-hidden flex-1 transition-transform duration-150 group-hover/navitem:translate-x-0.5">
              {item.name}
            </span>
            <ChevronRightIcon
              className={`w-3.5 h-3.5 shrink-0 ml-3 text-gray-500 transition-all duration-150 group-hover/navitem:text-gray-300 ${
                open ? 'rotate-90' : ''
              }`}
            />
          </>
        )}
      </Link>

      {open &&
        createPortal(
          <>
            {/* Purely visual backdrop — pointer-events-none so clicks pass through to page elements */}
            <div
              className="fixed inset-0 bg-black/40 pointer-events-none"
              style={{ zIndex: 9998 }}
              aria-hidden="true"
            />
            <div
              ref={popoverRef}
              role="menu"
              className="fixed bg-dark-900 rounded-lg shadow-lg border border-dark-700 py-2 w-44"
              style={{ left: popoverPos.left, top: popoverPos.top, zIndex: 9999 }}
            >
              <div className="px-3 py-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wider">
                {submenu.label}
              </div>
              {submenu.items.map((sub) => {
                const isSubActive = checkIsSubmenuActive(
                  sub.href,
                  location.pathname,
                  location.search
                );
                return (
                  <Link
                    key={sub.name}
                    to={sub.href}
                    role="menuitem"
                    onClick={closePopover}
                    className={`group/sub flex items-center gap-2 mx-2 px-2 py-2 rounded-md text-sm transition-colors ${
                      isSubActive
                        ? 'text-white bg-primary'
                        : 'text-gray-300 hover:bg-dark-600 hover:text-white'
                    }`}
                  >
                    <sub.icon className="w-4 h-4 transition-transform duration-150 group-hover/sub:scale-110" />
                    {sub.name}
                  </Link>
                );
              })}
            </div>
          </>,
          document.body
        )}
    </React.Fragment>
  );
};
