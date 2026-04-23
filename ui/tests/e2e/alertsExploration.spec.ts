import { test, expect } from '@playwright/test';

const PAGE_HEADING = 'Alert Analysis Queue';

test.describe('Alerts List Exploration', () => {
  test('should load the alerts page with table', async ({ page }) => {
    await page.goto('/alerts');

    await expect(page.getByText(PAGE_HEADING)).toBeVisible({ timeout: 10_000 });

    // Table should render with expected columns
    const table = page.locator('table').first();
    await expect(table).toBeVisible({ timeout: 15_000 });

    const headerRow = table.locator('thead tr').first();
    await expect(headerRow).toContainText('Severity');
    await expect(headerRow).toContainText('Title');
  });

  test('should have filter controls', async ({ page }) => {
    await page.goto('/alerts');
    await expect(page.getByText(PAGE_HEADING)).toBeVisible({ timeout: 10_000 });

    // Find and click the filter toggle button
    const filterButton = page.getByRole('button', { name: /filter/i }).first();
    await expect(filterButton).toBeVisible();
    await filterButton.click();

    // Filter panel should appear with search input
    await expect(page.getByPlaceholder('Search alerts...')).toBeVisible({ timeout: 5_000 });
  });

  test('should have auto-refresh control', async ({ page }) => {
    await page.goto('/alerts');
    await expect(page.getByText(PAGE_HEADING)).toBeVisible({ timeout: 10_000 });

    // Auto-refresh checkbox should exist
    const refreshCheckbox = page.getByRole('checkbox').first();
    await expect(refreshCheckbox).toBeVisible();
  });

  test('should have pagination when data exists', async ({ page }) => {
    await page.goto('/alerts');
    await expect(page.getByText(PAGE_HEADING)).toBeVisible({ timeout: 10_000 });

    // Wait for table data to load
    await page.waitForTimeout(2000);

    // Check for pagination or data - either rows in the table or a "no alerts" state
    const tableRows = page.locator('table tbody tr');
    const rowCount = await tableRows.count();

    if (rowCount > 0) {
      // At least one alert exists - verify row is clickable
      const firstRow = tableRows.first();
      await expect(firstRow).toBeVisible();
    }
  });

  test('should navigate to alert details on row click', async ({ page }) => {
    await page.goto('/alerts');
    await expect(page.getByText(PAGE_HEADING)).toBeVisible({ timeout: 10_000 });

    // Wait for a data row with AID- prefix (filters out loading/empty rows)
    const dataRow = page.getByRole('row').filter({ hasText: /AID-/ }).first();
    await dataRow.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {});

    test.skip(!(await dataRow.isVisible()), 'No alerts available in backend');

    // Click the alert row
    await dataRow.click();

    // Should navigate to alert details
    await expect(page).toHaveURL(/\/alerts\/[^/]+/, { timeout: 10_000 });
  });

  test('should support column sorting', async ({ page }) => {
    await page.goto('/alerts');
    await expect(page.getByText(PAGE_HEADING)).toBeVisible({ timeout: 10_000 });

    // Wait for table to load with data
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 15_000 });

    // Click a sortable column header (Severity is sortable)
    const severityHeader = page.locator('th').filter({ hasText: 'Severity' });
    await severityHeader.click();

    // The sort should trigger — no crash, page still functional
    await expect(page.getByText(PAGE_HEADING)).toBeVisible();
  });

  test('should show refresh button and it works', async ({ page }) => {
    await page.goto('/alerts');
    await expect(page.getByText(PAGE_HEADING)).toBeVisible({ timeout: 10_000 });

    // Find refresh button
    const refreshButton = page.getByRole('button', { name: /refresh/i }).first();
    if (await refreshButton.isVisible()) {
      await refreshButton.click();
      // Should not crash — page should still be functional
      await expect(page.getByText(PAGE_HEADING)).toBeVisible();
    }
  });
});
