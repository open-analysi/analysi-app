# UI Design Decisions

Historical log of UI/UX design decisions made during Analysi UI development.
Imported from the UI project's decision log when the UI repo was folded
in-tree. Grouped by area of the app.

Each decision records the choice made and the reasoning at the time. Some
may now be obsolete; treat this as a history of intent, not current spec.

## Contents

- [Architecture & Tooling](#architecture-tooling) (7)
- [Testing & Verification](#testing-verification) (5)
- [Cross-cutting UX Patterns](#cross-cutting-ux-patterns) (3)
- [Modals & Dialogs](#modals-dialogs) (1)
- [Navigation & Settings](#navigation-settings) (3)
- [Alert Details Page](#alert-details-page) (2)
- [Workbench](#workbench) (14)
- [Workflow Builder](#workflow-builder) (8)
- [Workflow Visualization](#workflow-visualization) (2)
- [Live Workflow Page](#live-workflow-page) (3)
- [AI Task Builder](#ai-task-builder) (5)
- [Task Runs & Listing](#task-runs-listing) (5)
- [Task Deletion Flow](#task-deletion-flow) (2)
- [Execution History](#execution-history) (2)
- [Findings Display](#findings-display) (4)
- [Integrations UI](#integrations-ui) (8)
- [Knowledge Graph](#knowledge-graph) (6)
- [Knowledge Page](#knowledge-page) (1)
- [Skills Page](#skills-page) (3)
- [Other](#other) (2)

## Architecture & Tooling

### API: Fetch limits

**Decision:** Use limit=10000 instead of no limit for fetching all items from API

**Reasoning:** Practical upper bound that fetches everything while avoiding unbounded requests

### Git: Pre-commit hooks

**Decision:** Use --no-verify when pre-existing lint errors block commits of unrelated changes

**Reasoning:** Pre-existing errors shouldn't block progress on new features

### JSON diff structural changes only

**Decision:** Workbench JSON diff view should only highlight structural changes (added/removed/modified keys), not formatting differences (whitespace, indentation)

**Reasoning:** Formatting noise drowns out meaningful changes; analysts care about data changes not pretty-printing

### Use library for JSON diff

**Decision:** Use an existing diff library for JSON diff visualization instead of writing custom UI code

**Reasoning:** Reduces maintenance burden and UI code complexity

### Tenant from JWT not hardcoded env var

**Decision:** Tenant should come from JWT/auth (Valkey), not from VITE_BACKEND_API_TENANT env var. Move the env var to .env.test for testing only

**Reasoning:** Runtime auth is the correct source of truth; a hardcoded tenant name is a security/correctness risk

### Bridge file must not live in src/generated/

**Decision:** Hand-maintained type bridge file must NOT reside in src/generated/ — moved to src/types/api.ts. src/generated/ is reserved for auto-generated files only

**Reasoning:** Hand-maintained code in src/generated/ is misleading and risks being overwritten during codegen

### Document API types bridge architecture in CLAUDE.md

**Decision:** The three-layer type architecture (src/generated/api.ts → src/types/api.ts → src/types/<domain>.ts) must be documented in CLAUDE.md as a permanent project pattern

**Reasoning:** Makes the bridge file purpose clear to all contributors and prevents accidental removal


## Testing & Verification

### Playwright: Browser management

**Decision:** Don't kill vite server when running Playwright - use existing dev server

**Reasoning:** More efficient development workflow, faster testing iterations

### Definition of Done: browser verification via Playwright

**Decision:** Every UI feature or bug fix must be verified visually in the browser (via Playwright) before being considered done

**Reasoning:** Team was completing features without browser verification, leading to undetected visual regressions

### Browser verification tool priority

**Decision:** Use Playwright first for browser verification; fall back to Puppeteer only if Playwright does not work

**Reasoning:** Playwright is the preferred tool; Puppeteer should only be used as a fallback, not as the primary verification method

### Playwright browser conflict workaround in CLAUDE.md

**Decision:** Document in CLAUDE.md that when Playwright fails with browserType.launchPersistentContext error, Chrome is already open — close Playwright first or use Chrome DevTools MCP instead

**Reasoning:** Recurring issue that wastes debugging time

### E2E test coverage priorities

**Decision:** E2E test priorities: Settings, Alerts exploration (not specific values), Alert details, Execution history, Knowledge units, Workflow-runs visualization. Unit tests first, then E2E. Focus on functionality not exact values

**Reasoning:** Focus on functional verification over exact data matching; these are the highest-value user flows


## Cross-cutting UX Patterns

### Overview tab: Content strategy

**Decision:** Remove redundant info (short summary, current analysis). Add clickable quick stats cards linking to sub-tabs (Findings, Artifacts)

**Reasoning:** Overview should provide navigation to detailed content, not duplicate it

### Lists: Pagination strategy

**Decision:** Add client-side pagination (10 items/page) to TaskRunList and ArtifactList, similar to TasksTable

**Reasoning:** Consistent UX pattern across the app for list components

### Viewport must never shift on user actions

**Decision:** Workbench viewport must never shift or expand on user actions like clicking diff, executing tasks, etc.

**Reasoning:** Shifting viewport disorients the user and breaks their focus context


## Modals & Dialogs

### Modals: Confirmation dialogs

**Decision:** Use ConfirmDialog component consistently instead of window.confirm()

**Reasoning:** Consistent UX, better styling, follows app design patterns


## Navigation & Settings

### History nav: sidebar popover sub-menu

**Decision:** History navigation in the left sidebar shows sub-options as a popover/submenu on click rather than requiring two clicks and large mouse movements

**Reasoning:** Two-click + mouse movement pattern was inefficient; showing sub-options directly from the sidebar on click reduces friction

### Sidebar nav: local CLAUDE.md for pattern docs

**Decision:** Add a CLAUDE.md in the nav bar directory to document the nav item implementation pattern so it is not repeated incorrectly

**Reasoning:** A structural mistake in how the History nav item was implemented was hard to debug; local CLAUDE.md prevents recurrence

### Settings is platform-level not account-level

**Decision:** Remove Settings from the Account flyout menu — Settings is platform-level configuration, not per-account

**Reasoning:** Conceptual separation: account settings are user-specific, platform settings affect the whole instance


## Alert Details Page

### Alert Details: Analysis tab layout

**Decision:** Use sub-tabs for Workflow Run and Task Runs within Analysis Details tab

**Reasoning:** Keeps the UI organized while showing related workflow information together

### Alert Details: Artifacts sub-tab

**Decision:** Add Artifacts as third sub-tab under Analysis Details

**Reasoning:** Natural grouping of analysis-related content (workflow, tasks, artifacts)

## Workbench

### Workbench: Button grouping

**Decision:** Two button groups - Script Actions (New/Save/Save As) on left with outline-solid style, Action buttons (Copy icon/Run green) on right

**Reasoning:** Visual separation of workflow actions from execution actions

### Workbench: New task creation

**Decision:** Remove 'New Ad Hoc Script' from TaskSelector dropdown, use 'New' button in toolbar instead

**Reasoning:** Single consistent entry point for creating new scripts

### Workbench: Run with unsaved changes

**Decision:** Show dialog requiring Save or Save As before running modified tasks. No 'Run Without Saving' option

**Reasoning:** Running unsaved changes would execute the old DB version, which is confusing - force explicit save

### Workbench: Save As naming

**Decision:** Auto-generate versioned name (e.g., 'Task Name v2', 'v3') and copy original description when using Save As

**Reasoning:** Reduces friction, maintains traceability to original task

### Workbench: Header removal

**Decision:** Remove Workbench page header ('Workbench' title and 'Execute and test tasks' subtitle)

**Reasoning:** Reclaim vertical real estate - header provides no actionable value

### Workbench: Save button behavior

**Decision:** Save button opens Save As modal when no task is selected (not just in explicit ad-hoc mode)

**Reasoning:** When no task is selected, clicking Save has no target to update, so redirect to Save As for clearer UX

### Workbench nav: sidebar sub-menu popover

**Decision:** Apply the same sidebar sub-menu popover treatment to the Workbench nav item (Tasks workbench / Workflows workbench)

**Reasoning:** History nav was improved with a popover sub-menu; Workbench has two modes and should use the same pattern for consistency

### Workbench sub-menu labels

**Decision:** Call the workbench sub-menu options 'Tasks' and 'Workflows', not 'Task Execution' and 'Workflow Builder'

**Reasoning:** Short descriptive names are cleaner and self-evident; longer names added noise without clarity

### Workbench: input/output diff toggle

**Decision:** Add a toggle in the Workbench output panel to switch between full output view and a delta/diff view showing only what changed from the input JSON

**Reasoning:** When tasks modify large JSON inputs, spotting what changed is hard without a diff; a diff toggle makes the delta immediately visible

### Workbench: diff toggle auto-scroll

**Decision:** When clicking the diff toggle, automatically scroll to the first changed (green) section if one exists

**Reasoning:** In large outputs, the diff section may not be in the initial viewport; auto-scrolling to the first change saves the user from hunting for it

### Workbench: Cmd+Enter run shortcut

**Decision:** Use Cmd+Enter (Mac) / Ctrl+Enter (Win/Linux) as the keyboard shortcut to run a task in the Workbench

**Reasoning:** Cmd+Enter is a more standard convention for execute actions in IDEs; Shift+Enter is often used for newlines

### Workbench: remove legacy unused workbench

**Decision:** Remove any unused legacy workbench that is no longer in use

**Reasoning:** Keeping dead code creates confusion about which workbench is current and violates the no-duplicate-logic principle

### Workbench: task analysis in left sidebar

**Decision:** Show task script analysis (tools/integrations used) in the left sidebar of the Workbench, below the description section

**Reasoning:** The sidebar has unused real estate below the description; displaying dependencies there keeps the main editor area uncluttered

### Workbench: tool badges clickable to code location

**Decision:** Tool badges in the Workbench sidebar are clickable and navigate the editor to the line(s) where the tool is used in the script

**Reasoning:** Showing which tools are used is more useful when users can immediately jump to the usage location in the code


## Workflow Builder

### Workflow Builder: Grid background

**Decision:** Add light dot grid pattern to canvas background

**Reasoning:** Visual reference for node positioning, common pattern in workflow builder tools like n8n and Node-RED

### Workflow Builder: Disable auto-connect

**Decision:** New nodes added from palette are stacked without automatic edge connections

**Reasoning:** Auto-connect was too aggressive, forced linear workflows and made parallel branches frustrating

### Workflow Builder: Node action buttons layout

**Decision:** Delete button (X) at top-left, Connect button (+) at bottom-right of selected nodes

**Reasoning:** Flow is left-to-right, so connect button at bottom-right feels more natural for outgoing edges

### Workflow Builder: Auto-merge on fan-in

**Decision:** Automatically insert a merge transformation node when creating fan-in connections (multiple edges to same target)

**Reasoning:** Opinionated UX - prevents invalid multi-input states, enforces proper data flow patterns

### Workflow Builder: Fan-in merge node behavior

**Decision:** When multiple edges fan into a single node, auto-insert a merge node; further edges to the same target connect to the existing merge node

**Reasoning:** Being opinionated about fan-in prevents messy graphs; auto-merge nodes make topology cleaner and visually predictable

### Workflow Builder: Merge node reuse

**Decision:** When adding edges to a node that already has a merge node feeding it, connect to the existing merge instead of creating a new one

**Reasoning:** Avoids redundant merge chains, keeps workflow topology clean

### Workflow Builder: Fixed toolbox on scroll

**Decision:** The right-side toolbox stays fixed in position as the user scrolls the canvas left or right

**Reasoning:** Scrolling the canvas caused the toolbox to go off-screen; fixed positioning keeps tools always reachable

### Workflow Builder: Node descriptions on hover

**Decision:** Show task/transformation descriptions on hover tooltip; defer additional display modes for later

**Reasoning:** Hover is the quickest way to surface documentation without disrupting the building flow


## Workflow Visualization

### Workflow duration color thresholds

**Decision:** Workflows use different duration color thresholds than tasks: green below 1 minute, red at 10 minutes or more

**Reasoning:** Workflow executions are inherently longer than tasks; applying the same thresholds as tasks would incorrectly flag normal workflow durations as slow

### Workflow graph: leftmost node anchored to left edge

**Decision:** Workflow graph layout starts with the leftmost node at the far left of the canvas (not centered)

**Reasoning:** Centering caused the left and right extremes of large graphs to be clipped; anchoring to the left preserves the full layout within the viewport


## Live Workflow Page

### Live workflow: shareable URL required

**Decision:** Live workflow execution view must have a shareable URL; absence of one was identified as a gap to fix

**Reasoning:** Users looking at a live workflow had no URL to share with colleagues, making collaboration on running executions impossible

### Live workflow: dedicated page not modal

**Decision:** Move live workflow execution from a modal to a dedicated page with its own URL

**Reasoning:** Modal had no shareable URL; a proper page allows bookmarking, sharing, and browser navigation

### Live workflow: page-centric approach

**Decision:** Use a page-centric (not embedded) approach for the live workflow graph

**Reasoning:** Embedded approach would be fixed at 500px height; page-centric approach gives full-page real estate and proper URL


## AI Task Builder

### AI indicator icon

**Decision:** Use SparklesIcon from Heroicons for AI-generated content indicator

**Reasoning:** Industry-standard icon for AI/smart features, cleaner than custom SVG

### AI task builder UI pattern

**Decision:** Modal (Recommended)

**Options considered:** Modal (Recommended); Sidebar Panel; Keep it minimal

**Reasoning:** Modal was explicitly chosen over sidebar panel and minimal interface as the preferred approach for the task generation UI

### AI task builder: example prompts while generating

**Decision:** While AI generates the cy script, show example prompts (clickable to fill the main prompt) in the modal background instead of showing partial generated code

**Reasoning:** Showing partial in-progress code was not useful; showing example prompts gives users inspiration and utility while waiting

### AI task builder: alert context dropdown

**Decision:** Provide a dropdown to select an alert as context for AI task generation; show top 10 with a search bar filtered by title

**Reasoning:** The backend API supports an alert as context/example for testing the new task; surfacing this in the UI improves task generation quality

### AI task builder: variant selection as modal

**Decision:** Show the variant selection experience as a modal (not inline); open it early with an advisory not to close it; place Confirm variant action at the top

**Reasoning:** Inline experience was hard to find and the confirm button was buried at the bottom of a long list; modal ensures visibility and correct guidance


## Task Runs & Listing

### Tasks table: Row interaction

**Decision:** Make entire row clickable for expand/collapse. Add compact pink edit button in Actions column. Remove 'Open in Workbench' from expanded section

**Reasoning:** Faster navigation - single click anywhere expands, dedicated edit button is always visible

### Task run View Details: source links

**Decision:** In task run View Details, the Source section links to: the workflow, the workflow run, and the alert analysis that triggered it; all can be null for ad-hoc tasks

**Reasoning:** Existing labels were incorrect (Analysis pointed to workflow run); proper source attribution is needed for traceability

### Task run filter chain: alert to task

**Decision:** Filter task runs by alert by chaining: alert → analysis runs → workflow runs → task runs (not a direct workflow_run_id filter)

**Reasoning:** Direct workflow run filter was unreliable; chaining through analysis runs correctly maps an alert to all related task executions

### Task-building history: click opens Workbench

**Decision:** Clicking a created task in the task-building execution history opens it in the Workbench for editing, not the task list page

**Reasoning:** The natural next step after seeing a generated task is to edit/refine it; opening the Workbench is more actionable than the list view

### Deleted task UX in task runs

**Decision:** When a task referenced by a task run has been deleted, show a 'Task deleted' badge in the expanded details and hide the 'Open in Workbench' button instead of letting users click through to a 404

**Reasoning:** Better UX than silently failing or showing a confusing error page


## Task Deletion Flow

### Task deletion: usage check first

**Decision:** Before deleting a task, check if any workflows use it; if yes, show a message to remove the task from those workflows or delete the workflows first

**Reasoning:** Deleting a task in use breaks dependent workflows; usage check prevents data integrity issues and gives clear corrective guidance

### Task deletion: frontend check-first flow

**Decision:** Frontend calls the usage-check API first and shows the appropriate message rather than attempting deletion and catching the error response

**Reasoning:** Catching a 409 shows a generic error; proactive checking gives users a clear, actionable message before any destructive action


## Execution History

### Execution history: type selector placement

**Decision:** Add a Type selector (Workflows/Tasks/etc.) side-by-side with the search bar in execution history, with a proper label

**Reasoning:** Execution history covers multiple run types; a prominent inline selector reduces clicks to navigate to the right history type

### Task execution history: alert-based filter

**Decision:** Remove the workflow run filter from task execution history; replace with an alert dropdown filter (chaining: alert → analysis runs → workflow runs → task runs)

**Reasoning:** The workflow run filter did not work reliably; filtering by alert is more meaningful for users investigating specific incidents


## Findings Display

### Findings: Field display strategy

**Decision:** Show only enrichment fields in Findings, exclude metadata (trid, cy_name, status). Add Workbench link and task description subtitle

**Reasoning:** Enrichment fields are the predominant user-relevant data; metadata is redundant

### Findings: JSON rendering

**Decision:** Display enrichment JSON as direct k-v pairs in expanded table instead of nested expandable field

**Reasoning:** Better UX - shows relevant data immediately without extra clicks

### Findings: AI title display

**Decision:** Show ai_analysis_title field in Finding card header. Task name becomes subtitle, AI-generated title becomes primary heading

**Reasoning:** AI-generated titles are more descriptive and user-relevant than task names

### Findings: Header format

**Decision:** Always show task name first, then AI icon (sparkles) and arrow pointing to AI-generated title. Special handling for disposition and summary tasks

**Reasoning:** Consistent display pattern while accommodating task-specific field names


## Integrations UI

### Integration sidebar click behavior

**Decision:** Show details panel first (Recommended)

**Options considered:** Show details panel first (Recommended); Hover tooltip with details; Expandable accordion

**Reasoning:** Showing details on click gives users context before committing to a configuration action

### Integration action details scope

**Decision:** Both connectors and tools

**Options considered:** Connectors with descriptions; Tools with descriptions; Both connectors and tools

**Reasoning:** Listing only connectors or only tools was insufficient; users need visibility into all available action types in one view

### Integration preview: always centered modal

**Decision:** The integration preview/details panel always opens as a centered modal rather than inline

**Reasoning:** Inline display required scrolling to find the panel when an integration near the bottom was selected; modal always appears centered

### Integration View Details: show tools and connectors

**Decision:** The View Details modal for an integration must show both tools and connectors (not just overview metadata)

**Reasoning:** Users need to see exactly which tools and connectors are available for an integration in order to evaluate and use it

### Integration View Details: tab-based layout

**Decision:** Reorganize the View Details modal into a tab-based layout: Overview, Actions, Runs, Configuration

**Reasoning:** Tab-based organization is cleaner and allows content to be grouped logically without scrolling through one long panel

### Integration View Details: fixed modal size

**Decision:** The View Details modal size must be fixed and not resize when switching between tabs

**Reasoning:** Modal resizing on tab switch created a jarring, unstable UX; fixed size ensures consistent layout regardless of content length

### Integration Actions tab content

**Decision:** Remove quick actions from Overview tab; in Actions tab, list all available tools one-by-one with metadata; show at least the last 10 recent runs

**Reasoning:** Listing tools by count without names is not useful; users need to know exactly which tools are available

### Integration card: double-click opens View Details

**Status:** Reverted — current behavior is single-click (see "Integration sidebar click behavior" above). Kept here for history.

**Decision:** Double-clicking an integration card opens the View Details modal

**Reasoning:** Providing a double-click shortcut is more efficient than requiring users to find and click the View Details button


## Knowledge Graph

### Knowledge graph: node-centric exploration

**Decision:** Knowledge graph uses node-centric exploration: pick a starting node and show the graph N hops out, rather than displaying the entire graph at once

**Reasoning:** The full graph (136+ edges) was visually unusable; neighborhood exploration from a chosen node makes the graph navigable and meaningful

### Knowledge graph: click to re-center

**Decision:** Clicking a node in the knowledge graph allows the user to make it the new center node for exploration

**Reasoning:** Users need to navigate the graph dynamically; re-centering on any node enables natural graph traversal

### Knowledge graph: double-click suppresses search dropdown

**Decision:** On node double-click, populate the search bar but suppress the search dropdown that would otherwise re-open below it

**Reasoning:** Search bar population shows context; the dropdown re-opening after a direct selection is distracting and unnecessary

### Knowledge graph: double-click centers view

**Decision:** After a node double-click, automatically center the view on the selected node as the default behavior

**Reasoning:** Users expect double-click to navigate to that node; not centering left the selected node off-screen or buried among neighbors

### Knowledge graph: starts empty

**Decision:** Knowledge graph starts completely empty (no pre-selected starting node)

**Reasoning:** Rather than pre-loading a default node, the graph shows an empty state with a prompt to search; keeps the starting experience intentional

### Knowledge graph: starts empty (confirmed)

**Decision:** Knowledge graph starts completely empty with no default pre-loaded node

**Reasoning:** User confirmed: start empty for now, let users pick a node via search


## Knowledge Page

### Knowledge page: KU type filter

**Decision:** Add a type selector to the Knowledge page displayed side-by-side with the search bar, to filter which type of Knowledge Unit to view

**Reasoning:** Users need to narrow down KU display by type; inline filter next to search is a natural and consistent UX placement


## Skills Page

### Skills page: file tree from namespace field

**Decision:** Show skill files using their directory structure as defined by the namespace field, not a flat list

**Reasoning:** The namespace field encodes the hierarchical structure of skill files; a directory tree display matches how users think about skill organization

### Skills page: 'Selected Skill' label

**Decision:** Label the currently selected skill 'Selected Skill' rather than 'Active Skill'

**Reasoning:** 'Active' implies system state; 'Selected' better reflects the user's own selection action in the UI

### Skills extraction UX feedback

**Decision:** After clicking Extract, show a message that extraction may take several minutes; after approving an extraction, refresh the skill sidebar to show newly added files

**Reasoning:** Without a waiting message users may think extraction failed; without sidebar refresh the new file is not visible until a manual page reload


## Other

### Task and workflow listing action icons

**Decision:** Tasks listing: keep edit, add delete with confirmation modal. Workflows listing: icon-only [play][view][edit][delete] without text labels, with confirmation before deleting

**Reasoning:** Consistent icon treatment across listings; confirmation prevents accidental data loss; icon-only for workflows saves horizontal space

### Editable skills get visual indicator

**Decision:** Skills cards that allow UI data additions should have an extra icon/indicator to distinguish them from read-only skills

**Reasoning:** Makes it visually clear which skills support user contributions

