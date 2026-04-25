# Sidebar Navigation Rules

## Architecture

The sidebar lives in `src/components/sidebar/` with these files:

| File                     | Purpose                                                                                  |
| ------------------------ | ---------------------------------------------------------------------------------------- |
| `Sidebar.tsx`            | Main container — collapse/expand, logo, sections, tooltip                                |
| `SidebarNavItem.tsx`     | Single nav link (icon + label)                                                           |
| `SidebarSubmenuItem.tsx` | Nav link with flyout popover (Workbench, History)                                        |
| `sidebarConfig.ts`       | Navigation items, sections, submenus, active-state helpers                               |
| `types.ts`               | TypeScript interfaces (`NavItem`, `NavSection`, etc.) + shared `navItemClasses()` helper |
| `index.ts`               | Barrel export                                                                            |

Collapse state is managed by `src/hooks/useSidebarCollapse.ts` (persisted in localStorage).

## Dual-state design

The sidebar operates in two modes:

- **Expanded** (256px): Icon + text label + section headers + chevron indicators on submenu items
- **Collapsed** (64px): Icon only + separators between sections + fixed-position tooltips on hover

The `<aside>` uses `h-screen sticky top-0` so it stays pinned to the viewport and the internal nav scrolls independently.

## Section grouping

Navigation is organized into 4 groups (defined in `sidebarConfig.ts`):

1. **Core**: Alerts, Integrations, Tasks, Workflows
2. **Develop**: Workbench (submenu), History (submenu)
3. **Knowledge**: List, Graph, Skills
4. **Admin** (pinned to bottom via `mt-auto`): Settings, Audit Trail, Account

Section labels must NOT conflict with any nav item name (e.g., use "Develop" not "Workbench" for the section that contains the Workbench item).

## Nav item rendering rules

- Regular nav items use `SidebarNavItem` — renders a `<Link>` directly
- Submenu nav items use `SidebarSubmenuItem` — renders `<React.Fragment>` containing a `<Link>` + fixed-position popover
- All items within a section live inside a `<div className="flex flex-col gap-0.5">` for consistent spacing
- Both components use the shared `navItemClasses(collapsed, isActive)` function from `types.ts` for consistent styling
- Active state: `bg-primary text-white` with `aria-current="page"`
- Inactive state: `text-gray-400 hover:bg-dark-700 hover:text-gray-200`

## Adding submenus or popovers

If a nav item needs a flyout submenu:

1. Add a `SubmenuConfig` entry in `submenuConfigs` (in `sidebarConfig.ts`)
2. Include an `isParentActive` callback to control when the parent item highlights (e.g., `isParentActive: (pathname) => pathname === '/workbench'`)
3. The `Sidebar.tsx` `renderNavItem` function automatically detects items with submenu configs and renders `SidebarSubmenuItem`
4. The submenu item uses `React.Fragment` to group the `<Link>` and popover as siblings
5. Use `onClick` with `e.preventDefault()` to toggle the popover
6. The popover is **fixed-position**, placed via `getBoundingClientRect()`
7. Dismissal: click-outside (`mousedown` listener), Escape key (`keydown` capture), or route change (derived state via `openForLocation`)

## Accessibility

- `<aside>` has `aria-label="Main navigation"`
- Active items have `aria-current="page"`
- Submenu triggers have `aria-haspopup="true"` and `aria-expanded`
- Popover has `role="menu"`, sub-items have `role="menuitem"`
- Escape key closes flyout and returns focus to trigger

## Tooltips

Tooltips in collapsed mode are managed centrally in `Sidebar.tsx` (single tooltip element, fixed-position). Each nav item receives `onMouseEnter`/`onMouseLeave` callbacks that update the tooltip state. This avoids per-item tooltip state and keeps the DOM clean.

## Adding a new nav item

1. Add the item to the appropriate section in `getNavSections()` or `getAdminItems()` in `sidebarConfig.ts`
2. If it needs env-based versioning, create a builder function (like `getAlertItems()`)
3. If it needs a submenu, add a `SubmenuConfig` entry in `submenuConfigs` with an `isParentActive` callback
4. If it needs custom active-state logic for a non-submenu item, add a case to `checkIsActive()`
