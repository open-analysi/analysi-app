import { test, expect } from '@playwright/test';

/**
 * E2E Test: Integrations Page & Configuration Wizard
 *
 * Tests the full integration lifecycle using Global DNS (no API keys required):
 * 1. Verify the Integrations page loads with available and configured sections
 * 2. Search/filter integrations in the available catalog
 * 3. Configure a new Global DNS integration via the 4-step wizard
 * 4. Verify the new integration appears in "Your Integrations"
 * 5. Delete the integration and verify cleanup
 *
 * Global DNS is used because it requires no credentials, making this test
 * safe to run in any environment.
 */

// Unique suffix to avoid name collisions across test runs
const TEST_ID = Date.now().toString(36);
const INTEGRATION_NAME = `E2E DNS ${TEST_ID}`;

// Constants to avoid duplicate strings and hardcoded-IP lint warnings
const GLOBAL_DNS = 'Global DNS';
// eslint-disable-next-line sonarjs/no-hardcoded-ip -- public DNS server used as default in UI
const DNS_SERVER_IP = '8.8.8.8';

test.describe('Integrations Page', () => {
  test('should load with available integrations catalog and configured cards', async ({ page }) => {
    await page.goto('/integrations');

    // Wait for page to load — both sections should be visible
    await expect(page.getByRole('heading', { name: 'Available Integrations' })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByRole('heading', { name: 'Your Integrations' })).toBeVisible();

    // Should show configured count (e.g., "10 of 39 configured")
    await expect(page.getByText(/\d{1,3} of \d{1,3} configured/)).toBeVisible();

    // Should have at least one configured integration card with "View Details" button
    await expect(page.getByRole('button', { name: 'View Details' }).first()).toBeVisible();

    // Global DNS should appear in the available integrations catalog
    await expect(
      page.getByRole('button', { name: /Global DNS.*DNS.*action/ }).first()
    ).toBeVisible();
  });

  test('should filter available integrations via search', async ({ page }) => {
    await page.goto('/integrations');
    await expect(page.getByRole('heading', { name: 'Available Integrations' })).toBeVisible({
      timeout: 10_000,
    });

    // Search for "Global DNS"
    const searchInput = page.getByPlaceholder('Search integrations...');
    await expect(searchInput).toBeVisible();
    await searchInput.fill(GLOBAL_DNS);

    // Global DNS should be visible
    await expect(page.getByRole('button', { name: /Global DNS.*DNS/ }).first()).toBeVisible();

    // Unrelated integrations should be filtered out (e.g., Splunk)
    await expect(page.getByRole('button', { name: /Splunk Enterprise.*SIEM/ })).not.toBeVisible({
      timeout: 2_000,
    });

    // Clear the search
    await searchInput.clear();

    // Splunk should be visible again
    await expect(
      page.getByRole('button', { name: /Splunk Enterprise.*SIEM/ }).first()
    ).toBeVisible();
  });

  test('should open integration detail panel with tools and connectors', async ({ page }) => {
    await page.goto('/integrations');
    await expect(page.getByRole('heading', { name: 'Available Integrations' })).toBeVisible({
      timeout: 10_000,
    });

    // Click Global DNS in the catalog
    await page
      .getByRole('button', { name: /Global DNS.*DNS.*action/ })
      .first()
      .click();

    // Detail panel should show integration info
    await expect(page.getByRole('heading', { name: GLOBAL_DNS, level: 2 })).toBeVisible({
      timeout: 5_000,
    });

    // Should show actions section with action names
    await expect(page.getByRole('heading', { name: /Actions/ })).toBeVisible();
    await expect(page.getByText('Health Check')).toBeVisible();
    await expect(page.getByText('Resolve Domain', { exact: true })).toBeVisible();
    await expect(page.getByText('Reverse DNS Lookup', { exact: true })).toBeVisible();

    // Should have "Configure Integration" button
    await expect(page.getByRole('button', { name: 'Configure Integration' })).toBeVisible();

    // Close the panel
    await page.getByRole('button', { name: '×' }).click();
    await expect(page.getByRole('heading', { name: GLOBAL_DNS, level: 2 })).not.toBeVisible({
      timeout: 3_000,
    });
  });
});

