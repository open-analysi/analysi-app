# Definition of Done

Every UI feature or bug fix is only considered done after:

1. **At least one unit test** covering the new/changed behavior (Vitest + React Testing Library)
2. **Manual Playwright verification** in the browser confirming the feature works visually

Both steps are required before marking work complete.

## How to verify (try in order):

### 1. Playwright (preferred, try first)

1. Navigate to the relevant page: `mcp__playwright__browser_navigate` with `url: "http://localhost:5173/..."`
2. Take a screenshot: `mcp__playwright__browser_take_screenshot`
3. Interact if needed (click, fill, etc.) to verify dynamic behavior: `mcp__playwright__browser_click`, `mcp__playwright__browser_type`
4. Use `mcp__playwright__browser_snapshot` for accessibility tree inspection

**If Playwright fails with `browserType.launchPersistentContext: Failed to launch the browser process`** (log shows `"Opening in existing browser session"`), Chrome is already running and conflicts with Playwright's user-data-dir. `mcp__playwright__browser_close` alone won't fix this — skip to Chrome DevTools MCP or Puppeteer instead.

### 2. Chrome DevTools MCP (works when Chrome is already open)

1. List pages: `mcp__chrome-devtools__list_pages`
2. Navigate: `mcp__chrome-devtools__navigate_page` with `type: "url"` and `url: "http://localhost:5173/..."`
3. Take a screenshot: `mcp__chrome-devtools__take_screenshot`
4. Take a snapshot (a11y tree): `mcp__chrome-devtools__take_snapshot`
5. Interact: `mcp__chrome-devtools__click`, `mcp__chrome-devtools__fill`

### 3. Puppeteer (fallback)

1. Navigate to the relevant page: `mcp__puppeteer__puppeteer_navigate` with `url: "http://localhost:5173/..."`
2. Take a screenshot to confirm the feature is rendered correctly: `mcp__puppeteer__puppeteer_screenshot`
3. Interact if needed (click, fill, etc.) to verify dynamic behavior

## Setup notes:

- The dev server runs at `http://localhost:5173`
- Keycloak dev login: username `dev`, password `dev`
- Check `App.tsx` for the correct route paths if navigation redirects unexpectedly
- To get real data for testing (e.g., a workflow run ID), use `mcp__playwright__browser_evaluate` or `mcp__puppeteer__puppeteer_evaluate` to call `fetch('/api/...')` directly
- For Puppeteer: use `launchOptions: { headless: true, args: ["--no-sandbox", "--disable-setuid-sandbox"] }` and `allowDangerous: true` on the first `puppeteer_navigate` call

# Build, Lint, and Test Commands

- Development server: `http://localhost:5173`
- Build: `npm run build`
- Development: `npm run dev`
- Lint: `npm run lint` or `npm run lint:fix`
- Format: `npm run format`
- Test (watch mode): `npm run test`
- Run single test: `npm run test:once -- -t "test name"`
- Run related tests: `npm run test:related`
- Test coverage: `npm run test:coverage`
- Check (lint + format + test): `npm run check` - Use this before committing changes

# Linting Configuration

ESLint 9 flat config at `eslint.config.js`. Key plugins: `@typescript-eslint`,
`eslint-plugin-react`, `eslint-plugin-react-hooks`, `eslint-plugin-jsx-a11y`,
`eslint-plugin-sonarjs`, `eslint-plugin-unicorn`, `eslint-plugin-import`.

Enforced rules worth remembering:

- **Cognitive complexity limit**: 15 (SonarJS).
- **Duplicate strings**: max 5 occurrences before a constant is required (SonarJS).
- **File naming**: camelCase or PascalCase only (Unicorn).
- **Console methods**: only `console.warn`, `console.error`, `console.info` allowed.
- **Import order**: builtin → external (React first) → internal → parent → sibling → index,
  alphabetical within groups, newlines between groups.
- **TypeScript safety**: strict `no-unsafe-*` rules (call, member-access, assignment, argument, return).
- **No floating promises**: all promises must be awaited, caught, or explicitly `void`-ed.

Test files (`**/__tests__/**/*`, `*.test.*`, `*.spec.*`) and mocks
(`mocks/**/*`) relax the `no-unsafe-*` rules and allow explicit `any`.

