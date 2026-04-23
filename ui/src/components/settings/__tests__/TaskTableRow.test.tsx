import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router';
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import { Task } from '../../../types/knowledge';
import { TaskTableRow } from '../TaskTableRow';

// Mock the API
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getTask: vi.fn(),
    getTaskSchedule: vi.fn(),
    checkTaskDeletable: vi.fn(),
  },
}));

// Create a stable runSafe implementation that executes the promise
const mockRunSafe = async <T,>(promise: Promise<T>) => {
  try {
    const result = await promise;
    return [result, undefined] as [T, undefined];
  } catch (error) {
    return [undefined, error] as [undefined, unknown];
  }
};

// Mock the error handler hook with a stable reference
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: vi.fn(() => ({
    runSafe: mockRunSafe,
    error: null,
    handleError: vi.fn(),
    clearError: vi.fn(),
    createContext: vi.fn(),
  })),
}));

// Mock the user display hook to return the userId as-is
vi.mock('../../../hooks/useUserDisplay', () => ({
  useUserDisplay: (userId: string | undefined) => userId || 'Unknown',
}));

// Mock the task store
vi.mock('../../../store/taskStore', () => ({
  useTaskStore: vi.fn((selector) => {
    const state = { searchTerm: '' };
    return selector(state);
  }),
}));

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router', async () => {
  const actual = await vi.importActual('react-router');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('TaskTableRow Component', () => {
  const mockTask = {
    id: '00000001-0000-0000-0000-000000000001',
    name: 'Test Task',
    description: 'A test task for unit testing',
    function: 'summarization',
    created_by: 'test-user',
    visible: true,
    version: '1.0.0',
    scope: 'processing',
    status: 'enabled',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    knowledge_units: [{ id: 'ku-1', name: 'Test Directive', type: 'directive' }],
    knowledge_modules: [{ id: 'km-1', name: 'Test Module' }],
    data_samples: [{ input: 'test' }],
  } as unknown as Task;

  const mockProps = {
    task: mockTask,
    expanded: false,
    onToggleExpand: vi.fn<() => void>(),
    onDelete: undefined as ((id: string) => void) | undefined,
  };

  const renderComponent = (props: typeof mockProps = mockProps) => {
    return render(
      <BrowserRouter>
        <table>
          <tbody>
            <TaskTableRow {...props} />
          </tbody>
        </table>
      </BrowserRouter>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(backendApi.getTask).mockResolvedValue(mockTask);
  });

  describe('Collapsed row rendering', () => {
    it('renders the task name correctly', () => {
      renderComponent();
      expect(screen.getByText('Test Task')).toBeInTheDocument();
    });

    it('renders the task description correctly', () => {
      renderComponent();
      expect(screen.getByText('A test task for unit testing')).toBeInTheDocument();
    });

    it('renders the function badge correctly', () => {
      renderComponent();
      expect(screen.getByText('summarization')).toBeInTheDocument();
    });

    it('renders the scope badge correctly', () => {
      renderComponent();
      expect(screen.getByText('processing')).toBeInTheDocument();
    });

    it('renders the status badge correctly', () => {
      renderComponent();
      expect(screen.getByText('enabled')).toBeInTheDocument();
    });

    it('renders the version correctly', () => {
      renderComponent();
      expect(screen.getByText('1.0.0')).toBeInTheDocument();
    });

    it('renders the created_by correctly', () => {
      renderComponent();
      expect(screen.getByText('test-user')).toBeInTheDocument();
    });

    it('shows expand chevron icon', () => {
      renderComponent();
      expect(screen.getByLabelText('Expand row')).toBeInTheDocument();
    });

    it('renders the edit button (pink pencil icon)', () => {
      renderComponent();
      const editButton = screen.getByTitle('Open in Workbench');
      expect(editButton).toBeInTheDocument();
    });
  });

  describe('Row click behavior', () => {
    it('calls onToggleExpand when the row is clicked', () => {
      renderComponent();
      const row = screen.getByTestId(`task-row-${mockTask.id}`);
      fireEvent.click(row);
      expect(mockProps.onToggleExpand).toHaveBeenCalledTimes(1);
    });

    it('does not call onToggleExpand when edit button is clicked (stopPropagation)', () => {
      renderComponent();
      const editButton = screen.getByTitle('Open in Workbench');
      fireEvent.click(editButton);
      // Edit button should stop propagation, so onToggleExpand should not be called
      expect(mockProps.onToggleExpand).not.toHaveBeenCalled();
    });

    it('navigates to workbench when edit button is clicked', () => {
      renderComponent();
      const editButton = screen.getByTitle('Open in Workbench');
      fireEvent.click(editButton);
      expect(mockNavigate).toHaveBeenCalledWith('/workbench', {
        state: expect.objectContaining({
          taskId: mockTask.id,
          taskName: mockTask.name,
        }),
      });
    });
  });

  describe('Expanded row rendering', () => {
    it('shows collapse chevron when expanded', async () => {
      renderComponent({ ...mockProps, expanded: true });
      await waitFor(() => {
        expect(screen.getByLabelText('Collapse row')).toBeInTheDocument();
      });
    });

    it('displays expanded task details when expanded', async () => {
      renderComponent({ ...mockProps, expanded: true });

      await waitFor(() => {
        // Check for expanded section content
        expect(screen.getByText(/ID:/)).toBeInTheDocument();
        expect(screen.getByText(mockTask.id)).toBeInTheDocument();
      });
    });

    it('does not show large "Open in Workbench" text button in expanded section', async () => {
      renderComponent({ ...mockProps, expanded: true });

      await waitFor(() => {
        // The edit button in the row is for "Open in Workbench" but it's a small icon button (title only)
        // The large text button that says "Open in Workbench" was removed from expanded section
        // We verify by checking there's only one button with the "Open in Workbench" title (the icon button)
        const buttons = screen.queryAllByTitle('Open in Workbench');
        expect(buttons).toHaveLength(1); // Only the icon button in the row, not a text button in expanded
      });
    });

    it('displays knowledge units when available', async () => {
      renderComponent({ ...mockProps, expanded: true });

      await waitFor(() => {
        expect(screen.getByText('Knowledge Units:')).toBeInTheDocument();
        expect(screen.getByText(/Test Directive/)).toBeInTheDocument();
      });
    });

    it('displays knowledge modules when available', async () => {
      renderComponent({ ...mockProps, expanded: true });

      await waitFor(() => {
        expect(screen.getByText('Knowledge Modules:')).toBeInTheDocument();
        expect(screen.getByText('Test Module')).toBeInTheDocument();
      });
    });
  });

  describe('Different status colors', () => {
    it('applies correct color class for enabled status', () => {
      renderComponent();
      const statusBadge = screen.getByText('enabled');
      expect(statusBadge).toHaveClass('bg-green-100');
    });

    it('applies correct color class for disabled status', () => {
      const disabledTask = { ...mockTask, status: 'disabled' as const };
      renderComponent({ ...mockProps, task: disabledTask });
      const statusBadge = screen.getByText('disabled');
      expect(statusBadge).toHaveClass('bg-red-100');
    });
  });

  describe('Different function colors', () => {
    it('applies correct color class for summarization function', () => {
      renderComponent();
      const functionBadge = screen.getByText('summarization');
      expect(functionBadge).toHaveClass('bg-blue-100');
    });

    it('applies correct color class for extraction function', () => {
      const extractionTask = { ...mockTask, function: 'extraction' as const };
      renderComponent({ ...mockProps, task: extractionTask });
      const functionBadge = screen.getByText('extraction');
      expect(functionBadge).toHaveClass('bg-purple-100');
    });
  });

  describe('Different scope colors', () => {
    it('applies correct color class for processing scope', () => {
      renderComponent();
      const scopeBadge = screen.getByText('processing');
      expect(scopeBadge).toHaveClass('bg-violet-100');
    });

    it('applies correct color class for input scope', () => {
      const inputTask = { ...mockTask, scope: 'input' as const };
      renderComponent({ ...mockProps, task: inputTask });
      const scopeBadge = screen.getByText('input');
      expect(scopeBadge).toHaveClass('bg-teal-100');
    });

    it('applies correct color class for output scope', () => {
      const outputTask = { ...mockTask, scope: 'output' as const };
      renderComponent({ ...mockProps, task: outputTask });
      const scopeBadge = screen.getByText('output');
      expect(scopeBadge).toHaveClass('bg-amber-100');
    });
  });

  describe('N/A handling', () => {
    it('shows N/A when scope is undefined', () => {
      const noScopeTask = {
        ...mockTask,
        scope: undefined as unknown as 'input' | 'processing' | 'output',
      };
      renderComponent({ ...mockProps, task: noScopeTask });
      expect(screen.getByText('N/A')).toBeInTheDocument();
    });
  });

  describe('Schedule display in expanded row', () => {
    const scheduledTask = {
      ...mockTask,
      categories: ['health_monitoring', 'integration', 'scheduled'],
      schedule: null,
      last_run_at: null,
    } as unknown as Task;

    const mockScheduleEnabled = {
      id: 'sched-1',
      tenant_id: 'default',
      target_type: 'task',
      target_id: scheduledTask.id,
      schedule_type: 'every',
      schedule_value: '5m',
      timezone: 'UTC',
      enabled: true,
      params: null,
      origin_type: 'system',
      integration_id: 'splunk-main',
      next_run_at: '2026-04-02T10:00:00Z',
      last_run_at: '2026-04-02T09:55:00Z',
      created_at: '2026-04-01T00:00:00Z',
      updated_at: '2026-04-01T00:00:00Z',
    };

    const mockScheduleDisabled = {
      ...mockScheduleEnabled,
      enabled: false,
      next_run_at: null,
      last_run_at: null,
      integration_id: null,
    };

    it('fetches and displays schedule details when a scheduled task is expanded', async () => {
      vi.mocked(backendApi.getTask).mockResolvedValue(scheduledTask);
      vi.mocked(backendApi.getTaskSchedule).mockResolvedValue(mockScheduleEnabled);

      renderComponent({ ...mockProps, task: scheduledTask, expanded: true });

      await waitFor(() => {
        expect(backendApi.getTaskSchedule).toHaveBeenCalledWith(scheduledTask.id);
      });

      await waitFor(() => {
        expect(screen.getByText('Schedule:')).toBeInTheDocument();
        expect(screen.getByText('Every 5m')).toBeInTheDocument();
        expect(screen.getByText('Enabled')).toBeInTheDocument();
      });
    });

    it('shows next run and last run timestamps when available', async () => {
      vi.mocked(backendApi.getTask).mockResolvedValue(scheduledTask);
      vi.mocked(backendApi.getTaskSchedule).mockResolvedValue(mockScheduleEnabled);

      renderComponent({ ...mockProps, task: scheduledTask, expanded: true });

      await waitFor(() => {
        expect(screen.getByText('Next run:')).toBeInTheDocument();
        expect(screen.getByText('Last run:')).toBeInTheDocument();
      });
    });

    it('shows integration ID when schedule is linked to an integration', async () => {
      vi.mocked(backendApi.getTask).mockResolvedValue(scheduledTask);
      vi.mocked(backendApi.getTaskSchedule).mockResolvedValue(mockScheduleEnabled);

      renderComponent({ ...mockProps, task: scheduledTask, expanded: true });

      await waitFor(() => {
        expect(screen.getByText('Integration:')).toBeInTheDocument();
        expect(screen.getByText('splunk-main')).toBeInTheDocument();
      });
    });

    it('shows Disabled badge when schedule is not enabled', async () => {
      vi.mocked(backendApi.getTask).mockResolvedValue(scheduledTask);
      vi.mocked(backendApi.getTaskSchedule).mockResolvedValue(mockScheduleDisabled);

      renderComponent({ ...mockProps, task: scheduledTask, expanded: true });

      await waitFor(() => {
        expect(screen.getByText('Disabled')).toBeInTheDocument();
      });
    });

    it('does not fetch schedule for non-scheduled tasks', async () => {
      vi.mocked(backendApi.getTask).mockResolvedValue(mockTask);

      renderComponent({ ...mockProps, expanded: true });

      await waitFor(() => {
        expect(screen.getByText(/ID:/)).toBeInTheDocument();
      });

      expect(backendApi.getTaskSchedule).not.toHaveBeenCalled();
    });

    it('falls back to basic schedule display when API call fails', async () => {
      const taskWithScheduleString = {
        ...scheduledTask,
        schedule: '*/5 * * * *',
      } as unknown as Task;

      vi.mocked(backendApi.getTask).mockResolvedValue(taskWithScheduleString);
      vi.mocked(backendApi.getTaskSchedule).mockRejectedValue(new Error('Not found'));

      renderComponent({ ...mockProps, task: taskWithScheduleString, expanded: true });

      await waitFor(() => {
        expect(screen.getByText('Schedule:')).toBeInTheDocument();
        expect(screen.getByText('*/5 * * * *')).toBeInTheDocument();
      });
    });

    it('shows clock icon on collapsed row for scheduled tasks', () => {
      renderComponent({ ...mockProps, task: scheduledTask, expanded: false });
      expect(screen.getByLabelText('Scheduled task')).toBeInTheDocument();
    });

    it('does not show clock icon for non-scheduled tasks', () => {
      renderComponent({ ...mockProps, expanded: false });
      expect(screen.queryByLabelText('Scheduled task')).not.toBeInTheDocument();
    });
  });

  describe('Delete button functionality', () => {
    const DELETE_BUTTON_TITLE = 'Delete Task';

    it('renders delete button when onDelete prop is provided', () => {
      const onDelete = vi.fn();
      renderComponent({ ...mockProps, onDelete });
      const deleteButton = screen.getByTitle(DELETE_BUTTON_TITLE);
      expect(deleteButton).toBeInTheDocument();
    });

    it('does not render delete button when onDelete prop is not provided', () => {
      renderComponent({ ...mockProps });
      const deleteButton = screen.queryByTitle(DELETE_BUTTON_TITLE);
      expect(deleteButton).not.toBeInTheDocument();
    });

    it('does not call onToggleExpand when delete button is clicked (stopPropagation)', async () => {
      const user = userEvent.setup();
      const onDelete = vi.fn();
      vi.mocked(backendApi.checkTaskDeletable).mockResolvedValue({
        can_delete: true,
        reason: null,
        message: null,
      });

      renderComponent({ ...mockProps, onDelete });
      const deleteButton = screen.getByTitle(DELETE_BUTTON_TITLE);
      await user.click(deleteButton);

      // Delete button should stop propagation
      expect(mockProps.onToggleExpand).not.toHaveBeenCalled();
    });

    it('shows confirmation dialog when task can be deleted', async () => {
      const user = userEvent.setup();
      const onDelete = vi.fn();
      vi.mocked(backendApi.checkTaskDeletable).mockResolvedValue({
        can_delete: true,
        reason: null,
        message: null,
      });

      renderComponent({ ...mockProps, onDelete });
      const deleteButton = screen.getByTitle(DELETE_BUTTON_TITLE);
      await user.click(deleteButton);

      // Wait for the confirmation dialog to appear
      await waitFor(() => {
        expect(screen.getByText('Delete Task?')).toBeInTheDocument();
      });

      // Verify confirmation dialog content
      expect(screen.getByText(/Are you sure you want to delete "Test Task"\?/)).toBeInTheDocument();
    });

    it('shows "Cannot Delete" info dialog when task is in use', async () => {
      const user = userEvent.setup();
      const onDelete = vi.fn();
      vi.mocked(backendApi.checkTaskDeletable).mockResolvedValue({
        can_delete: false,
        reason: 'in_use',
        message: 'This task is used by 2 workflow(s): Workflow A, Workflow B.',
        workflows: [
          { id: '1', name: 'Workflow A' },
          { id: '2', name: 'Workflow B' },
        ],
      });

      renderComponent({ ...mockProps, onDelete });
      const deleteButton = screen.getByTitle(DELETE_BUTTON_TITLE);
      await user.click(deleteButton);

      // Wait for the info dialog to appear
      await waitFor(() => {
        expect(screen.getByText('Cannot Delete Task')).toBeInTheDocument();
      });

      // Verify info dialog content
      expect(screen.getByText(/This task is used by 2 workflow\(s\)/)).toBeInTheDocument();
    });

    it('shows delete confirmation when checkTaskDeletable API fails', async () => {
      const user = userEvent.setup();
      const onDelete = vi.fn();
      vi.mocked(backendApi.checkTaskDeletable).mockRejectedValue(new Error('Network error'));

      renderComponent({ ...mockProps, onDelete });
      const deleteButton = screen.getByTitle(DELETE_BUTTON_TITLE);
      await user.click(deleteButton);

      // Should still show the delete confirmation dialog despite API failure
      await waitFor(() => {
        expect(screen.getByText('Delete Task?')).toBeInTheDocument();
      });
    });

    it('calls onDelete when confirmation is accepted', async () => {
      const user = userEvent.setup();
      const onDelete = vi.fn();
      vi.mocked(backendApi.checkTaskDeletable).mockResolvedValue({
        can_delete: true,
        reason: null,
        message: null,
      });

      renderComponent({ ...mockProps, onDelete });
      const deleteButton = screen.getByTitle(DELETE_BUTTON_TITLE);
      await user.click(deleteButton);

      // Wait for the confirmation dialog
      await waitFor(() => {
        expect(screen.getByText('Delete Task?')).toBeInTheDocument();
      });

      // Click the Delete button in the dialog
      const confirmButton = screen.getByRole('button', { name: 'Delete' });
      await user.click(confirmButton);

      // Verify onDelete was called with the task id
      expect(onDelete).toHaveBeenCalledWith(mockTask.id);
    });

    it('does not call onDelete when confirmation is cancelled', async () => {
      const user = userEvent.setup();
      const onDelete = vi.fn();
      vi.mocked(backendApi.checkTaskDeletable).mockResolvedValue({
        can_delete: true,
        reason: null,
        message: null,
      });

      renderComponent({ ...mockProps, onDelete });
      const deleteButton = screen.getByTitle(DELETE_BUTTON_TITLE);
      await user.click(deleteButton);

      // Wait for the confirmation dialog
      await waitFor(() => {
        expect(screen.getByText('Delete Task?')).toBeInTheDocument();
      });

      // Click the Cancel button in the dialog
      const cancelButton = screen.getByRole('button', { name: 'Cancel' });
      await user.click(cancelButton);

      // Verify onDelete was NOT called
      expect(onDelete).not.toHaveBeenCalled();
    });
  });
});
