import { test, expect, type Page } from '@playwright/test';

/**
 * E2E Test: Task & Workflow Lifecycle
 *
 * End-to-end test that exercises the full lifecycle:
 * 1. Create Task A via the Workbench UI (simple Cy script, no integrations)
 * 2. Create Task B via the Workbench UI
 * 3. Create a workflow connecting A → B via the Workflow Builder
 * 4. Run the workflow and verify execution completes
 * 5. Delete the workflow
 * 6. Delete both tasks
 *
 * All interactions happen through the UI — no direct API calls for mutations.
 */

// Unique suffix to avoid name collisions across test runs
const TEST_ID = Date.now().toString(36);
const TASK_A_NAME = `E2E Task A ${TEST_ID}`;
const TASK_B_NAME = `E2E Task B ${TEST_ID}`;
const WORKFLOW_NAME = `E2E Workflow ${TEST_ID}`;

// Simple Cy scripts that work without any integrations
const TASK_A_SCRIPT = `result = {"source": "task_a", "message": "hello from task A"}
return result`;

const TASK_B_SCRIPT = `result = {"source": "task_b", "received": input}
return result`;

/**
 * Click an SVG node on the Reaflow canvas by name.
 *
 * Dispatches a click directly on the node's <rect> element rather than using
 * page.mouse.click at screen coordinates. SVG hit-testing with overlapping
 * <g> groups (due to Reaflow ports/labels extending beyond the visible rect)
 * can route coordinate-based clicks to the wrong node. Dispatching directly
 * on the element ensures the event bubbles through the correct <g> parent
 * to trigger the right onClick handler.
 */
async function clickCanvasNode(page: Page, nodeName: string): Promise<void> {
  const found = await page.evaluate((name: string) => {
    const foreignObjects = document.querySelectorAll('foreignObject');
    for (const fo of foreignObjects) {
      if (!fo.textContent?.includes(name)) continue;
      const rect = fo.parentElement?.querySelector(':scope > rect');
      if (rect) {
        const bounds = rect.getBoundingClientRect();
        rect.dispatchEvent(
          new MouseEvent('click', {
            bubbles: true,
            cancelable: true,
            clientX: bounds.x + bounds.width / 2,
            clientY: bounds.y + bounds.height / 2,
            view: window,
          })
        );
        return true;
      }
    }
    return false;
  }, nodeName);

  if (!found) throw new Error(`Canvas node "${nodeName}" not found on the canvas`);
}

/**
 * Set the Ace Editor content by using its JavaScript API.
 * More reliable than trying to type into the editor DOM.
 */
async function setAceEditorContent(page: Page, content: string): Promise<void> {
  await page.locator('.ace_editor').waitFor({ timeout: 10_000 });
  await page.evaluate((script) => {
    const editorEl = document.querySelector('.ace_editor') as HTMLElement & {
      env?: { editor?: { setValue(val: string, cursorPos?: number): void } };
    };
    editorEl?.env?.editor?.setValue(script, -1);
  }, content);
  // Brief pause to let React state sync with the Ace editor change event
  await expect(page.locator('.ace_editor')).toBeVisible();
}

/**
 * Get the current Ace Editor content
 */
async function getAceEditorContent(page: Page): Promise<string> {
  return page.evaluate(() => {
    const editorEl = document.querySelector('.ace_editor') as HTMLElement & {
      env?: { editor?: { getValue(): string } };
    };
    return editorEl?.env?.editor?.getValue() ?? '';
  });
}

/**
 * Create a task via the Workbench UI.
 * Navigates to /workbench, writes the Cy script, clicks "Save As...",
 * fills in the name, and saves.
 */
