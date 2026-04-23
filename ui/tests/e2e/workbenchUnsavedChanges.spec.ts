import { test, expect, type Page } from '@playwright/test';

/**
 * E2E Test: Workbench Unsaved Changes Protection
 *
 * Verifies that the workbench shows a dialog when the user tries to:
 * 1. Navigate away via React Router links (sidebar) while the editor is dirty
 * 2. Reload the page using keyboard shortcuts (Cmd+R / Ctrl+R) while dirty
 *
 * The dialog offers: Save Changes / Save As New Task... / Discard Changes / Cancel
 */

const DIRTY_SCRIPT = 'result = {"hello": "world"}';
const DIALOG_HEADING = 'Unsaved Changes';

/**
 * Set content in the Ace editor via its JavaScript API.
 * This is more reliable than simulating typing, and it triggers the editor's
 * change event so the workbench picks up isDirty.
 */
async function setAceEditorContent(page: Page, content: string): Promise<void> {
  await page.locator('.ace_editor').waitFor({ timeout: 10_000 });
  await page.evaluate((script) => {
    const editorEl = document.querySelector('.ace_editor') as HTMLElement & {
      env?: { editor?: { setValue(val: string, cursorPos?: number): void } };
    };
    editorEl?.env?.editor?.setValue(script, -1);
  }, content);
}

/**
 * Click a sidebar nav link by its label text.
 * We use evaluate to find and click the element directly to ensure it fires
 * the React Router navigation (not a real anchor navigate).
 */
async function clickSidebarLink(page: Page, label: string): Promise<void> {
  await page.evaluate((linkLabel) => {
    const links = Array.from(document.querySelectorAll('aside a, aside [role="link"]'));
    const link = links.find((el) => el.textContent?.trim().includes(linkLabel));
    if (link) {
      (link as HTMLElement).click();
    }
  }, label);
}

