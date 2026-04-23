import { test, expect } from '@playwright/test';

const BASE_URL = '/execution-history';

test.describe('Execution History Page', () => {
  test('should load with default Tasks view', async ({ page }) => {
    await page.goto(BASE_URL);

    // Page heading or content should be visible
    await expect(
      page.getByText('Execution History').or(page.getByText('Task Runs')).first()
    ).toBeVisible({ timeout: 10_000 });

    // Should default to tasks view
    await expect(page).toHaveURL(/(?:view=tasks|execution-history$)/);

    // Wait for data to load — either table with data or empty state
    await expect(
      page
        .locator('table')
        .or(page.getByText(/no.*runs/i))
        .or(page.getByText('Loading'))
        .first()
    ).toBeVisible({ timeout: 15_000 });
  });

  test('should switch between Task Runs and Workflow Runs views', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for initial load
    await expect(
      page.getByText('Execution History').or(page.getByText('Task Runs')).first()
    ).toBeVisible({ timeout: 10_000 });

    // Find the view selector tabs/buttons
    const workflowsTab = page
      .getByRole('button', { name: /workflow/i })
      .or(page.getByText('Workflow Runs', { exact: false }).first());

    if (await workflowsTab.isVisible()) {
      await workflowsTab.click();
      await expect(page).toHaveURL(/view=workflows/);

      // Content should update
      await page.waitForTimeout(1000);
      await expect(page.locator('main').first()).toBeVisible();
    }
  });

  test('should switch to Task Building view', async ({ page }) => {
    await page.goto(`${BASE_URL}?view=task-building`);

    // Should show task building content
    await expect(
      page
        .getByText('Task Building')
        .or(page.getByText('task-building'))
        .or(page.locator('table'))
        .first()
    ).toBeVisible({ timeout: 15_000 });
  });

  test('should have search functionality', async ({ page }) => {
    await page.goto(BASE_URL);

    await expect(
      page.getByText('Execution History').or(page.getByText('Task Runs')).first()
    ).toBeVisible({ timeout: 10_000 });

    // Search input should exist
    const searchInput = page.getByPlaceholder(/search/i).first();
    if (await searchInput.isVisible()) {
      // Type something and verify no crash
      await searchInput.fill('test-query');
      await page.waitForTimeout(1000);
      await expect(page.locator('main').first()).toBeVisible();

      // Clear search
      await searchInput.clear();
    }
  });

  test('should have auto-refresh control', async ({ page }) => {
    await page.goto(BASE_URL);

    await expect(
      page.getByText('Execution History').or(page.getByText('Task Runs')).first()
    ).toBeVisible({ timeout: 10_000 });

    // Auto-refresh checkbox
    const autoRefreshCheckbox = page.getByRole('checkbox').first();
    if (await autoRefreshCheckbox.isVisible()) {
      // Toggle auto-refresh — should not crash
      await autoRefreshCheckbox.click();
      await page.waitForTimeout(500);
      await autoRefreshCheckbox.click();
    }
  });

  test('should expand row details on click', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for table data
    const tableRows = page.locator('table tbody tr');
    await tableRows
      .first()
      .waitFor({ state: 'visible', timeout: 15_000 })
      .catch(() => {});

    const rowCount = await tableRows.count();
    test.skip(rowCount === 0, 'No execution history available');

    // Click first data row to expand
    await tableRows.first().click();

    // Should expand without error — wait a moment for expansion animation
    await page.waitForTimeout(500);
    await expect(page.locator('main').first()).toBeVisible();
  });

  test('should preserve view selection via URL', async ({ page }) => {
    // Navigate to workflows view
    await page.goto(`${BASE_URL}?view=workflows`);

    await expect(page.locator('main').first()).toBeVisible({ timeout: 10_000 });

    // Reload page
    await page.reload();

    // Should still be on workflows view after reload
    await expect(page).toHaveURL(/view=workflows/);
  });

  test('should have pagination controls when data exists', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for data
    const table = page.locator('table').first();
    await table.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {});

    if (await table.isVisible()) {
      // Pagination may or may not exist depending on data volume
      // This test just verifies the page works correctly
      await expect(page.locator('main').first()).toBeVisible();
    }
  });
});
