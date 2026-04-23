import { test, expect } from '@playwright/test';

/**
 * E2E Test: Workflow Builder Panel Resizing
 *
 * Verifies that the resizable panels in the Workflow Builder tab work correctly.
 * The Builder has a nested panel layout:
 *
 *   ┌──────────┬─────────────────────┬────────────┐
 *   │ Palette  │      Canvas         │ Properties │
 *   │  (18%)   │      (57%)          │   (25%)    │
 *   │          │                     │            │
 *   └──────────┴─────────────────────┴────────────┘
 *
 * Two vertical separators:
 *   1. Palette ↔ Canvas (outer group)
 *   2. Canvas ↔ Properties (inner group)
 *
 * Both Palette and Properties panels are collapsible.
 */

test.describe('Workflow Builder Panel Resizing', () => {
  test.beforeEach(async ({ page }) => {
    // Clear stale layout data from localStorage
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

    await page.goto('/workbench?tab=builder');

    // Wait for the builder to fully load — palette heading and properties heading
    await expect(page.getByRole('heading', { name: 'Components' })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByRole('heading', { name: 'Properties' })).toBeVisible({
      timeout: 5_000,
    });
  });

  test('should render all three panels with proper dimensions', async ({ page }) => {
    // Verify all panels exist and have meaningful size
    const panels = await page.evaluate(() => {
      const dataPanels = document.querySelectorAll('[data-panel]');
      return Array.from(dataPanels).map((p) => {
        const rect = (p as HTMLElement).getBoundingClientRect();
        return {
          id: p.getAttribute('data-panel-id') || p.getAttribute('data-panel') || p.id,
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        };
      });
    });

    // Should have at least 3 panels (palette, canvas wrapper, canvas, properties)
    expect(panels.length).toBeGreaterThanOrEqual(3);

    // All panels should have meaningful dimensions (> 30px width, > 100px height)
    for (const panel of panels) {
      expect(panel.width, `Panel "${panel.id}" should have width > 30px`).toBeGreaterThan(30);
      expect(panel.height, `Panel "${panel.id}" should have height > 100px`).toBeGreaterThan(100);
    }
  });

  test('should have separators with correct ARIA percentage values', async ({ page }) => {
    // Builder has vertical separators between the panels
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

    // Should have at least 2 vertical separators (palette↔canvas, canvas↔properties)
    const verticalSeps = separators.filter((s) => s.orientation === 'vertical');
    expect(verticalSeps.length).toBeGreaterThanOrEqual(2);

    for (const sep of verticalSeps) {
      // Values should be percentages (0-100), not pixel values
      expect(sep.valueMin, `Separator "${sep.id}" min should be ≤ 100`).toBeLessThanOrEqual(100);
      expect(sep.valueMax, `Separator "${sep.id}" max should be ≤ 100`).toBeLessThanOrEqual(100);
      expect(
        sep.valueNow,
        `Separator "${sep.id}" value should be between min and max`
      ).toBeGreaterThanOrEqual(sep.valueMin);
      expect(sep.valueNow).toBeLessThanOrEqual(sep.valueMax);

      // Should not be stuck at minimum (panel collapsed unexpectedly)
      expect(
        sep.valueNow,
        `Separator "${sep.id}" should not be stuck at minimum`
      ).toBeGreaterThan(sep.valueMin);
    }
  });

  test('should resize the palette separator by dragging', async ({ page }) => {
    // The first vertical separator is between Palette and Canvas
    const paletteSep = page.locator('[role="separator"][aria-orientation="vertical"]').first();
    await expect(paletteSep).toBeVisible();

    const valueBefore = parseFloat(
      (await paletteSep.getAttribute('aria-valuenow')) || '0'
    );

    // Drag the separator right by 60px (make palette wider)
    const box = await paletteSep.boundingBox();
    expect(box).toBeTruthy();

    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.mouse.down();
    await page.mouse.move(box!.x + box!.width / 2 + 60, box!.y + box!.height / 2, {
      steps: 10,
    });
    await page.mouse.up();

    const valueAfter = parseFloat(
      (await paletteSep.getAttribute('aria-valuenow')) || '0'
    );

    expect(
      valueAfter,
      'Palette separator should have moved (palette got wider)'
    ).toBeGreaterThan(valueBefore);

    // The change should be meaningful (at least 2% change)
    expect(Math.abs(valueBefore - valueAfter)).toBeGreaterThan(2);
  });

  test('should resize the properties separator by dragging', async ({ page }) => {
    // The second vertical separator is between Canvas and Properties
    const propsSep = page.locator('[role="separator"][aria-orientation="vertical"]').nth(1);
    await expect(propsSep).toBeVisible();

    const valueBefore = parseFloat(
      (await propsSep.getAttribute('aria-valuenow')) || '0'
    );

    // Drag the separator left by 60px (make properties wider)
    const box = await propsSep.boundingBox();
    expect(box).toBeTruthy();

    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.mouse.down();
    await page.mouse.move(box!.x + box!.width / 2 - 60, box!.y + box!.height / 2, {
      steps: 10,
    });
    await page.mouse.up();

    const valueAfter = parseFloat(
      (await propsSep.getAttribute('aria-valuenow')) || '0'
    );

    expect(
      valueAfter,
      'Properties separator should have moved (properties got wider)'
    ).toBeLessThan(valueBefore);

    // The change should be meaningful
    expect(Math.abs(valueBefore - valueAfter)).toBeGreaterThan(2);
  });

  test('should maintain all panels visible after resizing', async ({ page }) => {
    // Drag the palette separator right
    const paletteSep = page.locator('[role="separator"][aria-orientation="vertical"]').first();
    const box1 = await paletteSep.boundingBox();
    expect(box1).toBeTruthy();

    await page.mouse.move(box1!.x + box1!.width / 2, box1!.y + box1!.height / 2);
    await page.mouse.down();
    await page.mouse.move(box1!.x + box1!.width / 2 + 50, box1!.y + box1!.height / 2, {
      steps: 10,
    });
    await page.mouse.up();

    // Drag the properties separator left
    const propsSep = page.locator('[role="separator"][aria-orientation="vertical"]').nth(1);
    const box2 = await propsSep.boundingBox();
    expect(box2).toBeTruthy();

    await page.mouse.move(box2!.x + box2!.width / 2, box2!.y + box2!.height / 2);
    await page.mouse.down();
    await page.mouse.move(box2!.x + box2!.width / 2 - 50, box2!.y + box2!.height / 2, {
      steps: 10,
    });
    await page.mouse.up();

    // All critical UI elements should still be visible after resizing
    await expect(page.getByRole('heading', { name: 'Components' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Properties' })).toBeVisible();

    // Canvas toolbar buttons should still be accessible
    await expect(
      page.locator('button[title="Connect Nodes (C)"]')
    ).toBeVisible();
  });

  test('should collapse and expand the palette panel', async ({ page }) => {
    // Get palette panel width before collapse
    const widthBefore = await page.evaluate(() => {
      const panel = document.querySelector('#palette');
      return panel ? (panel as HTMLElement).getBoundingClientRect().width : -1;
    });
    expect(widthBefore).toBeGreaterThan(50);

    // Click the collapse button in the Palette header
    const collapseButton = page.locator('button[title="Collapse palette"]');
    await expect(collapseButton).toBeVisible();
    await collapseButton.click();

    // Verify the palette panel collapsed — its width should be near 0
    // Note: the heading DOM element remains in the tree but is clipped by overflow:hidden
    const paletteSep = page.locator('[role="separator"][aria-orientation="vertical"]').first();
    await expect(paletteSep).toHaveAttribute('aria-valuenow', /^0(\.0+)?$/, { timeout: 3_000 });

    const widthAfter = await page.evaluate(() => {
      const panel = document.querySelector('#palette');
      return panel ? (panel as HTMLElement).getBoundingClientRect().width : -1;
    });
    expect(widthAfter, 'Palette panel should be collapsed (near 0 width)').toBeLessThan(5);

    // Canvas and Properties should still be visible
    await expect(page.getByRole('heading', { name: 'Properties' })).toBeVisible();

    // Expand the palette by clicking the toggle button in the toolbar
    const expandButton = page.locator('button[title="Toggle palette (Ctrl+B)"]');
    await expandButton.click();

    // Palette should expand back to a meaningful width
    const widthExpanded = await page.evaluate(() => {
      const panel = document.querySelector('#palette');
      return panel ? (panel as HTMLElement).getBoundingClientRect().width : -1;
    });
    expect(widthExpanded, 'Palette panel should be expanded again').toBeGreaterThan(50);
  });

  test('should collapse and expand the properties panel', async ({ page }) => {
    // Get properties panel width before collapse
    const widthBefore = await page.evaluate(() => {
      const panel = document.querySelector('#properties');
      return panel ? (panel as HTMLElement).getBoundingClientRect().width : -1;
    });
    expect(widthBefore).toBeGreaterThan(50);

    // Click the collapse button in the Properties header
    const collapseButton = page.locator('button[title="Collapse properties"]');
    await expect(collapseButton).toBeVisible();
    await collapseButton.click();

    // Verify the properties panel collapsed — check computed width
    const widthAfter = await page.evaluate(() => {
      const panel = document.querySelector('#properties');
      return panel ? (panel as HTMLElement).getBoundingClientRect().width : -1;
    });
    expect(widthAfter, 'Properties panel should be collapsed (near 0 width)').toBeLessThan(5);

    // Palette and Canvas should still be visible
    await expect(page.getByRole('heading', { name: 'Components' })).toBeVisible();

    // Expand the properties by clicking the toggle button in the toolbar
    const expandButton = page.locator('button[title="Toggle properties panel"]');
    await expandButton.click();

    // Properties should expand back to a meaningful width
    const widthExpanded = await page.evaluate(() => {
      const panel = document.querySelector('#properties');
      return panel ? (panel as HTMLElement).getBoundingClientRect().width : -1;
    });
    expect(widthExpanded, 'Properties panel should be expanded again').toBeGreaterThan(50);
  });
});