Prettier: `semi: true`, `singleQuote: true`, `tabWidth: 2`,
`trailingComma: es5`, `printWidth: 100`.

# Pre-Commit Automation

Husky + lint-staged enforce quality on commit:

1. **Type check** — `tsc --noEmit` (warning only, does not block).
2. **ESLint with auto-fix** — staged `.ts`/`.tsx` files, treats warnings
   as errors (`--max-warnings 0`).
3. **Prettier** — auto-formats staged files.
4. **Related tests** — `vitest related` runs only tests affected by the
   staged diff, not the full suite.

Config files: `.husky/pre-commit`, `.lintstagedrc.mjs`,
`package.json` scripts (`type-check`, `lint`, `format`, `check`).

# Security Rules

- **NEVER commit API keys, secrets, or credentials** (even dev/test ones) in source code, scripts, or any file tracked by git. Always read them from environment variables or `.env` files (which must be in `.gitignore`).

# Code Style Guidelines

- TypeScript with strict mode enabled
- React functional components with hooks
- File naming: PascalCase for components, camelCase for utilities
- Formatting: Prettier with semi:true, singleQuote:true, tabWidth:2, printWidth:100
- Import order: builtin → external → internal → parent → sibling → index
- Use Tailwind CSS for styling
- Path aliases: @/_ for src/, @mocks/_ for mocks/
- Tests with Vitest and React Testing Library
- Prefer async/await over Promises
- Use TypeScript interfaces for object shapes
- Follow the centralized error handling system (see section below)
- Always look for existing code to iterate on instead of creating new code
- Always prefer simple solutions
- You are careful to only make changes that are requested or you are confident are well understood and related to the change being requested
- When fixing an issue or bug, do not introduce a new pattern or technology without first exhausting all options for the existing implementation. And if you finally do this, make sure to remove the old implementation afterwards so we don't have duplicate logic.
- Keep the codebase very clean and organized
- Avoid having files over 500 lines of code. Refactor at that point.
- Focus on the areas of code relevant to the task
- Do not touch code that is unrelated to the task
- Write thorough tests for all major functionality
- Avoid making major changes to the patterns and architecture of how a feature works, after it has shown to work well, unless explicitly instructed
- Always think about what other methods and areas of code might be affected by code changes
- When asked to refactor, just focuse on refactoring. Add tests that are missing that may introduce bugs or unwanted changes to functionality.
- When asked to add a feature, focuse on the feature, do not refactor! Do not change things that are unrelated to the feature at hand.

# API Types Architecture

Types flow through three layers:

```
src/generated/api.ts          ← auto-generated by openapi-typescript (DO NOT edit)
  ↓
src/types/api.ts              ← hand-maintained bridge file (maps API names → domain names)
  ↓
src/types/<domain>.ts         ← domain type files (alert.ts, taskRun.ts, workflow.ts, …)
```

## Rules

- **`src/generated/`** contains ONLY auto-generated files. Never put hand-written code there.
- **`src/types/api.ts`** is the bridge file. It imports from `../generated/api` and re-exports types with clean domain names (e.g., `Schemas['TaskRunResponse']` → `TaskRun`, `Schemas['AlertResponse']` → `Alert`). Update this file when the OpenAPI spec adds new schemas.
- **`src/types/<domain>.ts`** files import from `./api` (the bridge), add UI-only types (filters, query params, pagination state), and extend generated types when needed (e.g., `TaskRun` adds legacy `input`/`output`/`error` fields).
- Components and services **never** import from `src/generated/` directly. They import from `src/types/`.

## Why the bridge file exists

1. **Name decoupling** — The API spec uses `TaskRunResponse`, `AlertResponse`, etc. The UI uses `TaskRun`, `Alert`. Without the bridge, every import would be `Schemas['TaskRunResponse']`.
2. **Regeneration safety** — `api.ts` gets overwritten on every codegen run. The bridge is stable; if the backend renames a schema, you update one line, not 40 imports.
3. **Extension point** — Domain files can extend generated types with UI-only fields while keeping the generated types pure.

# Responsive Design Guidelines

- Ensure all UI components and pages adapt well to different screen sizes
- Target optimization for both laptop (1366x768) and desktop (1920x1080) screens
- Use Tailwind's responsive breakpoints consistently:
  - `md:` for laptop-optimized styles (≥768px)
  - `lg:` for desktop-optimized styles (≥1024px)
  - `xl:` for large desktop styles (≥1280px)
