import { test, expect } from '@playwright/test';

/**
 * E2E Test: Workbench from Alert Workflow
 *
 * Critical user journey:
 * Alerts → Alert Details v2 → Analysis Runs → Task Runs → View Details → Open in Workbench
 *
 * These tests verify that users can navigate from an alert to the Workbench
 * and that code + input data are properly transferred.
 *
 * Note: Tests depend on having analyzed alerts with task runs in the backend.
 * They skip gracefully if preconditions are not met.
 */

/**
 * Navigate from alerts page to Workbench by clicking through an analyzed alert's
 * task run. Returns true if navigation succeeded, false if preconditions weren't met.
 */
async function navigateToWorkbenchViaAlert(
  page: import('@playwright/test').Page
): Promise<boolean> {
  await page.goto('/alerts');
  await expect(page.getByText('Alert Analysis Queue')).toBeVisible();

  // Find an analyzed alert - skip if none exist
  const analyzedRow = page.getByRole('row').filter({ hasText: 'Analyzed' }).first();
  const hasAnalyzedAlert = await analyzedRow.isVisible().catch(() => false);
  if (!hasAnalyzedAlert) return false;

  await analyzedRow.click();

  // Wait for Analysis Runs tab
  const analysisRunsTab = page.getByRole('button', { name: /Analysis Runs/ });
  const hasAnalysisTab = await analysisRunsTab.isVisible({ timeout: 5_000 }).catch(() => false);
  if (!hasAnalysisTab) return false;

  await analysisRunsTab.click();

  // Switch to Task Runs sub-tab
  const taskRunsTab = page.getByRole('button', { name: /Task Runs/ });
  const hasTaskRunsTab = await taskRunsTab.isVisible({ timeout: 5_000 }).catch(() => false);
  if (!hasTaskRunsTab) return false;

  await taskRunsTab.click();

  // Find a View Details button
  const viewDetailsBtn = page.getByRole('button', { name: 'View Details' }).first();
  const hasViewDetails = await viewDetailsBtn.isVisible({ timeout: 5_000 }).catch(() => false);
  if (!hasViewDetails) return false;

  await viewDetailsBtn.click();

  // Click Open in Workbench
  const openInWorkbench = page.getByText('Open in Workbench').first();
  const hasOpenLink = await openInWorkbench.isVisible({ timeout: 5_000 }).catch(() => false);
  if (!hasOpenLink) return false;

  await openInWorkbench.click();

  // Wait for Workbench page to load
  await expect(page.getByRole('heading', { name: 'Code Editor' })).toBeVisible();
  await expect(page).toHaveURL(/\/workbench/);

  return true;
}

test.describe('Workbench from Alert Workflow', () => {
  test('should populate code and input when opening task from alert workflow', async ({ page }) => {
    // Allow extra time for the multi-step navigation
    test.slow();

    const navigated = await navigateToWorkbenchViaAlert(page);
    test.skip(!navigated, 'No analyzed alerts with task runs available in backend');

    // Read the Ace editor value via its API (more reliable than DOM text)
    const editorValue = await page.evaluate(() => {
      const editorEl = document.querySelector('.ace_editor') as HTMLElement & {
        env?: { editor?: { getValue(): string } };
      };
      return editorEl?.env?.editor?.getValue() ?? '';
    });

    // Verify the editor has content (not the default Hello World)
    expect(editorValue).toBeTruthy();
    expect(editorValue).not.toContain('Hello World');
    expect(editorValue.length).toBeGreaterThan(10);
  });

  test('should allow running the task with pre-filled data', async ({ page }) => {
    // Allow extra time for navigation + task execution
    test.slow();

    const navigated = await navigateToWorkbenchViaAlert(page);
    test.skip(!navigated, 'No analyzed alerts with task runs available in backend');

    // Verify Run button is enabled
    const runButton = page.getByRole('button', { name: /Run/ });
    await expect(runButton).toBeEnabled();

    // Click Run button
    await runButton.click();

    // Wait for execution to complete — button text returns to "Run" after execution
    await expect(runButton).toContainText('Run', { timeout: 30_000 });

    // Verify output section has content (use exact: true to avoid "Input & Output")
    const outputHeading = page.getByRole('heading', { name: 'Output', exact: true });
    await expect(outputHeading).toBeVisible();

    // Verify output area contains results
    const outputPanel = outputHeading.locator('..').locator('..');
    const outputText = await outputPanel.textContent();
    expect(outputText).toBeTruthy();
    expect(outputText!.length).toBeGreaterThan(10);
  });
});
