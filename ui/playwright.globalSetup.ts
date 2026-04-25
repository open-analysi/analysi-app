/**
 * Playwright Global Setup — Keycloak Auth
 *
 * Logs in via Keycloak once and saves the browser storage state.
 * All E2E tests reload this state to start as an authenticated user.
 *
 * Requires Keycloak to be running at http://localhost:8080.
 * Skips gracefully if Keycloak is unreachable.
 */
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium, request } from '@playwright/test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const AUTH_STATE_FILE = path.join(__dirname, 'tests', 'e2e', '.auth-state.json');
const KEYCLOAK_URL = 'http://localhost:8080';
const APP_URL = 'http://localhost:5173';

async function isKeycloakRunning(): Promise<boolean> {
  try {
    const ctx = await request.newContext();
    const response = await ctx.get(`${KEYCLOAK_URL}/realms/analysi`, { timeout: 5000 });
    await ctx.dispose();
    return response.ok();
  } catch {
    return false;
  }
}

export default async function globalSetup() {
  // Check if Keycloak is running
  const keycloakAvailable = await isKeycloakRunning();
  if (!keycloakAvailable) {
    console.warn(
      '\n⚠  Keycloak not running at http://localhost:8080 — auth E2E tests will be skipped\n'
    );
    // Write empty auth state file so tests can detect and skip
    fs.writeFileSync(AUTH_STATE_FILE, JSON.stringify({ keycloakUnavailable: true }));
    return;
  }

  const browser = await chromium.launch();
  const page = await browser.newPage();

  try {
    // Navigate to app — OidcProvider will redirect to Keycloak login.
    // Use 'domcontentloaded' because 'networkidle' resolves before the
    // async OIDC redirect happens (React must mount first, then the
    // library initiates the authorization code flow redirect).
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 });

    // Wait for the OIDC redirect to actually reach Keycloak
    await page.waitForURL(`${KEYCLOAK_URL}/**`, { timeout: 30_000 });

    // Now wait for the Keycloak login form to render
    await page.waitForSelector('input[name="username"]', { timeout: 15_000 });

    // Fill credentials (dev user from realm seed)
    await page.fill('input[name="username"]', 'dev');
    await page.fill('input[name="password"]', 'dev');
    await page.click('#kc-login');

    // Wait for redirect back to our app
    await page.waitForURL(`${APP_URL}/**`, { timeout: 15_000 });

    // Wait for app to fully load (sidebar navigation should be visible)
    await page.waitForSelector('[data-testid="sidebar"]', { timeout: 10_000 }).catch(() => {
      // Sidebar might not have testid yet — wait for any nav element
    });

    // Small delay for SW to store token
    await page.waitForTimeout(1000);

    // Save storage state (session storage + cookies)
    // Note: SW token is in browser context, so tests in same context will be auth'd
    const storageState = await page.context().storageState();
    fs.writeFileSync(AUTH_STATE_FILE, JSON.stringify(storageState));

    console.info('\n✓ Keycloak auth complete — storage state saved\n');
  } finally {
    await browser.close();
  }
}
