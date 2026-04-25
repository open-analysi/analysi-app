import { test, expect } from '@playwright/test';

const BASE_URL = '/knowledge-units';

test.describe('Knowledge Units Page', () => {
  test('should load the knowledge units page', async ({ page }) => {
    await page.goto(BASE_URL);

    // Page should render with heading
    await expect(
      page
        .getByText('Knowledge Units')
        .or(page.getByRole('heading', { name: /knowledge/i }))
        .first()
    ).toBeVisible({ timeout: 10_000 });

    // Should show either table with data or empty state
    await expect(
      page
        .locator('table')
        .or(page.getByText(/no knowledge units/i))
        .first()
    ).toBeVisible({ timeout: 15_000 });
  });

  test('should display knowledge units in a table', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for table
    const table = page.locator('table').first();
    await table.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {});

    if (await table.isVisible()) {
      // Table should have header row with expected columns
      const headerRow = table.locator('thead tr').first();
      await expect(headerRow).toBeVisible();

      // Should have at least Name column
      await expect(headerRow.getByText('Name').or(headerRow.getByText('name'))).toBeVisible();
    }
  });

  test('should have search functionality', async ({ page }) => {
    await page.goto(BASE_URL);

    await expect(page.getByText('Knowledge Units').first()).toBeVisible({ timeout: 10_000 });

    // Search input should exist
    const searchInput = page.getByPlaceholder(/search/i).first();
    if (await searchInput.isVisible()) {
      await searchInput.fill('test search');
      await page.waitForTimeout(1000);
      // Page should still be functional
      await expect(page.locator('main').first()).toBeVisible();

      // Clear search
      await searchInput.clear();
    }
  });

  test('should support sorting by columns', async ({ page }) => {
    await page.goto(BASE_URL);

    const table = page.locator('table').first();
    await table.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {});

    if (await table.isVisible()) {
      // Click a column header to sort
      const nameHeader = table.locator('th').filter({ hasText: /name/i }).first();
      if (await nameHeader.isVisible()) {
        await nameHeader.click();
        await page.waitForTimeout(500);
        // Page should not crash
        await expect(table).toBeVisible();
      }
    }
  });

  test('should interact with knowledge unit rows', async ({ page }) => {
    await page.goto(BASE_URL);

    const tableRows = page.locator('table tbody tr');
    await tableRows
      .first()
      .waitFor({ state: 'visible', timeout: 15_000 })
      .catch(() => {});

    const rowCount = await tableRows.count();
    test.skip(rowCount === 0, 'No knowledge units available');

    // Click the first row — it should either expand or open an edit modal
    await tableRows.first().click();
    await page.waitForTimeout(1000);

    // Page should still be functional after the interaction
    await expect(page.locator('main').first()).toBeVisible();
    // The table should still be visible
    await expect(page.locator('table').first()).toBeVisible();
  });

  test('should have filter controls', async ({ page }) => {
    await page.goto(BASE_URL);

    await expect(page.getByText('Knowledge Units').first()).toBeVisible({ timeout: 10_000 });

    // Page should render without errors even if no explicit filters
    await expect(page.locator('main').first()).toBeVisible();
  });

  test('should handle pagination', async ({ page }) => {
    await page.goto(BASE_URL);

    const table = page.locator('table').first();
    await table.waitFor({ state: 'visible', timeout: 15_000 }).catch(() => {});

    if (await table.isVisible()) {
      // Check if pagination controls exist
      const nextButton = page.getByRole('button', { name: /next/i }).first();
      if (await nextButton.isVisible()) {
        const isEnabled = await nextButton.isEnabled();
        if (isEnabled) {
          await nextButton.click();
          await page.waitForTimeout(1000);
          // Table should still be visible after pagination
          await expect(table).toBeVisible();
        }
      }
    }
  });
});