- For tables with many columns:
  - Wrap text inside cells with `wrap-break-word` instead of truncating
  - Hide less important columns on smaller screens using responsive classes
  - Use `table-fixed` with percentage widths to maintain column proportions
  - Implement horizontal scrolling with `overflow-x-auto` for when needed
- Implement a clear visual hierarchy that works at different screen sizes
- Test UI changes on both laptop and desktop displays before completing work
- Avoid designs that force horizontal scrolling on standard screen sizes
- Use responsive font sizes and spacing that adjust based on screen size

# Error Handling Guidelines

- Use `useErrorHandler` hook in components with async operations:

  ```typescript
  const { error, handleError, createContext, runSafe } = useErrorHandler('ComponentName');

  // Example usage
  const [result, error] = await runSafe(apiCall(params), 'methodName', {
    action: 'performing action',
    entityId: id,
  });
  ```

- Wrap key components with `ErrorBoundary` to catch render errors:

  ```tsx
  <ErrorBoundary component="ComponentName">
    <YourComponent />
  </ErrorBoundary>
  ```

- Provide rich context with every error for effective debugging:
  - Component/method name
  - Action being performed
  - Entity IDs and types
  - Relevant parameters

- Use `logger` utility with appropriate severity levels:

  ```typescript
  logger.error('Operation failed', error, context);
  logger.warn('Non-critical issue', warning, context);
  logger.info('Operation succeeded', data, context);
  logger.debug('Detailed information', details, context);
  ```

- For API calls, always provide error handling and user feedback
- Use error classification to generate appropriate user messages

# Form and Modal Guidelines

- **Unsaved Changes Protection**: Always implement confirmation dialogs when users attempt to close forms, modals, or wizards with unsaved changes.

## Critical Implementation Details for Escape Key Handling:

**IMPORTANT: The following approach is what actually works for Escape key handling in modals:**

```typescript
// Handle Escape key to close
useEffect(() => {
  const handleEscape = (event: KeyboardEvent) => {
    if (event.key === 'Escape' || event.key === 'Esc') {
      event.preventDefault();
      event.stopPropagation();

      // Check for unsaved changes directly in the handler
      // DO NOT use a separate function - check inline to avoid stale closures
      const hasChanges =
        formField1.length > 0 || formField2.length > 0 || Object.keys(formField3).length > 0;

      if (hasChanges) {
        if (
          window.confirm(
            'You have unsaved changes. Are you sure you want to exit? All your progress will be lost.'
          )
        ) {
          onClose();
        }
      } else {
        onClose();
      }
    }
  };

  // CRITICAL: Use document, not window, and use capture phase (true)
  document.addEventListener('keydown', handleEscape, true);
  return () => document.removeEventListener('keydown', handleEscape, true);
}, [formField1, formField2, formField3, onClose]); // Include ALL form state in deps
```

### Why this approach works:

1. **Use `document.addEventListener` with capture phase (`true`)** - catches event before any other handler
2. **Check state directly inline** - avoids stale closure issues with separate functions
3. **Include all form state in useEffect dependencies** - ensures handler always has current values
4. **Use `event.stopPropagation()`** - prevents other handlers from interfering
5. **Check both 'Escape' and 'Esc'** - browser compatibility

### What doesn't work:

- ❌ Using `window.addEventListener` - may miss events
- ❌ Using `useCallback` for handlers - creates stale closures
- ❌ Using refs to track state - adds complexity and can still fail
- ❌ Calling external functions from the handler - stale closure issues

### For other close methods (X button, Cancel, backdrop click):

```typescript
const handleSafeClose = () => {
  if (hasUnsavedChanges()) {
    if (window.confirm('You have unsaved changes. Are you sure you want to exit? All your progress will be lost.')) {
      onClose();
    }
  } else {
    onClose();
  }
};

// Backdrop click
<div className="modal-backdrop" onClick={handleSafeClose}>
  <div className="modal-content" onClick={(e) => e.stopPropagation()}>
    {/* content */}
  </div>
</div>
```

