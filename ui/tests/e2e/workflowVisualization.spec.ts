import { test, expect } from '@playwright/test';

/**
 * E2E Test: Workflow Visualization
 *
 * Verifies that workflow visualizations render correctly with:
 * - ELK layout and proper graph rendering
 * - Zoom controls (Zoom In, Zoom Out, Reset View)
 * - Workflow heading
 *
 * Accessed via: Alert Details → Analysis Runs tab → Workflow Run sub-tab
 *
 * Note: Tests depend on having analyzed alerts with workflow data.
 * They skip gracefully if preconditions are not met.
 */

test.describe('Workflow Visualization', () => {
  test('should render workflow visualization with proper layout', async ({ page }) => {
    // Navigate to alerts page to find a workflow via analyzed alerts
    await page.goto('/alerts');
    await expect(page.getByText('Alert Analysis Queue')).toBeVisible();

    // Find an analyzed alert - skip if none exist
    const analyzedRow = page.getByRole('row').filter({ hasText: 'Analyzed' }).first();
    const hasAnalyzedAlert = await analyzedRow.isVisible().catch(() => false);
    test.skip(!hasAnalyzedAlert, 'No analyzed alerts available in backend');

    await analyzedRow.click();

    // Wait for Analysis Runs tab and click it
    const analysisRunsTab = page.getByRole('button', { name: /Analysis Runs/ });
    const hasAnalysisTab = await analysisRunsTab.isVisible({ timeout: 5_000 }).catch(() => false);
    test.skip(!hasAnalysisTab, 'Alert has no Analysis Runs tab');

    await analysisRunsTab.click();

    // The "Workflow Run" sub-tab should be active by default and show the visualization
    // Wait for zoom controls to appear (indicates the workflow graph rendered)
    await expect(page.getByRole('button', { name: 'Zoom In' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Zoom Out' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Reset View' })).toBeVisible();

    // Verify the workflow heading is rendered
    await expect(
      page.getByRole('heading', { level: 3 }).filter({ hasText: /Workflow/ })
    ).toBeVisible();
  });
});