test.describe('Integration Configuration Lifecycle', () => {
  // Give extra time for the multi-step wizard + API calls
  test.setTimeout(90_000);

  // Unique integration_id per test run to avoid collisions with stale data
  const INTEGRATION_ID = `global-dns-e2e-${TEST_ID}`;

  test(`configure ${GLOBAL_DNS} → verify → delete`, async ({ page }) => {
    test.slow();

    // =============================================
    // CLEANUP: Delete stale integration from previous failed runs
    // =============================================
    await test.step('Clean up stale E2E integration if present', async () => {
      // Try to delete via API — ignore errors if it doesn't exist
      await page.request.delete(`/api/v1/default/integrations/${INTEGRATION_ID}`).catch(() => {});
    });

    // =============================================
    // STEP 1: Navigate and open the wizard
    // =============================================
    await test.step(`Open configuration wizard for ${GLOBAL_DNS}`, async () => {
      await page.goto('/integrations');
      await expect(page.getByRole('heading', { name: 'Available Integrations' })).toBeVisible({
        timeout: 10_000,
      });

      // Click Global DNS in the catalog
      await page
        .getByRole('button', { name: /Global DNS.*DNS.*action/ })
        .first()
        .click();

      // Wait for detail panel
      await expect(page.getByRole('heading', { name: GLOBAL_DNS, level: 2 })).toBeVisible({
        timeout: 5_000,
      });

      // Click Configure Integration
      await page.getByRole('button', { name: 'Configure Integration' }).click();

      // Wizard should open with "Setup Global DNS" heading
      await expect(page.getByRole('heading', { name: `Setup ${GLOBAL_DNS}` })).toBeVisible({
        timeout: 5_000,
      });
    });

    // =============================================
    // STEP 2: Fill in Integration details (Step 1 of 4)
    // =============================================
    await test.step('Fill integration details (Step 1: Integration)', async () => {
      // Verify we're on step 1
      await expect(page.getByText('Integration Name')).toBeVisible();

      // Fill in the name
      const nameInput = page.getByRole('textbox', { name: 'Integration Name *' });
      await expect(nameInput).toBeVisible();
      await nameInput.fill(INTEGRATION_NAME);

      // Fill description
      const descInput = page.getByRole('textbox', { name: 'Description' });
      await descInput.fill(`E2E test integration created at ${new Date().toISOString()}`);

      // Set a unique integration_id to avoid collisions with existing integrations
      const idInput = page.getByRole('textbox', { name: /global-dns/ });
      await idInput.clear();
      await idInput.fill(INTEGRATION_ID);

      // Verify DNS Server default is present
      await expect(page.getByRole('textbox', { name: DNS_SERVER_IP })).toBeVisible();

      // Click Next
      await page.getByRole('button', { name: 'Next: Credentials' }).click();
    });

    // =============================================
    // STEP 3: Credentials (Step 2 of 4) — skip, all optional for DNS
    // =============================================
    await test.step('Skip credentials (Step 2: Credentials)', async () => {
      // Verify we're on the credentials step
      await expect(page.getByRole('heading', { name: 'Credentials' })).toBeVisible({
        timeout: 5_000,
      });

      // Should indicate credentials are optional
      await expect(page.getByText(/optional/i)).toBeVisible();

      // Click Next without adding credentials
      await page.getByRole('button', { name: 'Next: Schedules' }).click();
    });

    // =============================================
    // STEP 4: Schedules (Step 3 of 4) — skip
    // =============================================
    await test.step('Skip schedules (Step 3: Schedules)', async () => {
      // Verify we're on the schedules step
      await expect(page.getByRole('heading', { name: 'Configure Schedules' })).toBeVisible({
        timeout: 5_000,
      });

      // Health Check connector should be listed
      await expect(page.getByRole('heading', { name: 'Health Check', level: 4 })).toBeVisible();

      // Click Review
      await page.getByRole('button', { name: 'Review Setup' }).click();
    });

    // =============================================
    // STEP 5: Review and Complete (Step 4 of 4)
    // =============================================
    await test.step('Review and complete setup (Step 4: Review)', async () => {
      // Verify we're on the review step
      await expect(page.getByRole('heading', { name: 'Review Configuration' })).toBeVisible({
        timeout: 5_000,
      });

      // Verify our name is shown in the review
      await expect(page.getByText(INTEGRATION_NAME)).toBeVisible();

      // Verify type is shown in the review details
      await expect(page.getByRole('paragraph').filter({ hasText: GLOBAL_DNS })).toBeVisible();

      // Verify DNS Server config is shown
      await expect(page.getByText(DNS_SERVER_IP).first()).toBeVisible();

      // Complete the setup
      await page.getByRole('button', { name: 'Complete Setup' }).click();

      // The system API key (VITE_DISABLE_AUTH mode) lacks integrations:create permission.
      // Detect this and skip the rest of the test gracefully.
      const setupComplete = page.getByText('Setup complete');
      const permissionError = page.getByText('Insufficient permissions').first();
      const result = await Promise.race([
        setupComplete.waitFor({ timeout: 30_000 }).then(() => 'success' as const),
        permissionError.waitFor({ timeout: 30_000 }).then(() => 'no-permission' as const),
      ]);

      if (result === 'no-permission') {
        // Close the wizard and skip remaining steps
        await page.getByRole('button', { name: 'Back' }).click();
        test.skip(true, 'API key lacks integrations:create permission — skipping lifecycle test');
      }
    });

    // =============================================
    // STEP 6: Verify integration appears in "Your Integrations"
    // =============================================
    await test.step('Verify new integration appears in Your Integrations', async () => {
      // The wizard should auto-close and return to the integrations page
      // Wait for our integration card to appear
      await expect(page.getByRole('heading', { name: INTEGRATION_NAME, level: 3 })).toBeVisible({
        timeout: 15_000,
      });

      // Should show "Active" status
      const integrationCard = page.locator('[class*="cursor-pointer"]').filter({
        hasText: INTEGRATION_NAME,
      });
      await expect(integrationCard.getByText('Active')).toBeVisible();

      // Should have View Details and Delete buttons
      await expect(integrationCard.getByRole('button', { name: 'View Details' })).toBeVisible();
      await expect(
        integrationCard.getByRole('button', { name: 'Delete integration' })
      ).toBeVisible();
    });

    // =============================================
    // STEP 7: Delete the integration
    // =============================================
    await test.step('Delete the integration', async () => {
      // Find the delete button for our integration
      const integrationCard = page.locator('[class*="cursor-pointer"]').filter({
        hasText: INTEGRATION_NAME,
      });
      await integrationCard.getByRole('button', { name: 'Delete integration' }).click();

      // Confirm the delete dialog
      await expect(page.getByRole('heading', { name: 'Delete Integration' })).toBeVisible({
        timeout: 5_000,
      });
      await expect(page.getByText(`delete ${INTEGRATION_NAME}`, { exact: false })).toBeVisible();

      // Click "Delete Integration" to confirm
      await page.getByRole('button', { name: 'Delete Integration', exact: true }).click();

      // Verify the integration card is gone
      await expect(page.getByRole('heading', { name: INTEGRATION_NAME, level: 3 })).not.toBeVisible(
        { timeout: 10_000 }
      );
    });
  });
});