- Track form state to detect unsaved changes
- Use clear, specific warning messages that explain what will be lost
- Apply this pattern to all forms, wizards, and modal dialogs
- Consider the entire form state including multi-step wizards
- Use `ConfirmDialog` component instead of `window.confirm()` for discard confirmations

## Modal Styling Decision (Hybrid Approach)

We use a **hybrid approach** for modal styling with three tiers:

### 1. Confirmation Dialogs (ConfirmDialog component)

Used for: Confirmations, warnings, discard changes prompts

**Styling:**

- Dark-only background: `bg-dark-800`
- Darker backdrop: `bg-black/60`
- Icon with colored circular badge on left
- Compact layout
- Located at: `/src/components/common/ConfirmDialog.tsx`

**Usage:**

```tsx
<ConfirmDialog
  isOpen={showConfirm}
  onClose={() => setShowConfirm(false)}
  onConfirm={handleConfirm}
  title="Discard Unsaved Changes?"
  message="You have unsaved changes. Are you sure you want to exit?"
  confirmLabel="Discard Changes"
  cancelLabel="Keep Editing"
  variant="warning" // 'info' | 'warning' | 'question'
/>
```

### 2. Involved Modals — Standard (reference: IntegrationSetupWizard)

Used for: Multi-step wizards, import flows, any modal with meaningful content or forms.
The **IntegrationSetupWizard** is the reference implementation — all involved modals should match its look and feel.

**Styling:**

- Dark-only background: `bg-dark-800`
- Backdrop: `bg-black/50`
- Header: title (`text-xl font-semibold text-white`) + subtitle (`text-gray-400 text-sm mt-1`) + X button (`w-6 h-6`, `text-gray-400 hover:text-white`)
- Cancel button: `bg-dark-700 hover:bg-dark-600 rounded-sm text-white`
- Primary action button: `bg-primary hover:bg-primary-dark rounded-sm text-white font-medium`
- Footer: `flex justify-end space-x-3 mt-6`
- Max width: `max-w-lg` (single-step) to `max-w-4xl` (multi-step wizard)
- Rounded corners: `rounded-lg` (not `rounded-xl`)
- Examples: `IntegrationSetupWizard`, `SkillImportModal`

**Common Structure:**

```tsx
<Dialog open={isOpen} onClose={handleSafeClose} className="relative z-50">
  <div className="fixed inset-0 bg-black/50" aria-hidden="true" />
  <div className="fixed inset-0 flex items-center justify-center p-4">
    <DialogPanel className="mx-auto rounded-lg bg-dark-800 p-6 w-full max-w-lg max-h-[90vh] flex flex-col">
      {/* Header: title + subtitle on left, X button on right */}
      <div className="flex justify-between items-start mb-4">
        <div>
          <DialogTitle className="text-xl font-semibold text-white">Title</DialogTitle>
          <p className="text-gray-400 text-sm mt-1">Subtitle explaining the purpose</p>
        </div>
        <button onClick={onClose} className="text-gray-400 hover:text-white">
          <XMarkIcon className="w-6 h-6" />
        </button>
      </div>
      {/* Content */}
      <div className="flex-1 overflow-y-auto">...</div>
      {/* Footer */}
      <div className="flex justify-end space-x-3 mt-6">
        <button className="px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-sm text-white text-sm">
          Cancel
        </button>
        <button className="px-4 py-2 bg-primary hover:bg-primary-dark rounded-sm text-white text-sm font-medium">
          Action
        </button>
      </div>
    </DialogPanel>
  </div>
</Dialog>
```

### 3. Simple Form Modals (legacy pattern, being phased out)

Used for: Simple data entry (e.g., `SaveAsTaskModal`, `KnowledgeUnitEditModal`)

**Styling:** `bg-white dark:bg-gray-800`, `bg-black/30` backdrop. New modals should use the Involved Modal pattern (tier 2) instead.

### Key Patterns

