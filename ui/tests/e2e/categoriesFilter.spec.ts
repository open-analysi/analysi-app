import { test, expect, Page } from '@playwright/test';

/**
 * E2E Tests for Unified Categories Filter
 *
 * Verifies that:
 * - Category badges render on KU and Task rows
 * - The Categories dropdown opens and lists available categories
 * - Selecting a category filters the list via backend API
 * - Selected chips appear inline and can be removed
 * - The filter works on both Knowledge Units and Tasks pages
 */

const DROPDOWN_OPTIONS = '[role="group"] >> .overflow-y-auto';
const OPTION_SELECTOR = 'button[role="option"]';
/* eslint-disable sonarjs/slow-regex -- trivial regexes for count extraction in test */
const UNITS_COUNT_RE = /\d+ units/;
const TASKS_COUNT_RE = /\d+ tasks/;
const DIGITS_RE = /\d+/;
/* eslint-enable sonarjs/slow-regex */

/** Extract the numeric count from text like "400 units" or "34 tasks". */
function parseCount(text: string | null): number {
  return parseInt(text?.match(DIGITS_RE)?.[0] ?? '0', 10);
}

/** Wait for the table to finish loading (spinner gone, rows visible). */
async function waitForTableLoaded(page: Page) {
  // Wait for at least one data row or "no results" message
  await page
    .locator('table tbody tr')
    .first()
    .or(page.getByText('No results'))
    .waitFor({ timeout: 15_000 });
}

/** Open the Categories dropdown and return the name of the first available category. */
async function openDropdownAndGetFirstCategory(page: Page): Promise<string> {
  await page.getByRole('button', { name: /Categories/ }).click();
  const dropdown = page.locator(DROPDOWN_OPTIONS);
  const firstOption = dropdown.locator(OPTION_SELECTOR).first();
  await expect(firstOption).toBeVisible();
  const name = (await firstOption.locator('span').last().textContent())?.trim() ?? '';
  return name;
}

test.describe('Categories Filter — Knowledge Units', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/knowledge-units');
    await waitForTableLoaded(page);
  });

  test('should display category badges on KU rows', async ({ page }) => {
    // KU rows should have inline category badges in the description column.
    // Look for at least one badge with a known category value.
    const badges = page.locator('table tbody td span').filter({
      hasText: /^(app|feedback|raw|tool|investigation|siem|content_review|forensics)$/,
    });
    await expect(badges.first()).toBeVisible({ timeout: 10_000 });
  });

  test('should show Categories dropdown button', async ({ page }) => {
    const categoriesButton = page.getByRole('button', { name: /Categories/ });
    await expect(categoriesButton).toBeVisible();
  });

  test('should open dropdown with searchable category list', async ({ page }) => {
    // Open the dropdown
    await page.getByRole('button', { name: /Categories/ }).click();

    // Verify search input appears
    const searchInput = page.getByPlaceholder('Search categories...');
    await expect(searchInput).toBeVisible();

    // Verify category options are listed (scoped to the dropdown panel)
    const dropdown = page.locator(DROPDOWN_OPTIONS);
    const options = dropdown.locator(OPTION_SELECTOR);
    await expect(options.first()).toBeVisible();
    const optionCount = await options.count();
    expect(optionCount).toBeGreaterThan(0);
  });

  test('should filter categories in dropdown via search', async ({ page }) => {
    // Dynamically pick the first category from the dropdown
    const categoryName = await openDropdownAndGetFirstCategory(page);
    test.skip(!categoryName, 'No categories available');

    // Use the first 3 chars as a search prefix
    const searchPrefix = categoryName.slice(0, 3);
    const searchInput = page.getByPlaceholder('Search categories...');
    await searchInput.fill(searchPrefix);

    // The original category should still be visible after filtering
    const dropdown = page.locator(DROPDOWN_OPTIONS);
    await expect(dropdown.locator(OPTION_SELECTOR, { hasText: categoryName })).toBeVisible();

    // Search for something that doesn't exist
    await searchInput.fill('zzzznonexistent');
    await expect(page.getByText('No categories match')).toBeVisible();
  });

  test('should filter KU list when a category is selected', async ({ page }) => {
    // Get the initial total count
    const totalBefore = page.getByText(UNITS_COUNT_RE);
    await expect(totalBefore).toBeVisible();
    const totalTextBefore = await totalBefore.textContent();
    const countBefore = parseCount(totalTextBefore);

    // Open dropdown and select the first available category
    const categoryName = await openDropdownAndGetFirstCategory(page);
    test.skip(!categoryName, 'No categories available');

    const dropdown = page.locator(DROPDOWN_OPTIONS);
    await dropdown.locator(OPTION_SELECTOR, { hasText: categoryName }).click();

    // Wait for the list to update
    await page.waitForTimeout(1500);

    // Verify count changed (filtered items should be fewer than total)
    const totalAfter = page.getByText(UNITS_COUNT_RE);
    await expect(totalAfter).toBeVisible();
    const totalTextAfter = await totalAfter.textContent();
    const countAfter = parseCount(totalTextAfter);
    expect(countAfter).toBeLessThan(countBefore);
    expect(countAfter).toBeGreaterThan(0);

    // Verify a selected chip appears inline
    const selectedChip = page.getByRole('button', { name: `Remove ${categoryName} filter` });
    await expect(selectedChip).toBeVisible();
  });

  test('should remove filter when clicking selected chip', async ({ page }) => {
    // Get the initial total
    const initialText = await page.getByText(UNITS_COUNT_RE).textContent();
    const initialCount = parseCount(initialText);

    // Open dropdown and select the first available category
    const categoryName = await openDropdownAndGetFirstCategory(page);
    test.skip(!categoryName, 'No categories available');

    const dropdown = page.locator(DROPDOWN_OPTIONS);
    await dropdown.locator(OPTION_SELECTOR, { hasText: categoryName }).click();

    // Wait for the chip to appear (proves filter applied)
    const chip = page.getByRole('button', { name: `Remove ${categoryName} filter` });
    await expect(chip).toBeVisible({ timeout: 10_000 });

    // Click the chip to remove filter
    await chip.click();

    // Wait for count to restore to original
    await expect(page.getByText(`${initialCount} units`)).toBeVisible({ timeout: 10_000 });
  });
});

