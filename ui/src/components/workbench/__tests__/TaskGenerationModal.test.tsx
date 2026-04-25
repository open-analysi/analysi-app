import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import type { Task } from '../../../types/knowledge';
import type { TaskBuildingRun } from '../../../types/taskRun';
import { TaskGenerationModal } from '../TaskGenerationModal';

// Mock scrollIntoView for jsdom
Element.prototype.scrollIntoView = vi.fn();

// Mock the backendApi
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getAlerts: vi.fn(),
    createTaskGeneration: vi.fn(),
    getTaskGeneration: vi.fn(),
    getTask: vi.fn(),
    getTasks: vi.fn(),
  },
}));

const mockGetAlerts = vi.mocked(backendApi.getAlerts);
const mockCreateTaskGeneration = vi.mocked(backendApi.createTaskGeneration);
const mockGetTaskGeneration = vi.mocked(backendApi.getTaskGeneration);
const mockGetTask = vi.mocked(backendApi.getTask);
const mockGetTasks = vi.mocked(backendApi.getTasks);

const TASK_NAME = 'VirusTotal: Domain Reputation Analysis';
const CREATE_TASK_MESSAGE = 'Tool call: mcp__cy-script-assistant__create_task';
const TEST_TASK_ID = 'task-abc';
const TEST_TASK_NAME = 'My Test Task';
const TEST_CREATED_AT = '2026-02-23T05:54:00Z';

