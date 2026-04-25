import { defineConfig, devices } from '@playwright/test';

const BASE_URL = 'http://localhost:5173';

export default defineConfig({
  testDir: '.',
  testMatch: 'demo.ts',
  timeout: 180_000,
  use: {
    ...devices['Desktop Chrome'],
    colorScheme: 'dark',
    baseURL: BASE_URL,
    viewport: { width: 1440, height: 900 },
    video: {
      mode: 'on',
      size: { width: 1440, height: 900 },
    },
    launchOptions: {
      slowMo: 40,
    },
  },
});