test.describe('Workbench Unsaved Changes Protection', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/workbench?tab=execute');
    await expect(page.getByRole('heading', { name: 'Code Editor' })).toBeVisible({
      timeout: 15_000,
    });
  });

  // =============================================
  // Navigation Blocker Tests
  // =============================================

  test('shows unsaved changes dialog when navigating away with dirty editor', async ({ page }) => {
    // Make the editor dirty by typing some content
    await setAceEditorContent(page, DIRTY_SCRIPT);

    // Wait a tick for React state to update
    await page.waitForTimeout(300);

    // Click the Alerts sidebar link to trigger navigation
    await clickSidebarLink(page, 'Alerts');

    // The unsaved changes dialog should appear
    await expect(page.getByRole('heading', { name: DIALOG_HEADING })).toBeVisible({
      timeout: 5_000,
    });
    await expect(
      page.getByText('You have unsaved changes. What would you like to do?')
    ).toBeVisible();
  });

  test('Cancel on nav dialog keeps user on workbench', async ({ page }) => {
    await setAceEditorContent(page, DIRTY_SCRIPT);
    await page.waitForTimeout(300);

    await clickSidebarLink(page, 'Alerts');
    await expect(page.getByRole('heading', { name: DIALOG_HEADING })).toBeVisible({
      timeout: 5_000,
    });

    // Click Cancel
    await page.getByRole('button', { name: 'Cancel' }).click();

    // Dialog should close, user remains on workbench
    await expect(page.getByRole('heading', { name: DIALOG_HEADING })).not.toBeVisible({
      timeout: 3_000,
    });
    await expect(page).toHaveURL(/\/workbench/);
  });

  test('Discard Changes on nav dialog navigates away', async ({ page }) => {
    await setAceEditorContent(page, DIRTY_SCRIPT);
    await page.waitForTimeout(300);

    await clickSidebarLink(page, 'Alerts');
    await expect(page.getByRole('heading', { name: DIALOG_HEADING })).toBeVisible({
      timeout: 5_000,
    });

    // Click Discard Changes
    await page.getByRole('button', { name: 'Discard Changes' }).click();

    // Should navigate away from workbench
    await expect(page).not.toHaveURL(/\/workbench/, { timeout: 10_000 });
  });

  test('no dialog when editor is clean and user navigates away', async ({ page }) => {
    // Do not set any content — editor stays clean

    await clickSidebarLink(page, 'Alerts');

    // Dialog should NOT appear
    const dialogVisible = await page
      .getByRole('heading', { name: DIALOG_HEADING })
      .isVisible({ timeout: 2_000 })
      .catch(() => false);
    expect(dialogVisible).toBe(false);

    // Should navigate away immediately
    await expect(page).not.toHaveURL(/\/workbench/, { timeout: 10_000 });
  });

  test('shows all expected buttons in nav blocker dialog (no task selected = canSave false)', async ({
    page,
  }) => {
    await setAceEditorContent(page, DIRTY_SCRIPT);
    await page.waitForTimeout(300);

    await clickSidebarLink(page, 'Alerts');
    await expect(page.getByRole('heading', { name: DIALOG_HEADING })).toBeVisible({
      timeout: 5_000,
    });

    // In ad-hoc mode (no task selected), "Save Changes" should NOT appear
    await expect(page.getByRole('button', { name: 'Save Changes' })).not.toBeVisible();

    // These should always be present
    await expect(page.getByRole('button', { name: 'Save As New Task...' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Discard Changes' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
  });

  // =============================================
  // Reload Dialog Tests
  // =============================================

  test('shows reload dialog when Cmd+R is pressed with dirty editor', async ({ page }) => {
    await setAceEditorContent(page, DIRTY_SCRIPT);
    await page.waitForTimeout(300);

    // Press the platform reload shortcut (Meta+r on Mac)
    await page.keyboard.press('Meta+r');

    // The custom unsaved changes dialog should appear (not a browser reload)
    // Note: while the dialog is open, HeadlessUI hides background elements from a11y tree,
    // so we verify via the dialog heading + URL staying on workbench
    await expect(page.getByRole('heading', { name: DIALOG_HEADING })).toBeVisible({
      timeout: 5_000,
    });
    await expect(page).toHaveURL(/\/workbench/);
  });

  test('shows reload dialog when Ctrl+R is pressed with dirty editor', async ({ page }) => {
    await setAceEditorContent(page, DIRTY_SCRIPT);
    await page.waitForTimeout(300);

    await page.keyboard.press('Control+r');

    // The custom unsaved changes dialog should appear (not a browser reload)
    await expect(page.getByRole('heading', { name: DIALOG_HEADING })).toBeVisible({
      timeout: 5_000,
    });
    await expect(page).toHaveURL(/\/workbench/);
  });

  test('Cancel on reload dialog keeps user on workbench without reloading', async ({ page }) => {
    await setAceEditorContent(page, DIRTY_SCRIPT);
    await page.waitForTimeout(300);

    await page.keyboard.press('Meta+r');
    await expect(page.getByRole('heading', { name: DIALOG_HEADING })).toBeVisible({
      timeout: 5_000,
    });

    // Click Cancel
    await page.getByRole('button', { name: 'Cancel' }).click();

    // Dialog should close, workbench still showing
    await expect(page.getByRole('heading', { name: DIALOG_HEADING })).not.toBeVisible({
      timeout: 3_000,
    });
    await expect(page).toHaveURL(/\/workbench/);
    await expect(page.getByRole('heading', { name: 'Code Editor' })).toBeVisible();
  });

  test('Discard Changes on reload dialog reloads the page', async ({ page }) => {
    await setAceEditorContent(page, DIRTY_SCRIPT);
    await page.waitForTimeout(300);

    await page.keyboard.press('Meta+r');
    await expect(page.getByRole('heading', { name: DIALOG_HEADING })).toBeVisible({
      timeout: 5_000,
    });

    // Click Discard Changes and wait for the reload to complete
    // Using waitForURL instead of deprecated waitForNavigation
    await Promise.all([
      page.waitForURL('**/workbench**', { timeout: 10_000 }),
      page.getByRole('button', { name: 'Discard Changes' }).click(),
    ]);

    // After reload, workbench should be loaded and clean (not dirty)
    await expect(page.getByRole('heading', { name: 'Code Editor' })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page).toHaveURL(/\/workbench/);
  });

  test('no reload dialog when editor is clean and Cmd+R is pressed', async ({ page }) => {
    // Do not set any content — editor stays clean

    await page.keyboard.press('Meta+r');

    // The custom dialog should NOT appear when editor is clean
    // (Note: Playwright's keyboard.press sends JS key events, not native browser shortcuts,
    // so the browser won't actually reload — we just verify no dialog appears)
    const dialogVisible = await page
      .getByRole('heading', { name: DIALOG_HEADING })
      .isVisible({ timeout: 2_000 })
      .catch(() => false);
    expect(dialogVisible).toBe(false);

    // Workbench should still be loaded
    await expect(page.getByRole('heading', { name: 'Code Editor' })).toBeVisible();
  });
});
