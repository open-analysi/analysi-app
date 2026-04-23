# End-to-End Tests

E2E tests using Playwright to verify critical user workflows.

## Quick Start

```bash
# Run all E2E tests (headless)
make test-e2e
# or
npm run test:e2e

# Run with Playwright UI (interactive, recommended for development)
make test-e2e-ui
# or
npm run test:e2e:ui

# Run in headed mode (see the browser)
make test-e2e-headed

# Run in debug mode (step through tests)
make test-e2e-debug
```

## Test Structure

### `smoke.spec.ts`

Quick sanity checks to verify the application is working:

- Home page loads
- Navigation works
- Basic pages render
- **Performance check**: No duplicate API calls on Alerts page

### `workbench-from-alert.spec.ts`

Critical workflow: Opening Workbench from Alert Details

- Tests the full user journey: Alerts → Alert Details → Workflow Tasks → Workbench
- Verifies code editor is populated with Cy script
- Verifies input data is pre-filled
- Tests task execution with pre-filled data

**Regressions caught by this test:**

- API response unwrapping issues (ApiResponse<T> vs T)
- Empty code editor when opening from workflow tasks

## Writing New Tests

### Best Practices

1. **Use descriptive test names** that explain what the test does
2. **Test user workflows**, not implementation details
3. **Use data-testid** attributes for stable selectors when possible
4. **Keep tests isolated** - each test should set up its own state
5. **Use Page Object Model** for complex pages (see `/tests/e2e/pages/` if created)

### Example Test

```typescript
import { test, expect } from '@playwright/test';

test('should complete user workflow', async ({ page }) => {
  // Navigate
  await page.goto('/your-page');

  // Wait for critical element
  await page.waitForSelector('text=Expected Content');

  // Interact
  await page.click('button:has-text("Click Me")');

  // Assert
  await expect(page.locator('text=Success')).toBeVisible();
});
```

## Configuration

See `playwright.config.ts` for configuration options:

- Test directory
- Browsers to test
- Base URL
- Timeouts
- Screenshots/videos on failure

## Debugging

### Visual Debugging (Recommended)

```bash
make test-e2e-ui
```

This opens the Playwright UI where you can:

- See test code and browser side-by-side
- Step through tests
- Inspect element selectors
- View trace timelines

### Debug Mode

```bash
make test-e2e-debug
```

This opens the Playwright Inspector for step-by-step debugging.

### Failed Test Artifacts

When tests fail, Playwright automatically captures:

- **Screenshots**: `test-results/*/test-failed-1.png`
- **Videos**: `test-results/*/video.webm`
- **Traces**: `test-results/*/trace.zip` (view at https://trace.playwright.dev)

## CI Integration

E2E tests should run in CI before merging:

```yaml
# .github/workflows/e2e.yml (example)
- name: Install dependencies
  run: npm ci

- name: Install Playwright Browsers
  run: npx playwright install --with-deps chromium

- name: Run E2E tests
  run: make test-e2e
```

## Troubleshooting

### Tests timing out

- Increase timeout in `playwright.config.ts`
- Check if dev server is running properly
- Verify backend services are accessible

### Flaky tests

- Add explicit waits: `await page.waitForSelector()`
- Use more specific selectors
- Check for race conditions in your application

### Can't find elements

- Use Playwright UI to inspect selectors
- Check if element is in an iframe
- Verify element visibility (not just DOM presence)

## Resources

- [Playwright Documentation](https://playwright.dev/docs/intro)
- [Best Practices](https://playwright.dev/docs/best-practices)
- [Debugging Guide](https://playwright.dev/docs/debug)
- [Selectors Guide](https://playwright.dev/docs/selectors)
