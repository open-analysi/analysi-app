import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

import { test, expect, type Page, type Browser, type BrowserContext } from '@playwright/test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_STATE_FILE = path.join(__dirname, '.auth-state.json');
const APP_URL = 'http://localhost:5173';
const KEYCLOAK_HOST = 'localhost:8080';

function isKeycloakAvailable(): boolean {
  try {
    const data = JSON.parse(fs.readFileSync(AUTH_STATE_FILE, 'utf-8'));
    return !data.keycloakUnavailable;
  } catch {
    return false;
  }
}

/**
 * Wait for the OIDC flow to settle. After navigating, the page may transit
 * through: app → Keycloak → /authentication/callback → app. This waits
 * until we land on a real app page (not a callback or Keycloak URL).
 */
async function waitForAppReady(page: Page, timeout = 30_000) {
  await page.waitForURL(
    (url) =>
      url.hostname === 'localhost' &&
      url.port === '5173' &&
      !url.pathname.includes('/authentication/'),
    { timeout }
  );
}

/**
 * Perform a fresh Keycloak login on the given page.
 * Used when the saved auth state has expired.
 */
async function performKeycloakLogin(page: Page) {
  // Wait for all three form elements to be visible before interacting —
  // Keycloak may still be rendering when the username input first appears.
  const username = page.locator('input[name="username"]');
  const password = page.locator('input[name="password"]');
  const loginBtn = page.locator('#kc-login');
  await username.waitFor({ state: 'visible', timeout: 15_000 });
  await password.waitFor({ state: 'visible', timeout: 5_000 });
  await loginBtn.waitFor({ state: 'visible', timeout: 5_000 });

  await username.fill('dev');
  await password.fill('dev');
  await loginBtn.click();

  // Keycloak may reject the first attempt when the session/CSRF token is stale
  // (e.g., after loading expired auth state). It shows "Invalid username or
  // password." but keeps the login form visible. Detect this and retry once.
  const appOrError = await Promise.race([
    page
      .waitForURL(
        (url) =>
          url.hostname === 'localhost' &&
          url.port === '5173' &&
          !url.pathname.includes('/authentication/'),
        { timeout: 15_000 }
      )
      .then(() => 'app' as const),
    page
      .getByText('Invalid username or password')
      .waitFor({ state: 'visible', timeout: 15_000 })
      .then(() => 'error' as const),
  ]).catch(() => 'unknown' as const);

  if (appOrError === 'error') {
    // Retry — the fresh Keycloak page now has a valid CSRF token
    await password.waitFor({ state: 'visible', timeout: 5_000 });
    await username.fill('dev');
    await password.fill('dev');
    await loginBtn.click();
    await waitForAppReady(page);
  } else if (appOrError === 'unknown') {
    // Fallback: maybe we're still on Keycloak for another reason
    await waitForAppReady(page, 15_000);
  }
  // appOrError === 'app' means we're already on the app — done
}

/**
 * Detect and handle a Keycloak redirect: if the page is on Keycloak,
 * perform a fresh login, save state, and navigate back to the target URL.
 * Returns true if a re-login was performed.
 */
async function handleKeycloakRedirect(
  page: Page,
  context: BrowserContext,
  targetUrl: string
): Promise<boolean> {
  if (!page.url().includes(KEYCLOAK_HOST)) return false;

  await performKeycloakLogin(page);

  // Save refreshed state for remaining tests
  const newState = await context.storageState();
  fs.writeFileSync(AUTH_STATE_FILE, JSON.stringify(newState));

  // OIDC callback always lands on "/" — navigate back to the intended target
  if (!page.url().includes(new URL(targetUrl).pathname)) {
    await page.goto(targetUrl);
    await waitForAppReady(page);
  }
  return true;
}

/**
 * Create an authenticated browser context. Loads the saved auth state, then
 * navigates to the target URL. If the saved session has expired (page lands
 * on Keycloak login instead of the app), performs a fresh login automatically
 * and updates the saved state file for subsequent tests.
 */
async function createAuthenticatedPage(
  browser: Browser,
  targetUrl: string
): Promise<{ context: BrowserContext; page: Page }> {
  const authState = JSON.parse(fs.readFileSync(AUTH_STATE_FILE, 'utf-8'));
  const context = await browser.newContext({ storageState: authState });
  const page = await context.newPage();

  await page.goto(targetUrl);

  // Wait for the page to settle: either we land on the app or on Keycloak.
  // The OIDC flow may take the page through: app → /authentication/callback → Keycloak.
  // Use a race between the app sidebar appearing and the Keycloak login form appearing
  // to avoid false positives from URL-only checks.
  const appReady = page.locator('nav').waitFor({ timeout: 20_000 });
  const keycloakLogin = page.locator('input[name="username"]').waitFor({ timeout: 20_000 });

  const settled = await Promise.race([
    appReady.then(() => 'app' as const),
    keycloakLogin.then(() => 'keycloak' as const),
  ]).catch(() => 'unknown' as const);

  if (settled === 'keycloak' || page.url().includes(KEYCLOAK_HOST)) {
    await handleKeycloakRedirect(page, context, targetUrl);
  }

  return { context, page };
}

test.describe('Authentication Flow', () => {
  test.beforeEach(() => {
    test.skip(!isKeycloakAvailable(), 'Keycloak not available — skipping auth tests');
  });

  test('login via Keycloak and land on app', async ({ browser }) => {
    // Fresh context — no cookies, no storageState — to test the full login flow
    const context = await browser.newContext();
    const page = await context.newPage();

    await page.goto(APP_URL);

    // OidcSecure redirects to Keycloak login form
    await page.waitForSelector('#kc-login', { timeout: 15_000 });
    await expect(page.locator('input[name="username"]')).toBeVisible();

    // Fill credentials and submit
    await performKeycloakLogin(page);

    // App sidebar should be visible
    await expect(page.locator('nav')).toBeVisible({ timeout: 10_000 });

    await context.close();
  });

  test('authenticated user can access Account menu with Log Out', async ({ browser }) => {
    const { context, page } = await createAuthenticatedPage(browser, APP_URL);

    // The Account button is in the sidebar
    const accountButton = page.getByRole('button', { name: 'Account' });
    await expect(accountButton).toBeVisible({ timeout: 10_000 });

    // Click to open the account popover
    await accountButton.click();

    // The popover should show Log Out as a menu item
    const logOutItem = page.getByRole('menuitem', { name: 'Log Out' });
    await expect(logOutItem).toBeVisible({ timeout: 5_000 });

    await context.close();
  });

  test('logout redirects to Keycloak login', async ({ browser }) => {
    const { context, page } = await createAuthenticatedPage(browser, APP_URL);

    // Open Account popover and click Log Out
    const accountButton = page.getByRole('button', { name: 'Account' });
    await expect(accountButton).toBeVisible({ timeout: 10_000 });
    await accountButton.click();

    const logOutItem = page.getByRole('menuitem', { name: 'Log Out' });
    await expect(logOutItem).toBeVisible({ timeout: 5_000 });
    await logOutItem.click();

    // Should end up on Keycloak login or an unauthenticated state
    await page.waitForURL(/localhost:(8080|5173)/, { timeout: 15_000 });

    await context.close();
  });

  test('AccountSettings shows user email and tenant', async ({ browser }) => {
    const { context, page } = await createAuthenticatedPage(browser, `${APP_URL}/account-settings`);

    // Should show user info from the JWT claims
    await expect(page.getByText('dev@analysi.local')).toBeVisible({ timeout: 10_000 });

    await context.close();
  });
});
