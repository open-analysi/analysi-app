import type { ComponentType, SVGProps } from 'react';

export type HeroIcon = ComponentType<SVGProps<SVGSVGElement> & { className?: string }>;

export interface NavItem {
  name: string;
  href: string;
  icon: HeroIcon;
}

export interface SubmenuConfig {
  label: string;
  items: NavItem[];
  /** Custom active-state check for the parent nav item. Falls back to `checkIsActive` when absent. */
  isParentActive?: (pathname: string) => boolean;
}

export interface NavSection {
  id: string;
  label: string;
  items: NavItem[];
}

export interface TooltipState {
  name: string;
  top: number;
  left: number;
}

/** Shared Tailwind classes for sidebar nav link items (used by SidebarNavItem & SidebarSubmenuItem). */
export function navItemClasses(collapsed: boolean, isActive: boolean): string {
  return `group/navitem flex items-center rounded-lg transition-colors ${
    collapsed ? 'justify-center p-3' : 'px-3 py-2.5'
  } ${isActive ? 'bg-primary text-white' : 'text-gray-400 hover:bg-dark-700 hover:text-gray-200'}`;
}
