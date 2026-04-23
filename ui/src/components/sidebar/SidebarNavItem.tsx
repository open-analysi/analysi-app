import React from 'react';

import { Link } from 'react-router';

import { navItemClasses } from './types';
import type { NavItem } from './types';

interface SidebarNavItemProps {
  item: NavItem;
  isActive: boolean;
  collapsed: boolean;
  onMouseEnter?: (name: string, element: HTMLElement) => void;
  onMouseLeave?: () => void;
}

export const SidebarNavItem: React.FC<SidebarNavItemProps> = ({
  item,
  isActive,
  collapsed,
  onMouseEnter,
  onMouseLeave,
}) => {
  return (
    <Link
      to={item.href}
      onMouseEnter={(e) => onMouseEnter?.(item.name, e.currentTarget)}
      onMouseLeave={onMouseLeave}
      className={navItemClasses(collapsed, isActive)}
      aria-current={isActive ? 'page' : undefined}
    >
      <item.icon className="w-5 h-5 shrink-0 transition-transform duration-150 group-hover/navitem:scale-110" />
      {!collapsed && (
        <span className="ml-3 text-sm whitespace-nowrap overflow-hidden transition-transform duration-150 group-hover/navitem:translate-x-0.5">
          {item.name}
        </span>
      )}
    </Link>
  );
};
