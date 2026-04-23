/**
 * Analysi Platform — Cinematic Demo Script
 *
 * Records a ~2-minute guided tour of the platform, telling the story of
 * a security analyst's morning: triage alerts, investigate findings,
 * explore workflows, check execution history, browse knowledge, and
 * review integrations.
 *
 * See demo/README.md for usage instructions.
 */

import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Pause so the viewer can absorb what's on screen. */
const breathe = (page: Page, ms = 1200) => page.waitForTimeout(ms);

/** Navigate without waiting for networkidle (auto-refresh pages never settle). */
async function go(page: Page, path: string) {
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  // Give the page a moment to render API data
  await page.waitForTimeout(1500);
}

/** Move the mouse to an element before clicking — shows intent. */
async function hoverThenClick(page: Page, selector: string, opts?: { timeout?: number }) {
  const el = page.locator(selector).first();
  await el.waitFor({ state: 'visible', timeout: opts?.timeout ?? 8000 });
  await el.scrollIntoViewIfNeeded();
  const box = await el.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 12 });
    await page.waitForTimeout(300);
  }
  await el.click();
}

/** Hover over an element without clicking — draws attention. */
async function spotlight(page: Page, selector: string, dwell = 800) {
  const el = page.locator(selector).first();
  const visible = await el
    .waitFor({ state: 'visible', timeout: 3000 })
    .then(() => true)
    .catch(() => false);
  if (!visible) return;
  const box = await el.boundingBox();
  if (box) {
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 10 });
    await page.waitForTimeout(dwell);
  }
}

/** Slowly scroll down inside a container so the viewer sees content rolling by. */
async function smoothScroll(page: Page, selector: string, distance = 400, duration = 1500) {
  const el = page.locator(selector).first();
  const box = await el.boundingBox();
  if (!box) return;
  const steps = 30;
  const stepDelay = duration / steps;
  const stepDistance = distance / steps;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, stepDistance);
    await page.waitForTimeout(stepDelay);
  }
}

/** Check if a table has real data rows (not "No ... found" or "Loading"). */
async function tableHasData(page: Page): Promise<boolean> {
  const row = page.locator('table tbody tr').first();
  const visible = await row.isVisible().catch(() => false);
  if (!visible) return false;
  const text = await row.textContent();
  return !!text && !text.includes('No ') && !text.includes('Loading') && !text.includes('no ');
}

// ---------------------------------------------------------------------------
// Demo
// ---------------------------------------------------------------------------

