import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E Test Configuration
 *
 * Two project setup:
 *
 * 1. "chromium" (default) — runs on port 5174 with VITE_DISABLE_AUTH=true.
 *    All tests except auth.spec.ts run here. No Keycloak needed.
 *
 * 2. "auth" — runs auth.spec.ts on port 5173 against the auth-enabled dev
 *    server. Requires Keycloak at localhost:8080. The globalSetup logs in
 *    once and saves browser state; tests that need it load the state file.
 *    Skips gracefully when Keycloak is unavailable.
 *
 * Run all:          npx playwright test
 * Run default only: npx playwright test --project=chromium
 * Run auth only:    npx playwright test --project=auth
 *
 * See https://playwright.dev/docs/test-configuration
 */

const E2E_PORT = 5174;
const E2E_BASE_URL = `http://localhost:${E2E_PORT}`;
const AUTH_BASE_URL = 'http://localhost:5173';

export default defineConfig({
  // Test directory
  testDir: './tests/e2e',

  // Global setup: Keycloak login (saves auth-state.json for the auth project).
  // Skips gracefully when Keycloak is not running.
  globalSetup: './playwright.globalSetup.ts',

  // Run tests in files in parallel
  fullyParallel: true,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on failures (2 on CI, 1 locally to handle transient flakiness)
  retries: process.env.CI ? 2 : 1,

  // Limit parallelism to prevent backend overload from concurrent API calls.
  // CI uses 1 worker for full stability; locally cap at 2 so the long-running
  // lifecycle/integration tests don't time out under heavy parallel load.
  workers: process.env.CI ? 1 : 2,

  // Reporter to use
  reporter: process.env.CI ? 'github' : 'html',

  // Global timeout for the entire test run (5 minutes for local, 3 min on CI with 1 worker)
  globalTimeout: process.env.CI ? 180_000 : 300_000,

  // Per-test timeout (30 seconds)
  timeout: 30_000,

  // Expect timeout (5 seconds for assertions)
  expect: {
    timeout: 5_000,
  },

  // Shared settings for all projects
  use: {
    // Action timeout (10 seconds for clicks, fills, etc.)
    actionTimeout: 10_000,

    // Navigation timeout (15 seconds for page.goto, etc.)
    navigationTimeout: 15_000,

    // Collect trace when retrying the failed test
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',

    // Video on failure
    video: 'retain-on-failure',
  },

  projects: [
    // Default project: auth-disabled server on port 5174
    {
      name: 'chromium',
      testIgnore: ['**/auth.spec.ts'],
      use: {
        ...devices['Desktop Chrome'],
        colorScheme: 'dark',
        baseURL: E2E_BASE_URL,
      },
    },

    // Auth project: auth-enabled server on port 5173 (requires Keycloak)
    {
      name: 'auth',
      testMatch: '**/auth.spec.ts',
      use: {
        ...devices['Desktop Chrome'],
        colorScheme: 'dark',
        baseURL: AUTH_BASE_URL,
      },
    },
  ],

  // Start a separate dev server on port 5174 with auth disabled.
  // VITE_E2E_API_KEY is forwarded only when explicitly set in the shell so that
  // an empty value doesn't override the .env file (Vite's dotenv won't overwrite
  // existing env vars, even empty ones).
  webServer: {
    command: [
      'VITE_DISABLE_AUTH=true',
      process.env.VITE_E2E_API_KEY ? `VITE_E2E_API_KEY=${process.env.VITE_E2E_API_KEY}` : '',
      `npx vite --port ${E2E_PORT}`,
    ]
      .filter(Boolean)
      .join(' '),
    url: E2E_BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
