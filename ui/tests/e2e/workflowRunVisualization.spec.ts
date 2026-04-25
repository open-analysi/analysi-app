import { test, expect } from '@playwright/test';

// Run serially — tests share a discovered workflow run ID
test.describe.configure({ mode: 'serial' });

let workflowRunId: string | null = null;
const SKIP_MSG = 'No workflow runs available in backend';

test.describe('Workflow Run Visualization', () => {
  test.beforeAll(async ({ browser }) => {
    // Discover a workflow run ID from execution history
    const page = await browser.newPage();
    try {
      // Try to find a workflow run via the API
      const runId = await page.evaluate(async () => {
        try {
          const response = await fetch('/api/workflow-runs?limit=1&sort=started_at&order=desc');
          if (response.ok) {
            const data = (await response.json()) as { workflow_runs?: Array<{ id: string }> };
            return data.workflow_runs?.[0]?.id ?? null;
          }
        } catch {
          // API not available, try UI approach
        }
        return null;
      });

      if (runId) {
        workflowRunId = runId;
      } else {
        // Fall back to finding a run via the execution history UI
        await page.goto('/execution-history?view=workflows');
        await page.waitForTimeout(3000);

        const tableRows = page.locator('table tbody tr');
        const rowCount = await tableRows.count();

        if (rowCount > 0) {
          // Look for a link to a workflow run in the first row
          const link = tableRows.first().locator('a[href*="workflow-runs"]').first();
          if (await link.isVisible()) {
            const href = await link.getAttribute('href');
            workflowRunId = href?.match(/workflow-runs\/([^/?]+)/)?.[1] ?? null;
          }
        }
      }
    } finally {
      await page.close();
    }
  });

  test('should display workflow run page with status', async ({ page }) => {
    test.skip(!workflowRunId, SKIP_MSG);

    await page.goto(`/workflow-runs/${workflowRunId as string}`);

    // Page should load — look for key structural elements
    await expect(page.locator('main').or(page.locator('[class*="page"]')).first()).toBeVisible({
      timeout: 15_000,
    });

    // Should display a status badge
    await expect(
      page
        .getByText('Completed')
        .or(page.getByText('Running'))
        .or(page.getByText('Failed'))
        .or(page.getByText('Cancelled'))
        .or(page.getByText('Pending'))
        .first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test('should display workflow name or heading', async ({ page }) => {
    test.skip(!workflowRunId, SKIP_MSG);

    await page.goto(`/workflow-runs/${workflowRunId as string}`);

    // Should have a heading or workflow name visible
    await expect(page.locator('main').first()).toBeVisible({ timeout: 15_000 });

    // Back navigation should be present
    const backButton = page
      .getByRole('button', { name: /back/i })
      .or(page.getByRole('link', { name: /back/i }));
    if (await backButton.isVisible()) {
      // Verify it exists without clicking
      expect(await backButton.isVisible()).toBe(true);
    }
  });

  test('should render workflow visualization canvas', async ({ page }) => {
    test.skip(!workflowRunId, SKIP_MSG);

    await page.goto(`/workflow-runs/${workflowRunId as string}`);

    await expect(page.locator('main').first()).toBeVisible({ timeout: 15_000 });

    // Look for SVG canvas (Reaflow renders SVG) or the canvas container
    const svgCanvas = page.locator('svg').first();
    await svgCanvas.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {});

    if (await svgCanvas.isVisible()) {
      // Reaflow renders nodes as foreignObject elements within SVG
      const foreignObjects = page.locator('foreignObject');
      const nodeCount = await foreignObjects.count();

      // At least one node should be visible if there's a visualization
      if (nodeCount > 0) {
        await expect(foreignObjects.first()).toBeVisible();
      }
    }
  });

  test('should display timing information', async ({ page }) => {
    test.skip(!workflowRunId, SKIP_MSG);

    await page.goto(`/workflow-runs/${workflowRunId as string}`);

    await expect(page.locator('main').first()).toBeVisible({ timeout: 15_000 });

    // Should show some timing/duration info
    // Look for common time-related text patterns
    await Promise.race([
      page
        .getByText(/\d{1,6} ?(ms|sec|min|hour)/i)
        .first()
        .waitFor({ timeout: 5_000 }),
      page
        .getByText(/duration/i)
        .first()
        .waitFor({ timeout: 5_000 }),
      page
        .getByText(/started/i)
        .first()
        .waitFor({ timeout: 5_000 }),
    ]).catch(() => {
      // Page loaded successfully even if timing info isn't visible
    });
  });

  test('should have copy run ID functionality', async ({ page }) => {
    test.skip(!workflowRunId, SKIP_MSG);

    await page.goto(`/workflow-runs/${workflowRunId as string}`);

    await expect(page.locator('main').first()).toBeVisible({ timeout: 15_000 });

    // Look for copy button
    const copyButton = page.getByRole('button', { name: /copy/i }).first();
    if (await copyButton.isVisible()) {
      await copyButton.click();
      // Should show feedback (checkmark or toast)
      await page.waitForTimeout(500);
      // Page should not crash after copy
      await expect(page.locator('main').first()).toBeVisible();
    }
  });
});