test.describe('Analysi Platform Demo', () => {
  test('Full product walkthrough', async ({ page }) => {
    test.setTimeout(180_000); // 3 minutes

    // -----------------------------------------------------------------------
    // PROLOGUE — Login
    // -----------------------------------------------------------------------

    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);

    // If Keycloak login screen appears, authenticate
    const loginBtn = page.getByRole('button', { name: 'Login' });
    if (await loginBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await page.getByRole('textbox', { name: 'Username or email' }).fill('dev');
      await page.getByRole('textbox', { name: 'Password' }).fill('dev');
      await breathe(page, 600);
      await loginBtn.click();
      await page.waitForURL((url) => !url.pathname.includes('authentication'), { timeout: 20000 });
      await breathe(page, 2000);
    }

    // -----------------------------------------------------------------------
    // ACT 1 — The Alert Queue
    // -----------------------------------------------------------------------

    await go(page, '/alerts');
    await expect(page.getByText('Alert Analysis Queue')).toBeVisible({ timeout: 10000 });
    await breathe(page, 1500);

    // Hover over table header columns
    await spotlight(page, 'table thead tr', 800);

    if (await tableHasData(page)) {
      // Hover over first few alert rows
      await spotlight(page, 'table tbody tr:nth-child(1)', 600);
      await spotlight(page, 'table tbody tr:nth-child(2)', 600);
      await spotlight(page, 'table tbody tr:nth-child(3)', 600);
      await breathe(page, 600);

      // Scroll the alert table
      await smoothScroll(page, 'main', 300, 1500);
      await breathe(page, 800);
      await smoothScroll(page, 'main', -300, 800);
      await breathe(page, 500);
    } else {
      // Show the empty state and controls
      await spotlight(page, 'button:has-text("Refresh"), button:has-text("Filters")', 1000);
      await breathe(page);
    }

    // -----------------------------------------------------------------------
    // ACT 2 — Drill Into an Alert
    // -----------------------------------------------------------------------

    if (await tableHasData(page)) {
      await hoverThenClick(page, 'table tbody tr:first-child');
      await page.waitForURL(/\/alerts\/[^/]+/, { timeout: 10000 });
      await breathe(page, 2000);

      // Explore the header
      await spotlight(page, 'h1, h2', 1000);

      // Try each tab
      for (const tabName of ['findings', 'report', 'analysis', 'workflow']) {
        const tab = page.getByRole('tab', { name: new RegExp(tabName, 'i') });
        if (await tab.isVisible().catch(() => false)) {
          await tab.scrollIntoViewIfNeeded();
          const tabBox = await tab.boundingBox();
          if (tabBox) {
            await page.mouse.move(tabBox.x + tabBox.width / 2, tabBox.y + tabBox.height / 2, {
              steps: 10,
            });
            await page.waitForTimeout(200);
          }
          await tab.click();
          await breathe(page, 1800);
          await smoothScroll(page, 'main', 300, 1200);
          await breathe(page, 600);
        }
      }
    }

    // -----------------------------------------------------------------------
    // ACT 3 — Tasks
    // -----------------------------------------------------------------------

    await go(page, '/tasks');
    await breathe(page, 1500);
    await spotlight(page, 'table, main h1, main h2', 1000);

    if (await tableHasData(page)) {
      await spotlight(page, 'table tbody tr:nth-child(1)', 600);
      await spotlight(page, 'table tbody tr:nth-child(2)', 600);
      await smoothScroll(page, 'main', 250, 1200);
      await breathe(page, 800);
    }

    // -----------------------------------------------------------------------
    // ACT 4 — Workflows & the DAG Visualizer
    // -----------------------------------------------------------------------

    await go(page, '/workflows');
    await breathe(page, 1500);

    if (await tableHasData(page)) {
      await hoverThenClick(page, 'table tbody tr:first-child');
      await breathe(page, 2500);

      // Let the DAG render, then explore it
      await spotlight(page, 'svg, canvas, [class*="reaflow"], [class*="workflow"]', 1500);
      await breathe(page, 1500);

      await page.goBack();
      await breathe(page);
    }

    // -----------------------------------------------------------------------
    // ACT 5 — The Workbench
    // -----------------------------------------------------------------------

    await go(page, '/workbench?tab=execute');
    await breathe(page, 1500);

    // Show the code editor
    await spotlight(page, '[class*="ace_editor"], [class*="editor"], [class*="CodeEditor"]', 1200);
    await breathe(page);

    // Switch to the builder tab via sidebar or URL
    await go(page, '/workbench?tab=builder');
    await breathe(page, 2000);

    // Admire the workflow builder canvas
    await spotlight(page, 'svg, canvas, [class*="reaflow"], [class*="builder"], main', 1500);
    await breathe(page, 1500);

    // -----------------------------------------------------------------------
    // ACT 6 — Execution History
    // -----------------------------------------------------------------------

    await go(page, '/execution-history?view=tasks');
    await breathe(page, 1500);

    if (await tableHasData(page)) {
      await smoothScroll(page, 'main', 300, 1500);
      await breathe(page, 800);
    }

    // Switch to workflow runs
    await go(page, '/execution-history?view=workflows');
    await breathe(page, 1500);

    if (await tableHasData(page)) {
      // Try to expand a row
      const expandBtn = page.locator('table tbody tr:first-child button').first();
      if (await expandBtn.isVisible().catch(() => false)) {
        await hoverThenClick(page, 'table tbody tr:first-child button');
        await breathe(page, 2000);
      }
    }

    // -----------------------------------------------------------------------
    // ACT 7 — Knowledge Graph
    // -----------------------------------------------------------------------

    await go(page, '/knowledge-graph');
    await breathe(page, 2500);

    // Let the graph settle, then move mouse around to highlight nodes
    const graphContainer = page
      .locator('canvas, svg, [class*="cytoscape"], [class*="graph"], main')
      .first();
    const graphBox = await graphContainer.boundingBox().catch(() => null);
    if (graphBox) {
      const cx = graphBox.x + graphBox.width / 2;
      const cy = graphBox.y + graphBox.height / 2;
      const radius = Math.min(graphBox.width, graphBox.height) * 0.25;
      for (let angle = 0; angle < Math.PI * 2; angle += Math.PI / 10) {
        await page.mouse.move(cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius, {
          steps: 4,
        });
        await page.waitForTimeout(100);
      }
      await breathe(page, 1000);
    }

    // -----------------------------------------------------------------------
    // ACT 8 — Integrations
    // -----------------------------------------------------------------------

    await go(page, '/integrations');
    await breathe(page, 1800);

    // Scroll through integration cards/list
    await smoothScroll(page, 'main', 400, 2000);
    await breathe(page);

    // -----------------------------------------------------------------------
    // ACT 9 — Settings & Configuration
    // -----------------------------------------------------------------------

    await go(page, '/settings');
    await breathe(page, 1500);

    // Click into a settings section if available
    const settingsLink = page.locator('a[href*="section="]').first();
    if (await settingsLink.isVisible().catch(() => false)) {
      await hoverThenClick(page, 'a[href*="section="]');
      await breathe(page, 2000);
      await smoothScroll(page, 'main', 250, 1200);
      await breathe(page);
    }

    // -----------------------------------------------------------------------
    // FINALE — Back to Alerts
    // -----------------------------------------------------------------------

    await go(page, '/alerts');
    await breathe(page, 1500);

    // Final panoramic hover across the page
    await page.mouse.move(200, 450, { steps: 8 });
    await page.mouse.move(1200, 450, { steps: 30 });
    await breathe(page, 2000);
  });
});
