import { test, expect } from '@playwright/test';

/**
 * E2E Test: Workbench Panel Resizing
 *
 * Verifies that the resizable panels in the Workbench Execute tab work correctly.
 * This test was added after a regression where react-resizable-panels v4
 * broke resizing because numeric size props were interpreted as pixels
 * instead of percentages.
 *
 * Key panels tested:
 * - Sidebar (left task list) — vertical separator
 * - Editor / Input & Output — horizontal separator
 * - Input / Output — vertical separator
 */

test.describe('Workbench Panel Resizing', () => {
  test.beforeEach(async ({ page }) => {
    // Clear any stale layout data from localStorage before each test
    await page.addInitScript(() => {
      const keysToRemove: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (
          key &&
          (key.includes('workbench') ||
            key.includes('workflow-builder') ||
            key.includes('react-resizable-panels'))
        ) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach((k) => localStorage.removeItem(k));
    });

    await page.goto('/workbench?tab=execute');

    // Wait for the workbench to fully load
    await expect(page.getByRole('heading', { name: 'Code Editor' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Input', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Output', exact: true })).toBeVisible();
  });

  test('should render all panels with proper proportions', async ({ page }) => {
    // Verify all key panels are visible and properly sized
    const panels = await page.evaluate(() => {
      const dataPanels = document.querySelectorAll('[data-panel]');
      return Array.from(dataPanels).map((p) => {
        const rect = (p as HTMLElement).getBoundingClientRect();
        return {
          id: p.getAttribute('data-panel') || p.id,
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        };
      });
    });

    // All panels should have meaningful dimensions (> 50px in both dimensions)
    for (const panel of panels) {
      expect(panel.width, `Panel "${panel.id}" should have width > 50px`).toBeGreaterThan(50);
      expect(panel.height, `Panel "${panel.id}" should have height > 50px`).toBeGreaterThan(50);
    }
  });

  test('should have separators with correct ARIA percentage values', async ({ page }) => {
    // Verify separators have ARIA attributes with sensible percentage values
    // This catches the v4 regression where numeric props were interpreted as pixels
    const separators = await page.evaluate(() => {
      const seps = document.querySelectorAll('[role="separator"]');
      return Array.from(seps).map((s) => ({
        id: s.id,
        orientation: s.getAttribute('aria-orientation'),
        valueMin: parseFloat(s.getAttribute('aria-valuemin') || '0'),
        valueMax: parseFloat(s.getAttribute('aria-valuemax') || '0'),
        valueNow: parseFloat(s.getAttribute('aria-valuenow') || '0'),
      }));
    });

    // Should have at least 3 separators (sidebar, editor/IO, input/output)
    expect(separators.length).toBeGreaterThanOrEqual(3);

    for (const sep of separators) {
      // All values should be reasonable percentages (0-100), not pixel values
      expect(sep.valueMin, `Separator "${sep.id}" min should be < 100`).toBeLessThanOrEqual(100);
      expect(sep.valueMax, `Separator "${sep.id}" max should be <= 100`).toBeLessThanOrEqual(100);
      expect(
        sep.valueNow,
        `Separator "${sep.id}" current value should be between min and max`
      ).toBeGreaterThanOrEqual(sep.valueMin);
      expect(sep.valueNow).toBeLessThanOrEqual(sep.valueMax);

      // Current value should NOT be equal to min (that would mean panel is stuck/collapsed)
      expect(
        sep.valueNow,
        `Separator "${sep.id}" should not be stuck at minimum`
      ).toBeGreaterThan(sep.valueMin);
    }
  });

  test('should resize the editor/IO horizontal separator by dragging', async ({ page }) => {
    // Find the horizontal separator (between editor and Input & Output)
    const horizontalSep = page.locator(
      '[role="separator"][aria-orientation="horizontal"]'
    );
    await expect(horizontalSep).toBeVisible();

    // Get initial value
    const valueBefore = parseFloat(
      (await horizontalSep.getAttribute('aria-valuenow')) || '0'
    );

    // Drag the separator up by 60px
    const box = await horizontalSep.boundingBox();
    expect(box).toBeTruthy();

    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.mouse.down();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2 - 60, {
      steps: 10,
    });
    await page.mouse.up();

    // Verify the value changed
    const valueAfter = parseFloat(
      (await horizontalSep.getAttribute('aria-valuenow')) || '0'
    );

    expect(
      valueAfter,
      'Horizontal separator should have moved (editor panel got smaller)'
    ).toBeLessThan(valueBefore);

    // The change should be meaningful (at least 3% change)
    expect(Math.abs(valueBefore - valueAfter)).toBeGreaterThan(3);
  });

  test('should resize the sidebar vertical separator by dragging', async ({ page }) => {
    // First vertical separator is the sidebar one
    const sidebarSep = page.locator('[role="separator"][aria-orientation="vertical"]').first();
    await expect(sidebarSep).toBeVisible();

    const valueBefore = parseFloat(
      (await sidebarSep.getAttribute('aria-valuenow')) || '0'
    );

    // Drag the separator right by 40px
    const box = await sidebarSep.boundingBox();
    expect(box).toBeTruthy();

    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.mouse.down();
    await page.mouse.move(box!.x + box!.width / 2 + 40, box!.y + box!.height / 2, {
      steps: 10,
    });
    await page.mouse.up();

    const valueAfter = parseFloat(
      (await sidebarSep.getAttribute('aria-valuenow')) || '0'
    );

    expect(
      valueAfter,
      'Sidebar separator should have moved (sidebar got larger)'
    ).toBeGreaterThan(valueBefore);

    expect(Math.abs(valueBefore - valueAfter)).toBeGreaterThan(1);
  });

  test('should resize the input/output vertical separator by dragging', async ({ page }) => {
    // Second vertical separator is the input/output one
    const ioSep = page.locator('[role="separator"][aria-orientation="vertical"]').nth(1);
    await expect(ioSep).toBeVisible();

    const valueBefore = parseFloat(
      (await ioSep.getAttribute('aria-valuenow')) || '0'
    );

    // Drag the separator right by 50px
    const box = await ioSep.boundingBox();
    expect(box).toBeTruthy();

    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.mouse.down();
    await page.mouse.move(box!.x + box!.width / 2 + 50, box!.y + box!.height / 2, {
      steps: 10,
    });
    await page.mouse.up();

    const valueAfter = parseFloat(
      (await ioSep.getAttribute('aria-valuenow')) || '0'
    );

    expect(
      valueAfter,
      'I/O separator should have moved (input panel got larger)'
    ).toBeGreaterThan(valueBefore);

    expect(Math.abs(valueBefore - valueAfter)).toBeGreaterThan(1);
  });

  test('should maintain panel visibility after resizing', async ({ page }) => {
    // Drag the horizontal separator significantly
    const horizontalSep = page.locator(
      '[role="separator"][aria-orientation="horizontal"]'
    );
    const box = await horizontalSep.boundingBox();
    expect(box).toBeTruthy();

    // Drag up by 80px
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.mouse.down();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2 - 80, {
      steps: 10,
    });
    await page.mouse.up();

    // All critical UI elements should still be visible
    await expect(page.getByRole('heading', { name: 'Code Editor' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Input', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Output', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /Run/ })).toBeVisible();
  });
});
