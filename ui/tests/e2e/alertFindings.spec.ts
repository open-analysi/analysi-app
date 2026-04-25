import { test, expect } from '@playwright/test';

/**
 * E2E Tests: Alert Findings Tab
 *
 * Regression tests for the Findings tab on alert details pages.
 *
 * Regression: Findings were shown as "No findings available" even though enrichment
 * data existed in taskRun.output_location. The bug was:
 *   1. The /task-runs/{id}/enrichment endpoint always returned { enrichment: null }
 *   2. getEnrichmentData() returned null for null (typeof null === 'object' is true)
 *
 * Fix: fetchEnrichment() now reads enrichment from taskRun.output_location first,
 * extracting the last key in output.enrichments (task-specific contribution).
 *
 * Tests skip gracefully if backend has no analyzed alerts with task runs.
 */

// Run serially — tests share the discovered alert ID and rely on sequential navigation
test.describe.configure({ mode: 'serial' });

// Shared state for the describe block — discovered once via beforeAll
let sharedAlertId: string | null = null;

test.describe('Alert Findings Tab', () => {
  test.beforeAll(async ({ browser }) => {
    // Discover an analyzed alert ID once for all tests in this suite
    const page = await browser.newPage();
    try {
      await page.goto('/alerts');
      await page.getByText('Alert Analysis Queue').waitFor({ state: 'visible', timeout: 15_000 });

      const analyzedRow = page.getByRole('row').filter({ hasText: 'Analyzed' }).first();
      await analyzedRow.waitFor({ state: 'visible', timeout: 10_000 });

      await analyzedRow.click();
      await page.waitForURL(/\/alerts\/[^/]+/, { timeout: 15_000 });

      const url = page.url();
      sharedAlertId = url.split('/alerts/')[1]?.split('?')[0] ?? null;
    } catch {
      sharedAlertId = null;
    } finally {
      await page.close();
    }
  });

  test('should show enrichment data when expanding task run cards', async ({ page }) => {
    test.slow();
    test.skip(!sharedAlertId, 'No analyzed alerts available in backend');

    await page.goto(`/alerts/${sharedAlertId as string}?tab=findings`);
    await expect(page.getByText('Analysis Findings')).toBeVisible({ timeout: 15_000 });

    // Wait for task run cards to appear
    const firstCard = page.locator('button').filter({ hasText: 'completed' }).first();
    await firstCard.waitFor({ state: 'visible', timeout: 15_000 });

    // Click "Expand All" to open all cards at once
    const expandAllBtn = page.getByRole('button', { name: /Expand All/ });
    await expandAllBtn.waitFor({ state: 'visible', timeout: 10_000 });
    await expandAllBtn.click();

    // Give synchronous output_location parsing a moment to render
    await page.waitForTimeout(500);

    // Core regression assertion: "No findings available" must NOT appear
    await expect(page.getByText('No findings available')).not.toBeVisible();
  });

  test('should display enrichment key-value rows in an expanded card', async ({ page }) => {
    test.slow();
    test.skip(!sharedAlertId, 'No analyzed alerts available in backend');

    await page.goto(`/alerts/${sharedAlertId as string}?tab=findings`);
    await expect(page.getByText('Analysis Findings')).toBeVisible({ timeout: 15_000 });

    // Wait for the first succeeded card to appear
    const firstSucceededCard = page
      .locator('.bg-dark-800.border.border-gray-700.rounded-lg')
      .filter({ hasText: 'completed' })
      .first();
    await firstSucceededCard.waitFor({ state: 'visible', timeout: 10_000 });

    // Click the card header button to expand it
    await firstSucceededCard.locator('button').first().click();

    // Wait for enrichment rows to render (more reliable than a fixed delay)
    const enrichmentRows = firstSucceededCard.locator('.py-3.flex');
    await expect(enrichmentRows.first()).toBeVisible({ timeout: 5_000 });

    // Verify "No findings available" is NOT shown in the expanded card
    await expect(firstSucceededCard.getByText('No findings available')).not.toBeVisible();

    // Verify enrichment key-value rows are present
    const rowCount = await enrichmentRows.count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test('should load enrichment data from output_location without calling enrichment API', async ({
    page,
  }) => {
    test.slow();
    test.skip(!sharedAlertId, 'No analyzed alerts available in backend');

    // Track calls to /enrichment API endpoint — none should occur when
    // output_location is available (the fix avoids the extra round-trip)
    const enrichmentApiCalls: string[] = [];
    page.on('request', (req) => {
      if (req.resourceType() === 'fetch' || req.resourceType() === 'xhr') {
        if (req.url().includes('/enrichment')) {
          enrichmentApiCalls.push(req.url());
        }
      }
    });

    await page.goto(`/alerts/${sharedAlertId as string}?tab=findings`);
    await expect(page.getByText('Analysis Findings')).toBeVisible({ timeout: 15_000 });

    // Reset to only capture calls made after the page finishes loading
    enrichmentApiCalls.length = 0;

    // Wait for the Expand All button then click it
    const expandAllBtn = page.getByRole('button', { name: /Expand All/ });
    await expandAllBtn.waitFor({ state: 'visible', timeout: 10_000 });
    await expandAllBtn.click();
    await page.waitForTimeout(1_000);

    // The fix: enrichment is read from output_location synchronously — no
    // API calls to /enrichment should be made when output_location is populated
    expect(enrichmentApiCalls.length).toBe(0);
  });

  test('should navigate directly to findings tab via URL and show findings', async ({ page }) => {
    test.slow();
    test.skip(!sharedAlertId, 'No analyzed alerts available in backend');

    // Navigate directly via URL — this is how users share/bookmark the page
    await page.goto(`/alerts/${sharedAlertId as string}?tab=findings`);

    // Verify the findings section heading is visible
    await expect(page.getByText('Analysis Findings')).toBeVisible({ timeout: 15_000 });

    // Wait for the Expand All button and click it
    const expandAllBtn = page.getByRole('button', { name: /Expand All/ });
    await expandAllBtn.waitFor({ state: 'visible', timeout: 10_000 });
    await expandAllBtn.click();
    await page.waitForTimeout(500);

    // Core regression assertion: no "No findings available" text after expanding
    await expect(page.getByText('No findings available')).not.toBeVisible();
  });
});