test.describe('Categories Filter — Tasks', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/tasks');
    await waitForTableLoaded(page);
  });

  test('should display category badges on Task rows', async ({ page }) => {
    const badges = page.locator('table tbody td span').filter({
      hasText: /^(extraction|processing|reasoning|enrichment|AI)$/,
    });
    await expect(badges.first()).toBeVisible({ timeout: 10_000 });
  });

  test('should show Categories dropdown and filter tasks', async ({ page }) => {
    const categoriesButton = page.getByRole('button', { name: /Categories/ });
    await expect(categoriesButton).toBeVisible();

    // Get initial count
    const totalBefore = page.getByText(TASKS_COUNT_RE);
    await expect(totalBefore).toBeVisible();
    const totalTextBefore = await totalBefore.textContent();
    const countBefore = parseCount(totalTextBefore);
    test.skip(countBefore === 0, 'No tasks in backend');

    // Open and select a category (scope to the dropdown panel)
    await categoriesButton.click();
    const dropdown = page.locator(DROPDOWN_OPTIONS);
    const firstOption = dropdown.locator(OPTION_SELECTOR).first();
    await expect(firstOption).toBeVisible();
    const categoryName = (await firstOption.locator('span').last().textContent())?.trim() ?? '';
    await firstOption.click();
    await page.waitForTimeout(1500);

    // Verify a selected chip appeared
    const selectedChip = page.getByRole('button', {
      name: `Remove ${categoryName} filter`,
    });
    await expect(selectedChip).toBeVisible();

    // Verify the Categories button shows the count badge
    const badge = page.getByRole('button', { name: /Categories/ }).locator('span');
    await expect(badge).toContainText('1');
  });

  test('should show categories in expanded task detail', async ({ page }) => {
    // Click a task row that has categories (e.g., one with visible category badges)
    const rowWithCategories = page
      .locator('table tbody tr')
      .filter({ hasText: /extraction|reasoning|enrichment/ })
      .first();
    test.skip(
      !(await rowWithCategories.isVisible().catch(() => false)),
      'No tasks with categories'
    );
    await rowWithCategories.click();

    // Wait for the expanded detail to render, then look for Categories section
    await expect(page.getByText('Categories:').first()).toBeVisible({ timeout: 10_000 });
  });
});