async function createTaskViaUI(page: Page, taskName: string, script: string): Promise<void> {
  // Navigate to workbench (Tasks tab)
  await page.goto('/workbench?tab=execute');
  await expect(page.getByRole('heading', { name: 'Code Editor' })).toBeVisible({
    timeout: 15_000,
  });

  // Write the Cy script into the Ace editor
  await setAceEditorContent(page, script);

  // Verify the script was written
  const editorContent = await getAceEditorContent(page);
  expect(editorContent).toContain(script.split('\n')[0]);

  // Click "Save As..." button
  await page.getByRole('button', { name: 'Save As...' }).click();

  // Wait for the Save As modal to appear
  await expect(page.getByText('Save As New Task')).toBeVisible({ timeout: 5_000 });

  // Fill in the task name
  await page.locator('#task-name').fill(taskName);

  // Fill in a description
  await page
    .locator('#task-description')
    .fill(`E2E test task created at ${new Date().toISOString()}`);

  // Click Save and wait for the modal to close (the modal closes on success).
  // We wait on the UI outcome rather than the raw HTTP response so this is
  // resilient to slow backend responses under parallel test load.
  const dialog = page.locator('[role="dialog"]');
  const saveButton = dialog.getByRole('button', { name: 'Save', exact: true });
  await expect(saveButton).toBeEnabled({ timeout: 5_000 });
  await saveButton.click();

  // Modal closes on success; long timeout accommodates a loaded backend
  await expect(page.getByText('Save As New Task')).not.toBeVisible({ timeout: 60_000 });
}

/**
 * Delete a task via the Tasks settings page.
 * Searches for the task by name, clicks the trash icon, and confirms.
 */
async function deleteTaskViaUI(page: Page, taskName: string): Promise<void> {
  await page.goto('/tasks');
  await expect(page.getByRole('heading', { name: 'Tasks' })).toBeVisible({ timeout: 10_000 });

  // Wait for tasks to load by checking the table is populated
  await expect(page.locator('tr[data-testid]').first()).toBeVisible({ timeout: 10_000 });

  // Search for the task and wait for the search API call to fully settle.
  // The search triggers a fetchTasks() API call that re-renders the row list.
  // If we click the trash button before the API response arrives, the row
  // re-mounts on response and the pending delete dialog state is lost.
  const searchInput = page.getByPlaceholder('Search tasks by name, description, or function...');
  await searchInput.fill(taskName);

  // Wait for the specific task row to appear after filtering
  const taskRow = page.locator('tr[data-testid]').filter({ hasText: taskName }).first();
  await expect(taskRow).toBeVisible({ timeout: 10_000 });

  // Wait for the search API call to complete so rows are stable
  await page.waitForLoadState('networkidle');

  // Click the delete (trash) button in the task row
  const trashButton = taskRow.locator('button[title="Delete Task"]');
  await expect(trashButton).toBeVisible({ timeout: 5_000 });
  await expect(trashButton).toBeEnabled({ timeout: 5_000 });
  await trashButton.click();

  // Wait for either the delete confirmation or "cannot delete" dialog.
  // The trash button triggers an async checkTaskDeletable API call before
  // showing any dialog, so allow generous time for the API response.
  const deleteDialogTitle = page.getByText('Delete Task?');
  const cannotDeleteTitle = page.getByText('Cannot Delete Task');
  await expect(deleteDialogTitle.or(cannotDeleteTitle)).toBeVisible({ timeout: 30_000 });

  if (await deleteDialogTitle.isVisible()) {
    // Click the "Delete" button within the dialog panel
    const dialog = page.locator('[role="dialog"]');
    await dialog.getByRole('button', { name: 'Delete' }).click({ timeout: 5_000 });
    // Wait for row to disappear (confirms API deletion completed)
    await expect(taskRow).not.toBeVisible({ timeout: 15_000 });
  } else {
    // "Cannot Delete Task" info dialog — dismiss and throw so the test fails
    const okButton = page.getByRole('button', { name: 'OK' });
    await okButton.click();
    throw new Error(`Task "${taskName}" cannot be deleted — it may still be used in a workflow`);
  }
}