| Aspect       | ConfirmDialog                | Involved Modal (standard)         | Simple Form Modal (legacy)                 |
| ------------ | ---------------------------- | --------------------------------- | ------------------------------------------ |
| Background   | `bg-dark-800`                | `bg-dark-800`                     | `bg-white dark:bg-gray-800`                |
| Backdrop     | `bg-black/60`                | `bg-black/50`                     | `bg-black/30`                              |
| Max width    | `max-w-md`                   | `max-w-lg` to `max-w-4xl`         | `max-w-xl` to `max-w-6xl`                  |
| Close button | None (Cancel button)         | X icon (`w-6 h-6`) in header      | X icon (`w-5 h-5`) in header               |
| Corners      | `rounded-lg`                 | `rounded-lg`                      | `rounded-xl`                               |
| Footer       | `flex justify-end space-x-3` | `flex justify-end space-x-3 mt-6` | `flex justify-end space-x-2 pt-4 border-t` |
| Cancel btn   | text button                  | `bg-dark-700` solid               | text button                                |

# Cytoscape.js Styling

- Use numeric values for all size properties: `'font-size': 64` not `'font-size': '64px'`
- Destroy and recreate instance to ensure styles apply properly
- Font sizes: small (12-16), medium (18-24), large (32-48), very large (64+)

# Workflow Visualization with Reaflow and react-zoom-pan-pinch

When implementing workflow visualizations that use Reaflow with react-zoom-pan-pinch for pan/zoom functionality, follow these guidelines to prevent viewport expansion while allowing full graph exploration:

## Container Constraints

- Set explicit container dimensions: `height: calc(100vh - 100px)` to prevent viewport expansion
- Use `overflow: hidden` on the container to clip content that extends beyond bounds
- Add `contain: layout size` CSS property for proper layout containment
- Ensure the container stays within viewport bounds to keep UI elements (navigation, settings) always visible

## Pan/Zoom Configuration

- Use `limitToBounds={false}` in TransformWrapper to allow free panning within the container
- Add `panning={{ velocityDisabled: true }}` for smoother, more controlled panning
- This allows users to explore all parts of large workflows without expanding the viewport

## CSS Implementation

```css
.workflow-container {
  width: 100%;
  height: calc(100vh - 100px);
  overflow: hidden;
  contain: layout size;
}

.workflow-container .react-transform-wrapper {
  width: 100% !important;
  height: 100% !important;
  overflow: hidden !important;
}

.workflow-container .react-transform-component {
  transform-origin: 0 0 !important;
}
```

## Key Principle

The viewport should never expand beyond window dimensions (no document scrollbars), but users should still be able to pan around to see all parts of the workflow within the constrained container. This maintains a consistent UI where navigation elements remain accessible.

## Preventing Edge Crossings in Reaflow/ELK Layouts

**Problem**: When multiple edges converge into a single node (e.g., an aggregation node), ELK's automatic layout may create unnecessary edge crossings where the top edge routes low and the bottom edge routes high, crossing in the middle.

**Solution**: Use explicit ports with sorted edge assignment to maintain vertical ordering.

### Implementation:

1. **Add ports to nodes** based on incoming/outgoing edge counts:

```typescript
const ports = [];
const incomingCount = workflow.edges.filter((e) => e.to_node_uuid === node.id).length;
const outgoingCount = workflow.edges.filter((e) => e.from_node_uuid === node.id).length;

// Input ports on WEST side
for (let i = 0; i < Math.max(incomingCount, 1); i++) {
  ports.push({
    id: `${node.id}-in-${i}`,
    side: 'WEST',
    width: 10,
    height: 10,
  });
}

// Output ports on EAST side
for (let i = 0; i < Math.max(outgoingCount, 1); i++) {
  ports.push({
    id: `${node.id}-out-${i}`,
    side: 'EAST',
    width: 10,
    height: 10,
  });
}
```

2. **Sort edges by source node ID** before assigning to target ports:

```typescript
// Group edges by target node
const edgesByTarget = new Map<string, typeof workflow.edges>();
workflow.edges.forEach((edge) => {
  if (!edgesByTarget.has(edge.to_node_uuid)) {
    edgesByTarget.set(edge.to_node_uuid, []);
  }
  edgesByTarget.get(edge.to_node_uuid)!.push(edge);
});

// Sort edges to each target by source node ID (alphabetically)
edgesByTarget.forEach((edges) => {
  edges.sort((a, b) => a.from_node_uuid.localeCompare(b.from_node_uuid));
});

// Assign edges to ports based on sorted position
const targetEdges = edgesByTarget.get(edge.to_node_uuid)!;
const targetInIndex = targetEdges.indexOf(edge);
const toPort = `${edge.to_node_uuid}-in-${targetInIndex}`;
```

