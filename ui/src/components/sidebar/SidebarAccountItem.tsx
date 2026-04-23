import React, { useCallback, useEffect, useRef, useState } from 'react';

import { useOidc } from '@axa-fr/react-oidc';
import {
  ArrowRightStartOnRectangleIcon,
  ChevronRightIcon,
  UserCircleIcon,
} from '@heroicons/react/24/outline';
import { createPortal } from 'react-dom';
import { Link } from 'react-router';

import { useAuthStore } from '@/store/authStore';

import { navItemClasses } from './types';
import type { NavItem } from './types';

const authDisabled = import.meta.env.VITE_DISABLE_AUTH === 'true';

/**
 * Wrapper around useOidc that returns a no-op when auth is disabled.
 * VITE_DISABLE_AUTH is a build-time constant so the branch never changes
 * at runtime, keeping hook call order stable.
 */
function useOidcSafe() {
  if (authDisabled) {
    return { logout: (() => {}) as (redirectUri?: string) => void };
  }
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useOidc();
}

interface SidebarAccountItemProps {
  item: NavItem;
  isActive: boolean;
  collapsed: boolean;
  onMouseEnter?: (name: string, element: HTMLElement) => void;
  onMouseLeave?: () => void;
}

export const SidebarAccountItem: React.FC<SidebarAccountItemProps> = ({
  item,
  isActive,
  collapsed,
  onMouseEnter,
  onMouseLeave,
}) => {
  const { logout } = useOidcSafe();
  const { email, name } = useAuthStore();

  const [open, setOpen] = useState(false);
  const [popoverPos, setPopoverPos] = useState({ left: 0, bottom: 0 });
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const handleToggle = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      // Open upward: align bottom of popover with bottom of trigger
      setPopoverPos({ left: rect.right + 8, bottom: window.innerHeight - rect.bottom });
    }
    setOpen((prev) => !prev);
  }, []);

  const closePopover = useCallback(() => setOpen(false), []);

  const handleLogout = useCallback(() => {
    closePopover();
    void logout('/');
  }, [logout, closePopover]);

  // Close on click outside
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

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        closePopover();
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('keydown', handleEscape, true);
    return () => document.removeEventListener('keydown', handleEscape, true);
  }, [open, closePopover]);

  const displayName = name || email || 'Account';

  return (
    <>
      <button
        ref={triggerRef}
        onClick={handleToggle}
        onMouseEnter={(e) => !open && onMouseEnter?.(item.name, e.currentTarget)}
        onMouseLeave={onMouseLeave}
        className={navItemClasses(collapsed, isActive)}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <item.icon className="w-5 h-5 shrink-0 transition-transform duration-150 group-hover/navitem:scale-110" />
        {!collapsed && (
          <>
            <span className="ml-3 text-sm whitespace-nowrap overflow-hidden flex-1 text-left transition-transform duration-150 group-hover/navitem:translate-x-0.5">
              {item.name}
            </span>
            <ChevronRightIcon
              className={`w-3.5 h-3.5 shrink-0 ml-3 text-gray-500 transition-all duration-150 group-hover/navitem:text-gray-300 ${
                open ? 'rotate-90' : ''
              }`}
            />
          </>
        )}
      </button>

      {open &&
        createPortal(
          <>
            <div
              className="fixed inset-0 bg-black/40 pointer-events-none"
              style={{ zIndex: 9998 }}
              aria-hidden="true"
            />
            <div
              ref={popoverRef}
              role="menu"
              className="fixed bg-dark-900 rounded-lg shadow-lg border border-dark-700 py-2 w-52"
              style={{ left: popoverPos.left, bottom: popoverPos.bottom, zIndex: 9999 }}
            >
              {/* User info */}
              <div className="px-3 py-2 border-b border-dark-700 mb-1">
                <div className="text-sm font-medium text-white truncate">{displayName}</div>
                {name && email && <div className="text-xs text-gray-400 truncate">{email}</div>}
              </div>

              {/* Profile */}
              <Link
                to="/account-settings"
                role="menuitem"
                onClick={closePopover}
                className="group/sub flex items-center gap-2 mx-2 px-2 py-2 rounded-md text-sm
                  text-gray-300 hover:bg-dark-600 hover:text-white transition-colors"
              >
                <UserCircleIcon className="w-4 h-4 transition-transform duration-150 group-hover/sub:scale-110" />
                Profile
              </Link>

              {/* Logout */}
              <button
                role="menuitem"
                onClick={handleLogout}
                className="group/sub flex items-center gap-2 mx-2 px-2 py-2 rounded-md text-sm w-[calc(100%-1rem)]
                  text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors"
              >
                <ArrowRightStartOnRectangleIcon className="w-4 h-4 transition-transform duration-150 group-hover/sub:scale-110" />
                Log Out
              </button>
            </div>
          </>,
          document.body
        )}
    </>
  );
};