test.describe('Task & Workflow Lifecycle', () => {
  // This is a long multi-step test — give it extra time
  test.setTimeout(180_000);

  test('full lifecycle: create tasks → build workflow → run → verify → cleanup', async ({
    page,
  }) => {
    // Allow extra time for the multi-step test
    test.slow();

    // =============================================
    // STEP 1: Create Task A
    // =============================================
    await test.step('Create Task A via Workbench', async () => {
      await createTaskViaUI(page, TASK_A_NAME, TASK_A_SCRIPT);
    });

    // =============================================
    // STEP 2: Create Task B
    // =============================================
    await test.step('Create Task B via Workbench', async () => {
      await createTaskViaUI(page, TASK_B_NAME, TASK_B_SCRIPT);
    });

    // =============================================
    // STEP 3: Create a Workflow connecting A → B
    // =============================================
    await test.step('Create workflow connecting Task A → Task B', async () => {
      // Navigate to Workbench → Workflows tab
      await page.goto('/workbench?tab=builder');

      // Wait for the workflow builder to load (palette heading appears)
      await expect(page.getByRole('heading', { name: 'Components' })).toBeVisible({
        timeout: 10_000,
      });

      // Click "New" to ensure we start with a clean canvas
      const newButton = page.getByRole('button', { name: 'New' }).first();
      const newButtonVisible = await newButton.isVisible({ timeout: 5_000 }).catch(() => false);
      if (newButtonVisible) {
        await newButton.click();
        // If there's a discard confirmation, confirm it
        const discardButton = page.getByRole('button', { name: 'Discard Changes' });
        const hasDiscard = await discardButton.isVisible({ timeout: 2_000 }).catch(() => false);
        if (hasDiscard) {
          await discardButton.click();
        }
      }

      // Set workflow name (use exact match — there are two name inputs on the page)
      const nameInput = page.getByPlaceholder('Workflow name...', { exact: true });
      await expect(nameInput).toBeVisible({ timeout: 5_000 });
      await nameInput.fill(WORKFLOW_NAME);

      // Wait for the palette to load tasks (search input should be interactive)
      const paletteSearch = page.getByPlaceholder('Search components...');
      await expect(paletteSearch).toBeVisible({ timeout: 5_000 });

      // Wait for the task list to finish loading before searching.
      // Under parallel load, the tasks API can be slow to respond.
      await expect(page.getByText('Loading tasks...')).not.toBeVisible({ timeout: 30_000 });

      // Search for Task A in the palette and click to add
      await paletteSearch.fill(TASK_A_NAME);

      // Click on Task A in the palette to add it to the canvas
      const taskAButton = page.getByRole('button', { name: TASK_A_NAME }).first();
      await expect(taskAButton).toBeVisible({ timeout: 10_000 });
      await taskAButton.click();

      // Clear search and find Task B
      await paletteSearch.clear();
      await paletteSearch.fill(TASK_B_NAME);

      // Click on Task B in the palette to add it to the canvas
      const taskBButton = page.getByRole('button', { name: TASK_B_NAME }).first();
      await expect(taskBButton).toBeVisible({ timeout: 10_000 });
      await taskBButton.click();

      // Clear the palette search
      await paletteSearch.clear();

      // Now connect Task A → Task B
      // Strategy: Click Task A to select it, enter connect mode, click Task B

      // Click Task A on the canvas to select it
      await clickCanvasNode(page, TASK_A_NAME);

      // Enter connect mode — with Task A selected, it becomes the source
      const connectButton = page.locator('button[title="Connect Nodes (C)"]');
      await expect(connectButton).toBeVisible({ timeout: 5_000 });
      await connectButton.click();

      // We should now be in connect mode — either waiting for source or target
      const targetPrompt = page.getByText('Click target node to connect');
      const sourcePrompt = page.getByText('Click source node first');

      // Wait for either prompt to appear (connect mode is active)
      await expect(targetPrompt.or(sourcePrompt)).toBeVisible({ timeout: 5_000 });

      if (await targetPrompt.isVisible()) {
        // Task A was auto-selected as source, click Task B as target
        await clickCanvasNode(page, TASK_B_NAME);
      } else {
        // Need to click source first, then target
        await clickCanvasNode(page, TASK_A_NAME);
        // After selecting source, wait for the target prompt
        await expect(targetPrompt).toBeVisible({ timeout: 3_000 });
        await clickCanvasNode(page, TASK_B_NAME);
      }

      // Verify connect mode exited (banner disappears after edge creation)
      await expect(targetPrompt).not.toBeVisible({ timeout: 5_000 });
      await expect(sourcePrompt).not.toBeVisible({ timeout: 5_000 });

      // Save the workflow
      const saveButton = page.getByRole('button', { name: 'Save Workflow' });
      await expect(saveButton).toBeVisible({ timeout: 5_000 });
      await saveButton.click();

      // Verify we navigated to the workflow detail page after save.
      // Under parallel test load, the save API can take 30s+.
      await expect(page).toHaveURL(/\/workflows\//, { timeout: 30_000 });
    });

    // =============================================
    // STEP 4: Run the workflow
    // =============================================
    let workflowRunUrl: string | null = null;

    await test.step('Run the workflow from Workflows list', async () => {
      // Navigate to workflows list page
      await page.goto('/workflows');
      await expect(page.getByRole('heading', { name: 'Workflows' })).toBeVisible({
        timeout: 10_000,
      });

      // Find our workflow's row (allow extra time for API response under load)
      const workflowRow = page.locator('tr').filter({ hasText: WORKFLOW_NAME }).first();
      await expect(workflowRow).toBeVisible({ timeout: 15_000 });

      // Click the Run button for this workflow
      const runButton = workflowRow.getByRole('button', { name: 'Run' });
      await expect(runButton).toBeVisible();
      await runButton.click();

      // Wait for the execution dialog to appear
      await expect(page.getByRole('heading', { name: 'Execute Workflow' })).toBeVisible({
        timeout: 5_000,
      });

      // The input textarea should have some content (auto-generated from schema)
      const inputTextarea = page.getByPlaceholder('Enter JSON input data...');
      await expect(inputTextarea).toBeVisible();

      // Make sure the input is valid JSON — set a simple input
      await inputTextarea.fill('{"test": true}');

      // Click "Start Execution"
      const startButton = page.getByRole('button', { name: /Start Execution/ });
      await expect(startButton).toBeEnabled({ timeout: 3_000 });
      await startButton.click();

      // Should navigate to the workflow run page /workflow-runs/:runId
      // Under parallel load, the execute API can take 30s+.
      await expect(page).toHaveURL(/\/workflow-runs\//, { timeout: 30_000 });
      workflowRunUrl = page.url();
    });

    // =============================================
    // STEP 5: Verify the workflow execution completes
    // =============================================
    await test.step('Verify workflow execution completes', async () => {
      // We should already be on the workflow run page
      expect(workflowRunUrl).toBeTruthy();

      // Wait for the status to show "Completed" (may take time for execution)
      await expect(page.getByText('Completed', { exact: true }).first()).toBeVisible({
        timeout: 60_000,
      });

      // Verify the workflow name is shown
      await expect(page.getByText(WORKFLOW_NAME).first()).toBeVisible();
    });

    // =============================================
    // STEP 6: Delete the workflow
    // =============================================
    await test.step('Delete the workflow', async () => {
      // Navigate to workflows list
      await page.goto('/workflows');
      await expect(page.getByRole('heading', { name: 'Workflows' })).toBeVisible({
        timeout: 10_000,
      });

      // Find the workflow row
      const workflowRow = page.locator('tr').filter({ hasText: WORKFLOW_NAME }).first();
      await expect(workflowRow).toBeVisible({ timeout: 10_000 });

      // Click the overflow menu (⋮) button
      const overflowButton = workflowRow.locator('button[title="More actions"]');
      await overflowButton.click();

      // Click "Delete" in the overflow menu
      const deleteMenuItem = page.getByRole('button', { name: 'Delete' }).last();
      await expect(deleteMenuItem).toBeVisible({ timeout: 3_000 });
      await deleteMenuItem.click();

      // Confirm deletion in the dialog
      await expect(page.getByText('Delete Workflow?')).toBeVisible({ timeout: 3_000 });
      const confirmDeleteButton = page.getByRole('button', { name: 'Delete' }).last();
      await confirmDeleteButton.click();

      // Verify the workflow is no longer in the list (allow extra time for API + re-render)
      const deletedRow = page.locator('tr').filter({ hasText: WORKFLOW_NAME });
      await expect(deletedRow).not.toBeVisible({ timeout: 15_000 });
    });

    // =============================================
    // STEP 7: Delete Task A
    // =============================================
    await test.step('Delete Task A', async () => {
      await deleteTaskViaUI(page, TASK_A_NAME);
    });

    // =============================================
    // STEP 8: Delete Task B
    // =============================================
    await test.step('Delete Task B', async () => {
      await deleteTaskViaUI(page, TASK_B_NAME);
    });
  });
});