3. **Use FIXED_ORDER port constraints** in ELK layout options:

```typescript
layoutOptions={{
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
  'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
  'elk.portConstraints': 'FIXED_ORDER',  // Critical!
}}
```

**Why it works**: Sorting edges alphabetically by source node UUID ensures consistent vertical ordering. When combined with FIXED_ORDER port constraints, ELK respects the port assignment, preventing edges from swapping positions and crossing unnecessarily.

**Important**: Do NOT add a `properties` field to ports - it causes ELK JSON parsing errors. Keep port definitions simple with just id, side, width, and height.

## Stale Closures in Reaflow Callbacks

Reaflow caches `onClick` handlers passed to `<Node>`. If the handler closes over React state (e.g., `connectMode`, `connectSourceId`), it will read stale values after state updates.

**Solution**: Use ref-based wrapper setters that update both the ref (synchronously) and state (for re-render). Read from refs inside callbacks:

```typescript
const [connectMode, _setConnectMode] = useState(false);
const connectModeRef = useRef(false);
const setConnectMode = useCallback((value: boolean) => {
  connectModeRef.current = value;
  _setConnectMode(value);
}, []);

// In Reaflow onClick — read from ref, not state
const handleNodeClick = useCallback(
  (_event, nodeData) => {
    if (connectModeRef.current) {
      /* ... */
    }
  },
  [store]
); // No connectMode in deps — ref is always current
```

## E2E Testing: Clicking SVG Nodes on Reaflow Canvas

**Never use `page.mouse.click(x, y)` to click Reaflow canvas nodes.** SVG `<g>` groups have extended hit areas (ports, labels) that overlap adjacent nodes, causing the browser to route coordinate-based clicks to the wrong node.

**Solution**: Find the target `<rect>` element by matching `foreignObject` text content, then dispatch the click event directly on it:

```typescript
const found = await page.evaluate((name: string) => {
  const foreignObjects = document.querySelectorAll('foreignObject');
  for (const fo of foreignObjects) {
    if (!fo.textContent?.includes(name)) continue;
    const rect = fo.parentElement?.querySelector(':scope > rect');
    if (rect) {
      const bounds = rect.getBoundingClientRect();
      rect.dispatchEvent(
        new MouseEvent('click', {
          bubbles: true,
          cancelable: true,
          clientX: bounds.x + bounds.width / 2,
          clientY: bounds.y + bounds.height / 2,
          view: window,
        })
      );
      return true;
    }
  }
  return false;
}, nodeName);
```

This ensures the event bubbles through the correct `<g>` parent to trigger the right `onClick` handler.

# URL State Management Guidelines

All UI state that users might want to bookmark, share, or return to via browser back button should be stored in URL parameters.

## Required URL State:

- Active tabs/views: `?tab=tabname`
- Search/filter terms: `?search=term&filter=value`
- Pagination: `?page=2&limit=50`
- Sort order: `?sort=field_direction`
- Expanded/modal states: `?expanded=id&modal=type`

## Implementation:

Always use the `useUrlState` hook for URL-persisted state:

```typescript
const [activeTab, setActiveTab] = useUrlState('tab', 'details');
const [searchTerm, setSearchTerm] = useUrlState('search', '');
const [page, setPage] = useUrlState('page', 1, { type: 'number' });
```

For multiple related values, use `useUrlStateObject`:

```typescript
const [filters, setFilters] = useUrlStateObject({
  status: 'all',
  priority: 'any',
  search: '',
});
```

## Rules:

