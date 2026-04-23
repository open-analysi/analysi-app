import { test, expect, type Page } from '@playwright/test';

/**
 * E2E Test: Workbench Output Renderer & Diff View
 *
 * Verifies the output panel formatting and the jsondiffpatch-powered
 * diff view that compares JSON input with task execution output.
 *
 * These tests execute real Cy scripts against the backend, so each
 * test needs extra time for task polling to complete (~10-30s per run).
 */

// Backend task execution can take 10-30s normally, but under parallel test
// load (2 workers) can stretch to 60-120s due to task queue congestion.
const EXEC_TIMEOUT = 120_000;

/** Set the Ace editor content via its API */
async function setEditorScript(page: Page, script: string) {
  await page.evaluate((s) => {
    const el = document.querySelector('.ace_editor') as HTMLElement & {
      env?: { editor?: { setValue(v: string, pos?: number): void } };
    };
    el?.env?.editor?.setValue(s, -1);
  }, script);
}

/** Fill the input textarea, run the script, and wait for execution to complete */
async function runWithInput(page: Page, script: string, inputJson: string) {
  await setEditorScript(page, script);

  const inputArea = page.getByPlaceholder('Enter input data (JSON, text, etc.)');
  await inputArea.fill(inputJson);

  const runButton = page.getByRole('button', { name: /Run/ });
  await runButton.click();

  // Wait for execution to START (button transitions to "Running..."),
  // then wait for it to FINISH (button reverts to "Run ⌘↵").
  // Without the first check, the second can pass before the state changes.
  await expect(runButton).toContainText('Running', { timeout: 10_000 });
  await expect(runButton).not.toContainText('Running', { timeout: EXEC_TIMEOUT });
}

test.describe('Workbench Output & Diff View', () => {
  // Each test executes a real backend task — mark as slow (3× timeout)
  test.slow();

  test.beforeEach(async ({ page }) => {
    await page.goto('/workbench');
    await expect(page.getByRole('heading', { name: 'Code Editor' })).toBeVisible({
      timeout: 15_000,
    });
  });

  test('pretty-prints JSON output', async ({ page }) => {
    const inputJson = '{"severity":"high","source":"firewall"}';
    await runWithInput(page, 'return input', inputJson);

    // Should have indented pretty-printed keys
    await expect(page.getByText('"severity": "high"')).toBeVisible();
    await expect(page.getByText('"source": "firewall"')).toBeVisible();
  });

  test('shows "No differences found" for return input', async ({ page }) => {
    const inputJson = '{"severity":"high","source":"firewall","alert_id":"ABC-123"}';
    await runWithInput(page, 'return input', inputJson);

    await page.getByRole('button', { name: 'Diff' }).click();

    await expect(page.getByText('No differences found')).toBeVisible();
  });

  test('shows modified, added, and unchanged fields in diff', async ({ page }) => {
    const inputJson = '{"severity":"high","source":"firewall","alert_id":"ABC-123"}';
    const script = [
      'result = input',
      'result["severity"] = "critical"',
      'result["enrichments"] = [{"context": "test enrichment"}]',
      'return result',
    ].join('\n');

    await runWithInput(page, script, inputJson);
    await page.getByRole('button', { name: 'Diff' }).click();

    // Modified: severity changed
    await expect(page.locator('.jsondiffpatch-modified').first()).toBeVisible();
    // Added: enrichments array
    await expect(page.locator('.jsondiffpatch-added').first()).toBeVisible();
    // Unchanged: source and alert_id
    await expect(page.locator('.jsondiffpatch-unchanged').first()).toBeVisible();
  });

  test('switches between Output and Diff views', async ({ page }) => {
    const inputJson = '{"a":1}';
    const script = 'result = input\nresult["b"] = 2\nreturn result';

    await runWithInput(page, script, inputJson);

    // Should start in Output view with pretty-printed JSON
    await expect(page.getByText('"b": 2')).toBeVisible();

    // Switch to Diff — should show added field
    await page.getByRole('button', { name: 'Diff' }).click();
    await expect(page.locator('.jsondiffpatch-added').first()).toBeVisible();

    // Switch back to Output — diff markers should be gone
    await page.getByRole('button', { name: 'Output' }).click();
    await expect(page.getByText('"b": 2')).toBeVisible();
    await expect(page.locator('.jsondiffpatch-added')).toHaveCount(0);
  });

  test('shows deleted fields in diff when output removes keys', async ({ page }) => {
    const inputJson = '{"keep":"yes","remove_me":"gone"}';
    const script = ['result = {}', 'result["keep"] = input["keep"]', 'return result'].join('\n');

    await runWithInput(page, script, inputJson);
    await page.getByRole('button', { name: 'Diff' }).click();

    await expect(page.locator('.jsondiffpatch-deleted').first()).toBeVisible();
  });

  test('does not show diff toggle when no input data is provided', async ({ page }) => {
    // This test often runs last when the backend task queue is congested
    // from parallel workers, so give it extra headroom beyond test.slow().
    test.setTimeout(180_000);

    await setEditorScript(page, 'return "hello"');

    const runButton = page.getByRole('button', { name: /Run/ });
    await runButton.click();

    // Wait for execution to START then FINISH
    await expect(runButton).toContainText('Running', { timeout: 10_000 });
    await expect(runButton).not.toContainText('Running', { timeout: EXEC_TIMEOUT });

    // Wait for the output placeholder to disappear (replaced by actual output)
    await expect(page.getByText('Output will appear here after running the task')).not.toBeVisible({
      timeout: 10_000,
    });

    // Diff button should NOT be visible (no input data was provided)
    await expect(page.getByRole('button', { name: 'Diff' })).not.toBeVisible();
  });
});
