# Analysi Platform Demo

Automated, scripted product walkthrough recorded with Playwright. Produces a
~90-second MP4 video touring every major section of the platform.

## What the demo covers

| Act      | Page              | Highlights                                            |
| -------- | ----------------- | ----------------------------------------------------- |
| Prologue | Login             | Keycloak authentication (skipped if auth is disabled) |
| 1        | Alerts            | Queue table, severity badges, sorting columns         |
| 2        | Alert Details     | Tabs: findings, report, analysis, workflow tasks      |
| 3        | Tasks             | Task definitions list                                 |
| 4        | Workflows         | DAG visualizer with zoom/pan                          |
| 5        | Workbench         | Code editor (Execute) and workflow builder canvas     |
| 6        | Execution History | Task runs, workflow runs with expandable rows         |
| 7        | Knowledge Graph   | Interactive node graph with cursor exploration        |
| 8        | Integrations      | Connected services grid                               |
| 9        | Settings          | Configuration cards and drill-down                    |

The script is resilient to empty data — if a section has no records, it
gracefully shows the empty state and moves on.

## Prerequisites

- Dev server running at `http://localhost:5173` (`npm run dev`)
- Backend API running at `http://localhost:8001`
- Keycloak at `http://localhost:8080` (or auth disabled via `VITE_DISABLE_AUTH=true`)
- [ffmpeg](https://ffmpeg.org/) installed (for WebM → MP4 conversion)

## Quick start

```bash
# Record headless (saves WebM, then convert to MP4)
npm run demo:record
npm run demo:mp4

# Watch live in a headed browser
npm run demo
```

## Manual conversion

If you prefer to convert manually or tweak ffmpeg settings:

```bash
# Find the WebM
ls test-results/demo*/video.webm

# Convert — adjust crf (quality: lower = better, 18-23 is good) and preset
ffmpeg -i test-results/demo*/video.webm \
  -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p \
  demo/demo.mp4
```

## Customizing the demo

### Pacing

The Playwright config (`demo/playwright.config.ts`) sets `slowMo: 40` for
natural-feeling interactions. Increase for a slower, more deliberate feel;
decrease for a snappier recording.

### Resolution

Default is 1440x900. Change `viewport` and `video.size` in the config:

```ts
viewport: { width: 1920, height: 1080 },
video: { mode: 'on', size: { width: 1920, height: 1080 } },
```

### Adding scenes

Edit `demo/demo.ts`. Each act follows the same pattern:

```ts
// Navigate
await go(page, '/your-page');
await breathe(page, 1500);

// Interact
await spotlight(page, 'selector', 800); // hover to draw attention
await hoverThenClick(page, 'selector'); // glide cursor, then click
await smoothScroll(page, 'main', 300); // cinematic scroll
await breathe(page); // pause for the viewer
```

### Helper functions

| Helper                               | Purpose                                                                  |
| ------------------------------------ | ------------------------------------------------------------------------ |
| `breathe(page, ms)`                  | Pause so the viewer can absorb the screen                                |
| `go(page, path)`                     | Navigate without waiting for `networkidle` (safe for auto-refresh pages) |
| `hoverThenClick(page, sel)`          | Glide cursor to element center, pause, click                             |
| `spotlight(page, sel, ms)`           | Hover without clicking — draws visual attention                          |
| `smoothScroll(page, sel, dist, dur)` | Slow scroll inside a container                                           |
| `tableHasData(page)`                 | Check if a table has real rows (not empty/loading state)                 |

## Files

```
demo/
  README.md              ← this file
  demo.ts                ← Playwright test script (the walkthrough)
  playwright.config.ts   ← Playwright config (resolution, video, slowMo)
  demo.mp4               ← generated output (git-ignored)
```
