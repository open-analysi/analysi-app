import {
  AcademicCapIcon,
  ArrowPathIcon,
  BeakerIcon,
  BellIcon,
  BoltIcon,
  BookOpenIcon,
  CheckCircleIcon,
  ClipboardDocumentListIcon,
  ClockIcon,
  Cog6ToothIcon,
  PlayCircleIcon,
  PuzzlePieceIcon,
  RectangleGroupIcon,
  ShareIcon,
  UserCircleIcon,
  WrenchScrewdriverIcon,
} from '@heroicons/react/24/outline';

import type { NavItem, NavSection, SubmenuConfig } from './types';

// --- Section definitions ---

export function getNavSections(): NavSection[] {
  return [
    {
      id: 'core',
      label: 'Core',
      items: [
        { name: 'Alerts', href: '/alerts', icon: BellIcon },
        { name: 'Integrations', href: '/integrations', icon: PuzzlePieceIcon },
        { name: 'Tasks', href: '/tasks', icon: CheckCircleIcon },
        { name: 'Workflows', href: '/workflows', icon: RectangleGroupIcon },
      ],
    },
    {
      id: 'develop',
      label: 'Develop',
      items: [
        { name: 'Workbench', href: '/workbench', icon: BeakerIcon },
        { name: 'History', href: '/execution-history', icon: ClockIcon },
      ],
    },
    {
      id: 'knowledge',
      label: 'Knowledge',
      items: [
        { name: 'List', href: '/knowledge-units', icon: BookOpenIcon },
        { name: 'Graph', href: '/knowledge-graph', icon: ShareIcon },
        { name: 'Skills', href: '/skills', icon: AcademicCapIcon },
      ],
    },
  ];
}

export function getAdminItems(): NavItem[] {
  return [
    { name: 'Settings', href: '/settings', icon: Cog6ToothIcon },
    { name: 'Audit Trail', href: '/audit', icon: ClipboardDocumentListIcon },
    { name: 'Account', href: '/account-settings', icon: UserCircleIcon },
  ];
}

// --- Submenu configurations ---

export const submenuConfigs: Record<string, SubmenuConfig> = {
  Workbench: {
    label: 'Workbench',
    items: [
      { name: 'Tasks', href: '/workbench?tab=execute', icon: PlayCircleIcon },
      { name: 'Workflows', href: '/workbench?tab=builder', icon: WrenchScrewdriverIcon },
    ],
    isParentActive: (pathname) => pathname === '/workbench',
  },
  History: {
    label: 'History',
    items: [
      { name: 'Task Runs', href: '/execution-history?view=tasks', icon: PlayCircleIcon },
      { name: 'Workflow Runs', href: '/execution-history?view=workflows', icon: ArrowPathIcon },
      {
        name: 'Task Building',
        href: '/execution-history?view=task-building',
        icon: WrenchScrewdriverIcon,
      },
      {
        name: 'Control Events',
        href: '/settings?section=control-events&tab=history',
        icon: BoltIcon,
      },
    ],
    isParentActive: (pathname) =>
      pathname.startsWith('/execution-history') || pathname === '/settings',
  },
};

// --- Active state helpers ---

export function checkIsActive(itemHref: string, pathname: string): boolean {
  // Alerts
  if (itemHref === '/alerts') {
    return pathname === '/alerts' || pathname.startsWith('/alerts/');
  }
  // Integrations
  if (itemHref === '/integrations') {
    return pathname === '/integrations' || pathname.startsWith('/integrations/');
  }
  // Default: exact match
  return pathname === itemHref;
}

function matchesAllQueryParams(subHref: string, pathname: string, search: string): boolean {
  const [hrefPath, hrefQuery] = subHref.split('?');
  if (pathname !== hrefPath) return false;
  const params = new URLSearchParams(hrefQuery);
  const searchParams = new URLSearchParams(search);
  for (const [key, value] of params.entries()) {
    if (searchParams.get(key) !== value) return false;
  }
  return true;
}

export function checkIsSubmenuActive(subHref: string, pathname: string, search: string): boolean {
  if (subHref.includes('tab=')) {
    const tab = subHref.split('tab=')[1];
    if (pathname === '/workbench') {
      // 'execute' is the default tab — active when no tab param is present
      if (tab === 'execute') {
        return !search.includes('tab=') || search.includes('tab=execute');
      }
      return search.includes(`tab=${tab}`);
    }
    return false;
  }
  if (subHref.includes('view=')) {
    const view = subHref.split('view=')[1];
    return pathname === '/execution-history' && search.includes(`view=${view}`);
  }
  if (subHref.includes('section=')) {
    return matchesAllQueryParams(subHref, pathname, search);
  }
  return false;
}