describe('TaskGenerationModal', () => {
  const onClose = vi.fn();
  const onComplete = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });

    // Default: alerts endpoint returns empty
    mockGetAlerts.mockResolvedValue({ alerts: [], total: 0 });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const renderModal = (props?: { taskId?: string | null; taskName?: string | null }) =>
    render(
      <TaskGenerationModal
        isOpen={true}
        onClose={onClose}
        onComplete={onComplete}
        taskId={props?.taskId}
        taskName={props?.taskName}
      />
    );

  // ─── Mode selector (create vs improve) ─────────────────────────────

  describe('mode selector', () => {
    it('does not show mode selector when no taskId is provided', async () => {
      renderModal();
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(screen.queryByRole('button', { name: /Create New Task/ })).not.toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: /Improve Current Task/ })
      ).not.toBeInTheDocument();
    });

    it('shows mode selector when taskId is provided', async () => {
      renderModal({ taskId: TEST_TASK_ID, taskName: TEST_TASK_NAME });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      expect(screen.getByRole('button', { name: /Create New Task/ })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Improve Current Task/ })).toBeInTheDocument();
    });

    it('defaults to create mode even when task is loaded', async () => {
      renderModal({ taskId: TEST_TASK_ID, taskName: TEST_TASK_NAME });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // Create button should be active (purple border)
      const createBtn = screen.getByRole('button', { name: /Create New Task/ });
      expect(createBtn.className).toContain('border-purple-600');

      // Subtitle should say "create" (the <p> subtitle element)
      expect(
        screen.getAllByText('Describe the task you want to create').length
      ).toBeGreaterThanOrEqual(1);
    });

    it('switches to improve mode and updates labels', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderModal({ taskId: TEST_TASK_ID, taskName: TEST_TASK_NAME });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // Click "Improve Current Task"
      await user.click(screen.getByRole('button', { name: /Improve Current Task/ }));

      // Improve button should now be active
      const improveBtn = screen.getByRole('button', { name: /Improve Current Task/ });
      expect(improveBtn.className).toContain('border-purple-600');

      // Subtitle should reference the task name
      expect(
        screen.getByText(new RegExp(`Describe what to change about "${TEST_TASK_NAME}"`))
      ).toBeInTheDocument();

      // Task name indicator should be visible
      expect(screen.getByText(TEST_TASK_NAME)).toBeInTheDocument();
      expect(screen.getByText(/Improving:/)).toBeInTheDocument();

      // Description label should update
      expect(screen.getByText('Describe what you want to change')).toBeInTheDocument();

      // Generate button should say "Improve Task"
      expect(screen.getByRole('button', { name: /Improve Task/ })).toBeInTheDocument();
    });

    it('does not show task name indicator in create mode', async () => {
      renderModal({ taskId: TEST_TASK_ID, taskName: TEST_TASK_NAME });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // In create mode (default), the "Improving:" indicator should not be shown
      expect(screen.queryByText(/Improving:/)).not.toBeInTheDocument();
    });

    it('hides example prompts in improve mode', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderModal({ taskId: TEST_TASK_ID, taskName: TEST_TASK_NAME });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // In create mode, example prompts toggle should be visible
      expect(screen.getByText(/Example Prompts/)).toBeInTheDocument();

      // Switch to improve mode
      await user.click(screen.getByRole('button', { name: /Improve Current Task/ }));

      // Example prompts should be hidden
      expect(screen.queryByText(/Example Prompts/)).not.toBeInTheDocument();
    });

    it('sends task_id in improve mode when generating', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      mockCreateTaskGeneration.mockResolvedValue({
        id: 'gen-improve-1',
        status: 'pending',
        description: 'test',
        created_at: TEST_CREATED_AT,
      });
      mockGetTaskGeneration.mockResolvedValue({
        id: 'gen-improve-1',
        status: 'in_progress',
        progress_messages: [],
      } as unknown as TaskBuildingRun);

      renderModal({ taskId: 'task-to-improve', taskName: 'Task To Improve' });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // Switch to improve mode
      await user.click(screen.getByRole('button', { name: /Improve Current Task/ }));

      // Type description
      const textarea = screen.getByPlaceholderText(/Example: Add error handling/);
      await user.type(textarea, 'Add better error handling for edge cases');

      // Click Improve Task
      await user.click(screen.getByRole('button', { name: /Improve Task/ }));

      expect(mockCreateTaskGeneration).toHaveBeenCalledWith(
        expect.objectContaining({
          task_id: 'task-to-improve',
          description: 'Add better error handling for edge cases',
        })
      );
    });

    it('does NOT send task_id in create mode even when task is loaded', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      mockCreateTaskGeneration.mockResolvedValue({
        id: 'gen-create-1',
        status: 'pending',
        description: 'test',
        created_at: TEST_CREATED_AT,
      });
      mockGetTaskGeneration.mockResolvedValue({
        id: 'gen-create-1',
        status: 'in_progress',
        progress_messages: [],
      } as unknown as TaskBuildingRun);

      renderModal({ taskId: 'task-loaded', taskName: 'Loaded Task' });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });

      // Stay in create mode (default)
      const textarea = screen.getByPlaceholderText(/Example: Create a task/);
      await user.type(textarea, 'Create a brand new task from scratch');

      await user.click(screen.getByRole('button', { name: /Generate Task/ }));

      expect(mockCreateTaskGeneration).toHaveBeenCalledWith(
        expect.objectContaining({
          description: 'Create a brand new task from scratch',
        })
      );
      // task_id should NOT be in the request
      expect(mockCreateTaskGeneration).not.toHaveBeenCalledWith(
        expect.objectContaining({ task_id: expect.anything() })
      );
    });
  });

  // ─── Task ID resolution after generation ────────────────────────────

  describe('task ID resolution after generation', () => {
    it('should use the correct task when result.task_id matches the generated task name', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      // Step 1: createTaskGeneration returns a generation run ID
      mockCreateTaskGeneration.mockResolvedValue({
        id: 'gen-123',
        status: 'pending',
        description: 'test',
        created_at: TEST_CREATED_AT,
      });

      // Step 2: First poll returns in_progress
      // Step 3: Second poll returns completed with correct task_id
      const completedResponse = {
        id: 'gen-123',
        status: 'completed',
        progress_messages: [
          {
            timestamp: '2026-02-23T05:54:49Z',
            message: CREATE_TASK_MESSAGE,
            level: 'info',
            details: {
              input: {
                name: TASK_NAME,
                script: 'result = input\nreturn result',
              },
            },
          },
        ],
        result: {
          task_id: 'correct-task-id',
          cy_name: 'virustotal_domain_reputation_analysis',
        },
      };

      mockGetTaskGeneration
        .mockResolvedValueOnce({
          id: 'gen-123',
          status: 'in_progress',
          progress_messages: [],
        } as unknown as TaskBuildingRun)
        .mockResolvedValueOnce(completedResponse as unknown as TaskBuildingRun);

      // The task fetched by result.task_id matches the expected name — correct!
      mockGetTask.mockResolvedValue({
        id: 'correct-task-id',
        name: TASK_NAME,
        cy_name: 'virustotal_domain_reputation_analysis',
        script: 'result = input\nreturn result',
      } as unknown as Task);

      renderModal();

      // Type a description
      const textarea = screen.getByPlaceholderText(/Example: Create a task/);
      await user.type(textarea, 'Create a task that checks domain reputation');

      // Click Generate
      const generateButton = screen.getByRole('button', { name: /Generate Task/ });
      await user.click(generateButton);

      // Advance through polling intervals
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });

      // Wait for completion and the "Open in Editor" button
      await waitFor(
        () => {
          expect(screen.getByRole('button', { name: /Open in Editor/ })).toBeInTheDocument();
        },
        { timeout: 5000 }
      );

      // Click "Open in Editor"
      const openButton = screen.getByRole('button', { name: /Open in Editor/ });
      await user.click(openButton);

      // Verify onComplete was called with the correct task ID
      expect(onComplete).toHaveBeenCalledWith(
        'correct-task-id',
        'virustotal_domain_reputation_analysis'
      );
    });

    it('should resolve the correct task when result.task_id points to wrong task (concurrent creation bug)', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      mockCreateTaskGeneration.mockResolvedValue({
        id: 'gen-456',
        status: 'pending',
        description: 'test',
        created_at: TEST_CREATED_AT,
      });

      // Backend returns WRONG task_id due to concurrent creation race condition
      const completedResponse = {
        id: 'gen-456',
        status: 'completed',
        progress_messages: [
          {
            timestamp: '2026-02-23T05:54:49Z',
            message: CREATE_TASK_MESSAGE,
            level: 'info',
            details: {
              input: {
                name: TASK_NAME,
                script: 'result = input\nreturn result',
              },
            },
          },
        ],
        result: {
          // WRONG! This is an E2E test task that was created concurrently
          task_id: 'wrong-e2e-task-id',
          cy_name: 'e2e_task_b_mlyrjybg',
        },
      };

      mockGetTaskGeneration.mockResolvedValueOnce(completedResponse as unknown as TaskBuildingRun);

      // The task at result.task_id is the WRONG one (E2E test task)
      mockGetTask.mockResolvedValue({
        id: 'wrong-e2e-task-id',
        name: 'E2E Task B mlyrjybg',
        cy_name: 'e2e_task_b_mlyrjybg',
        script: 'result = {"source": "task_b"}\nreturn result',
      } as unknown as Task);

      // Search by name should find the correct task
      mockGetTasks.mockResolvedValue({
        tasks: [
          {
            id: 'correct-vt-task-id',
            name: TASK_NAME,
            cy_name: 'virustotal_domain_reputation_analysis',
            created_at: '2026-02-23T05:56:10Z',
          } as unknown as Task,
        ],
        total: 1,
      });

      renderModal();

      // Type a description
      const textarea = screen.getByPlaceholderText(/Example: Create a task/);
      await user.type(textarea, 'Create a task that checks domain reputation');

      // Click Generate
      const generateButton = screen.getByRole('button', { name: /Generate Task/ });
      await user.click(generateButton);

      // Advance through polling
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });

      // Wait for completion
      await waitFor(
        () => {
          expect(screen.getByRole('button', { name: /Open in Editor/ })).toBeInTheDocument();
        },
        { timeout: 5000 }
      );

      // Click "Open in Editor"
      const openButton = screen.getByRole('button', { name: /Open in Editor/ });
      await user.click(openButton);

      // onComplete should be called with the CORRECT task ID,
      // not the wrong one from result.task_id
      expect(onComplete).toHaveBeenCalledWith(
        'correct-vt-task-id',
        expect.any(String) // cy_name
      );

      // It should NOT have been called with the wrong task ID
      expect(onComplete).not.toHaveBeenCalledWith('wrong-e2e-task-id', expect.any(String));
    });

    it('should fall back to result.task_id when no create_task calls found in progress messages', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      mockCreateTaskGeneration.mockResolvedValue({
        id: 'gen-789',
        status: 'pending',
        description: 'test',
        created_at: TEST_CREATED_AT,
      });

      // Generation completed but no create_task progress messages (edge case)
      const completedResponse = {
        id: 'gen-789',
        status: 'completed',
        progress_messages: [
          {
            timestamp: '2026-02-23T05:54:49Z',
            message: 'Some other tool call',
            level: 'info',
          },
        ],
        result: {
          task_id: 'fallback-task-id',
          cy_name: 'some_task',
        },
      };

      mockGetTaskGeneration.mockResolvedValueOnce(completedResponse as unknown as TaskBuildingRun);

      // Even though we can't verify, the task exists
      mockGetTask.mockResolvedValue({
        id: 'fallback-task-id',
        name: 'Some Task',
        cy_name: 'some_task',
        script: 'return input',
      } as unknown as Task);

      renderModal();

      const textarea = screen.getByPlaceholderText(/Example: Create a task/);
      await user.type(textarea, 'Create a task for something');

      const generateButton = screen.getByRole('button', { name: /Generate Task/ });
      await user.click(generateButton);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(2100);
      });

      await waitFor(
        () => {
          expect(screen.getByRole('button', { name: /Open in Editor/ })).toBeInTheDocument();
        },
        { timeout: 5000 }
      );

      const openButton = screen.getByRole('button', { name: /Open in Editor/ });
      await user.click(openButton);

      // Should fall back to result.task_id when we can't verify
      expect(onComplete).toHaveBeenCalledWith('fallback-task-id', 'some_task');
    });
  });
});
