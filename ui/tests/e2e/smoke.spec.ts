import { test, expect } from '@playwright/test';

/**
 * E2E Smoke Tests
 *
 * Quick sanity checks to verify the application is working.
 * These should run fast and catch critical breakages.
 */

test.describe('Smoke Tests', () => {
  test('should load the home page', async ({ page }) => {
    await page.goto('/');

    // Verify the page title
    await expect(page).toHaveTitle(/Analysi Security Dashboard/);

    // Verify navigation is visible using role-based selectors
    await expect(page.getByRole('link', { name: 'Alerts' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Integrations' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Workbench' })).toBeVisible();
  });

  test('should navigate to Alerts page', async ({ page }) => {
    await page.goto('/alerts');

    // Verify we're on the alerts page
    await expect(page.getByText('Alert Analysis Queue')).toBeVisible();

    // Verify table headers are present by checking the header row
    const headerRow = page.locator('table').first().locator('tr').first();
    await expect(headerRow).toContainText('Severity');
    await expect(headerRow).toContainText('Status');
  });

  test('should navigate to Integrations page', async ({ page }) => {
    await page.goto('/');

    // Click on Integrations link
    await page.getByRole('link', { name: 'Integrations' }).click();

    // Verify we're on the integrations page
    await expect(page.getByText('Your Integrations')).toBeVisible();
  });

  test('should navigate to Workbench page', async ({ page }) => {
    await page.goto('/workbench');

    // Verify we're on the workbench page - look for the Code Editor heading
    await expect(page.getByRole('heading', { name: 'Code Editor' })).toBeVisible();

    // Verify the search tasks combobox is present
    await expect(page.getByRole('combobox', { name: 'Search tasks...' })).toBeVisible();

    // Verify Run button is present
    await expect(page.getByRole('button', { name: /Run/ })).toBeVisible();
  });

  test('should navigate to alert details when clicking an alert row', async ({ page }) => {
    await page.goto('/alerts');
    await expect(page.getByText('Alert Analysis Queue')).toBeVisible({ timeout: 10_000 });

    // Wait for alerts to load — skip if no alerts in the table
    const firstDataRow = page.locator('table tbody tr').first();
    const hasAlerts = await firstDataRow.isVisible().catch(() => false);
    test.skip(!hasAlerts, 'No alerts available in backend');

    // Skip if the first row is just a loading or "No alerts found" message
    const rowText = await firstDataRow.textContent();
    test.skip(
      rowText?.includes('Loading') || rowText?.includes('No alerts found') || false,
      'No alert data rows available'
    );

    // Click the first alert row
    await firstDataRow.click();

    // Verify we navigated to alert details (URL should contain /alerts/<id>)
    await expect(page).toHaveURL(/\/alerts\/[^/]+$/);

    // Verify we're NOT on the integrations page (the bug sent us there)
    await expect(page.getByText('Alert Analysis Queue')).not.toBeVisible();
    await expect(page.getByText('Your Integrations')).not.toBeVisible();
  });

  test('should not have duplicate API calls on Alerts page', async ({ page }) => {
    // Track API requests
    const alertsRequests: string[] = [];
    const dispositionsRequests: string[] = [];

    page.on('request', (request) => {
      const url = request.url();
      // Only track fetch/xhr API calls, not page navigation or static assets
      const resourceType = request.resourceType();
      if (resourceType !== 'fetch' && resourceType !== 'xhr') return;

      if (url.includes('/alerts')) {
        alertsRequests.push(url);
      }
      if (url.includes('/dispositions')) {
        dispositionsRequests.push(url);
      }
    });

    // Navigate to alerts page and wait for network to settle
    await page.goto('/alerts', { waitUntil: 'networkidle' });

    // Verify the page loaded
    await expect(page.getByText('Alert Analysis Queue')).toBeVisible();

    // Verify only a reasonable number of alerts requests were made
    expect(alertsRequests.length).toBeLessThanOrEqual(2);

    // Verify only one dispositions request was made
    expect(dispositionsRequests.length).toBeLessThanOrEqual(1);
  });
});