1. Use descriptive, short parameter names
2. Don't store sensitive data in URLs (no API keys, passwords, tokens)
3. Clean defaults from URL (if tab='details' is default, don't show ?tab=details)
4. Use replace:true for state changes to avoid cluttering history
5. Validate URL params on load to handle invalid/outdated links
6. Keep URL parameters consistent across similar pages (all lists use 'page', 'sort', 'search')

## Setting Multiple URL Parameters Atomically

**IMPORTANT**: When you need to update multiple URL parameters at once (e.g., navigating to a specific tab AND subtab), do NOT call multiple `useUrlState` setters sequentially. Each setter calls `setSearchParams` internally, and subsequent calls can overwrite previous ones due to how React batches state updates.

**Problem - Race Condition:**

```typescript
// ❌ BAD: These calls race and the second may overwrite the first
setActiveTab('analysis'); // Sets ?tab=analysis
setActiveSubTab('artifacts'); // May overwrite to just ?subtab=artifacts
```

**Solution - Use setSearchParams directly:**

```typescript
const [, setSearchParams] = useSearchParams();

// ✅ GOOD: Update both params in a single atomic operation
setSearchParams(
  (prev) => {
    prev.set('tab', 'analysis');
    prev.set('subtab', 'artifacts');
    return prev;
  },
  { replace: true }
);
```

This ensures both parameters are set in a single URL update, avoiding race conditions.

## Testing:

When implementing a new feature with URL state, verify:

- Browser back/forward navigation maintains state correctly
- Page refresh preserves all UI state
- Sharing URL with colleague opens same view
- Invalid URL params fall back gracefully to defaults
- Direct navigation via URL works (e.g., /alerts/123/v2?tab=workflow-tasks)

## Examples:

- Alert Details tabs: `/alerts/123/v2?tab=workflow-tasks`
- Filtered list: `/alerts?status=open&priority=high&search=ransomware`
- Pagination: `/integrations?page=2&sort=name_asc`
- Modal state: `/workflows/456?modal=execution&runId=789`

# Component Testing Guidelines (Vitest + React Testing Library)

## Headless UI Dialog `act()` Warnings

Components that use `<Dialog>` from `@headlessui/react` perform async state transitions on mount and unmount. Rendering them synchronously in tests produces React `act()` warnings:

> "An update to Ie inside a test was not wrapped in act(...)"
> "A component suspended inside an `act` scope, but the `act` call was not awaited"

### Solution: Async render helper with microtask flush

```typescript
import { render, act } from '@testing-library/react';

// Create a helper that renders and waits for Dialog transitions to settle
async function renderModal(ku: KnowledgeUnit | null) {
  const result = render(
    <MyModal isOpen={true} onClose={mockOnClose} data={ku} />
  );
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });
  return result;
}

// Use in every test:
it('should render correctly', async () => {
  await renderModal(mockData);
  expect(screen.getByText('Title')).toBeInTheDocument();
});
```

### When a second Dialog opens (e.g., ConfirmDialog)

Actions that open or close a nested Dialog (ConfirmDialog, alert, etc.) also trigger transitions. Wrap them in `act()`:

```typescript
// Opening a ConfirmDialog via Cancel click
await act(async () => {
  fireEvent.click(screen.getByText('Cancel'));
  await new Promise((r) => setTimeout(r, 0));
});

// Closing a dialog via Discard/Confirm button
await act(async () => {
  fireEvent.click(screen.getByText('Discard Changes'));
  await new Promise((r) => setTimeout(r, 0));
});
```

### Prefer `fireEvent.change` over `userEvent.type` when triggering Dialog opens

`userEvent.type` wraps each keystroke in its own `act()` scope. If the test then opens a Dialog (e.g., by clicking Cancel), the keystroke-level `act` scope can conflict with the Dialog's Suspense-like transitions, producing:

> "A component suspended inside an `act` scope"

Fix: Use `fireEvent.change` for setting form values when the test's purpose is to verify Dialog behavior, not typing behavior:

```typescript
// Instead of: await userEvent.type(input, ' Modified');
fireEvent.change(nameInput, { target: { value: 'Modified Value' } });
```

### Summary of rules

| Scenario                                               | Pattern                                                                   |
| ------------------------------------------------------ | ------------------------------------------------------------------------- |
| Render a component with Dialog                         | `await renderModal(...)` with microtask flush                             |
| Open a nested Dialog (Cancel/X/Escape with dirty form) | Wrap `fireEvent.click` in `act(async () => { ...; await setTimeout(0) })` |
| Set form values before Dialog tests                    | `fireEvent.change` instead of `userEvent.type`                            |
| Assert after Dialog close                              | Wrap in `await waitFor(() => { ... })`                                    |

## Mock Typing Best Practices

- Use `vi.mocked(module.fn)` instead of `(module.fn as any).mockReturnValue` — provides type safety
- Use `vi.mocked(useStore).mockReturnValue({...} as ReturnType<typeof useStore>)` for Zustand stores
- Avoid `as any` in test fixtures — use `as unknown as TargetType` or proper type narrowing
