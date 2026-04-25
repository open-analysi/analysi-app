import { test, expect } from '@playwright/test';

test.describe('Settings Page', () => {
  test('should load settings card grid', async ({ page }) => {
    await page.goto('/settings');

    await expect(page.getByRole('heading', { name: 'Settings' }).first()).toBeVisible({
      timeout: 10_000,
    });

    // All 3 section cards visible (use role=button to target the cards, not description text)
    await expect(page.getByRole('button', { name: /Analysis Groups/i }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Alert Routing Rules/i }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Event Reaction Rules/i }).first()).toBeVisible();
  });

  test('should navigate to Analysis Groups and back', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Settings' }).first()).toBeVisible({
      timeout: 10_000,
    });

    // Click Analysis Groups card
    await page
      .getByRole('button', { name: /Analysis Groups/i })
      .first()
      .click();
    await expect(page).toHaveURL(/section=analysis-groups/);

    // Section heading should appear
    await expect(page.getByRole('heading', { name: 'Analysis Groups' })).toBeVisible({
      timeout: 15_000,
    });

    // Navigate back
    await page.getByLabel('Back to Settings').click();
    await expect(page).not.toHaveURL(/section=/);
    await expect(page.getByRole('heading', { name: 'Settings' }).first()).toBeVisible();
  });

  test('should navigate to Alert Routing Rules', async ({ page }) => {
    await page.goto('/settings?section=alert-routing');

    // Should show alert routing content
    await expect(
      page.getByText('Alert Routing Rules').or(page.getByText('Loading')).first()
    ).toBeVisible({ timeout: 10_000 });

    // Wait for data to load - should see either table with rules or empty state
    await expect(
      page.locator('table').or(page.getByText('No routing rules')).or(page.getByText('Loading'))
    ).toBeVisible({ timeout: 15_000 });
  });

  test('should navigate to Event Reaction Rules section with tabs', async ({ page }) => {
    await page.goto('/settings?section=control-events');

    // Sub-tabs should be visible (use button role for the tabs)
    await expect(page.getByRole('button', { name: 'Reaction Rules' })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByRole('button', { name: 'Control Events' })).toBeVisible();

    // Default tab is rules — heading appears inside the rules component
    await expect(page.getByRole('heading', { name: 'Event Reaction Rules' })).toBeVisible({
      timeout: 15_000,
    });

    // Switch to history tab
    await page.getByRole('button', { name: 'Control Events' }).click();
    await expect(page).toHaveURL(/tab=history/);

    // History content should load — Fire Test Event collapsible panel
    await expect(page.getByRole('button', { name: /Fire Test Event/i })).toBeVisible({
      timeout: 15_000,
    });

    // Switch back to rules
    await page.getByRole('button', { name: 'Reaction Rules' }).click();
    // 'rules' is the default tab, so it may not appear in URL
    await expect(page.getByRole('heading', { name: 'Event Reaction Rules' })).toBeVisible({
      timeout: 10_000,
    });
  });

  test('should show Event Reaction Rules table with actions', async ({ page }) => {
    await page.goto('/settings?section=control-events&tab=rules');

    // Wait for rules to load
    await expect(
      page.getByText('No reaction rules yet.').or(page.locator('table').first())
    ).toBeVisible({ timeout: 15_000 });

    // Action buttons should be present
    await expect(page.getByRole('button', { name: /refresh/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /new rule/i })).toBeVisible();
  });

  test('should open and close the create rule form', async ({ page }) => {
    await page.goto('/settings?section=control-events&tab=rules');

    // Wait for data to load
    await expect(
      page.getByText('No reaction rules yet.').or(page.getByRole('button', { name: /new rule/i }))
    ).toBeVisible({ timeout: 15_000 });

    // Open create form
    await page.getByRole('button', { name: /new rule/i }).click();
    await expect(page.getByText('Create New Rule')).toBeVisible();

    // Form fields should be visible
    await expect(page.getByLabel('Name')).toBeVisible();
    await expect(page.getByLabel('Channel')).toBeVisible();

    // Cancel closes the form
    await page.getByRole('button', { name: /cancel/i }).click();
    await expect(page.getByText('Create New Rule')).not.toBeVisible();
  });

  test('should show Event History with filters and test panel', async ({ page }) => {
    await page.goto('/settings?section=control-events&tab=history');

    // Wait for history to load — use the table directly since both table and "No events found"
    // cell can be visible simultaneously (the cell is inside the table), causing strict mode violation
    await expect(page.locator('table').first()).toBeVisible({
      timeout: 15_000,
    });

    // Filter dropdowns should exist — use locator for select elements
    await expect(page.locator('select').first()).toBeVisible();

    // Expand the Fire Test Event panel
    const fireTestToggle = page.getByText('Fire Test Event');
    await expect(fireTestToggle).toBeVisible();
    await fireTestToggle.click();

    const fireButton = page.getByRole('button', { name: /fire event/i });
    await expect(fireButton).toBeVisible({ timeout: 10_000 });

    // Fire button should be disabled without a channel
    await expect(fireButton).toBeDisabled();
  });
});
