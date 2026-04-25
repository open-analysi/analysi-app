import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { TaskRun } from '../../../types/taskRun';
import { TaskRunList } from '../TaskRunList';

// Mock react-router
const mockNavigate = vi.fn();
vi.mock('react-router', () => ({
  useNavigate: () => mockNavigate,
}));

// Mock the formatUtils
vi.mock('../../../utils/formatUtils', () => ({
  formatBytes: (bytes: number) => `${bytes} bytes`,
  formatDuration: (duration: string) => {
    const match = /PT(\d+(?:\.\d+)?)S/.exec(duration);
    return match ? `${match[1]}s` : duration;
  },
  getDurationColorClass: () => 'text-green-400',
}));

// Mock backendApi
const mockGetTask = vi.fn();
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getTask: (...args: unknown[]) => mockGetTask(...args),
    getAlert: vi.fn().mockResolvedValue(null),
    getWorkflowRun: vi.fn().mockResolvedValue(null),
    getWorkflow: vi.fn().mockResolvedValue(null),
  },
}));

// Mock componentStyles
vi.mock('../../../styles/components', () => ({
  componentStyles: {
    tableHeader: 'mock-table-header',
    tableHeaderCell: 'mock-table-header-cell',
    tableBody: 'mock-table-body',
    tableRow: 'mock-table-row',
    tableCell: 'mock-table-cell',
  },
}));

const VIEW_DETAILS = 'View Details';
const REGULAR_TASK = 'Regular Task';
const TASK_ID_1 = 'task-id-1';
const OPEN_IN_WORKBENCH_TITLE = 'Open this task in Workbench with the same input';
const OPEN_IN_WORKBENCH = 'Open in Workbench';

describe('TaskRunList', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetTask.mockReset();
    // Default: task exists
    mockGetTask.mockResolvedValue({ id: TASK_ID_1, task_name: 'Some Task' });
  });

  const mockTaskRuns: TaskRun[] = [
    {
      id: 'task-1',
      tenant_id: 'tenant-1',
      task_id: TASK_ID_1,
      task_name: REGULAR_TASK,
      status: 'completed',
      duration: 'PT3.2S',
      started_at: '2025-08-23T16:52:01.000Z',
      completed_at: '2025-08-23T16:52:04.200Z',
      input_type: 'inline',
      input_location: '{"test": "input data"}',
      input_content_type: 'application/json',
      output_type: 'inline',
      output_location: '{"result": "success"}',
      output_content_type: 'application/json',
      created_at: '2025-08-23T16:52:00.000Z',
      updated_at: '2025-08-23T16:52:04.200Z',
    },
    {
      id: 'adhoc-task-1',
      tenant_id: 'tenant-1',
      task_id: undefined,
      task_name: 'Ad Hoc Script',
      cy_script: 'return "Hello from Ad Hoc"',
      status: 'completed',
      duration: 'PT2.1S',
      started_at: '2025-08-23T17:00:00.000Z',
      completed_at: '2025-08-23T17:00:02.100Z',
      input_type: 'inline',
      input_location: '{"ad_hoc": "input"}',
      input_content_type: 'application/json',
      output_type: 'inline',
      output_location: '{"result": "ad hoc output"}',
      output_content_type: 'application/json',
      created_at: '2025-08-23T17:00:00.000Z',
      updated_at: '2025-08-23T17:00:02.100Z',
    },
  ];

  it('renders task runs correctly', () => {
    render(<TaskRunList taskRuns={mockTaskRuns} />);

    expect(screen.getByText(REGULAR_TASK)).toBeInTheDocument();
    expect(screen.getByText('Ad Hoc Script')).toBeInTheDocument();
  });

  it('shows Open in Workbench button for regular tasks', () => {
    render(<TaskRunList taskRuns={[mockTaskRuns[0]]} />);

    // Click View Details to expand
    const viewDetailsButton = screen.getByText(VIEW_DETAILS);
    fireEvent.click(viewDetailsButton);

    // Check for Open in Workbench button
    const openInWorkbenchButton = screen.getByTitle(OPEN_IN_WORKBENCH_TITLE);
    expect(openInWorkbenchButton).toBeInTheDocument();
    expect(openInWorkbenchButton.textContent).toContain(OPEN_IN_WORKBENCH);
  });

  it('shows Open in Workbench button for Ad Hoc tasks', () => {
    render(<TaskRunList taskRuns={[mockTaskRuns[1]]} />);

    // Click View Details to expand
    const viewDetailsButton = screen.getByText(VIEW_DETAILS);
    fireEvent.click(viewDetailsButton);

    // Check for Open in Workbench button with Ad Hoc specific title
    const openInWorkbenchButton = screen.getByTitle('Open Ad Hoc script in Workbench');
    expect(openInWorkbenchButton).toBeInTheDocument();
    expect(openInWorkbenchButton.textContent).toContain(OPEN_IN_WORKBENCH);
  });

  it('navigates to Workbench with correct props for regular task', () => {
    render(<TaskRunList taskRuns={[mockTaskRuns[0]]} />);

    // Click View Details to expand
    const viewDetailsButton = screen.getByText(VIEW_DETAILS);
    fireEvent.click(viewDetailsButton);

    // Click Open in Workbench
    const openInWorkbenchButton = screen.getByTitle(OPEN_IN_WORKBENCH_TITLE);
    fireEvent.click(openInWorkbenchButton);

    expect(mockNavigate).toHaveBeenCalledWith(`/workbench?taskId=${TASK_ID_1}&taskRunId=task-1`, {
      state: {
        inputData: JSON.stringify({ test: 'input data' }, null, 2),
        cyScript: undefined,
        isAdHoc: false,
      },
    });
  });

  it('navigates to Workbench with correct props for Ad Hoc task', () => {
    render(<TaskRunList taskRuns={[mockTaskRuns[1]]} />);

    // Click View Details to expand
    const viewDetailsButton = screen.getByText(VIEW_DETAILS);
    fireEvent.click(viewDetailsButton);

    // Click Open in Workbench
    const openInWorkbenchButton = screen.getByTitle('Open Ad Hoc script in Workbench');
    fireEvent.click(openInWorkbenchButton);

    expect(mockNavigate).toHaveBeenCalledWith('/workbench?taskRunId=adhoc-task-1', {
      state: {
        inputData: JSON.stringify({ ad_hoc: 'input' }, null, 2),
        cyScript: 'return "Hello from Ad Hoc"',
        isAdHoc: true,
      },
    });
  });

  it('shows Open in Workbench button for workflow-spawned tasks with execution_context.task_id', () => {
    const workflowSpawnedTask: TaskRun = {
      ...mockTaskRuns[0],
      id: 'workflow-spawned-1',
      task_id: undefined,
      cy_script: undefined,
      task_name: 'Ad Hoc Task',
      execution_context: {
        task_id: 'ctx-task-id-1',
        cy_name: 'some_task',
        tenant_id: 'default',
      },
    };

    render(<TaskRunList taskRuns={[workflowSpawnedTask]} />);

    const viewDetailsButton = screen.getByText(VIEW_DETAILS);
    fireEvent.click(viewDetailsButton);

    const openInWorkbenchButton = screen.getByTitle(OPEN_IN_WORKBENCH_TITLE);
    expect(openInWorkbenchButton).toBeInTheDocument();
    expect(openInWorkbenchButton.textContent).toContain(OPEN_IN_WORKBENCH);
  });

  it('navigates to Workbench with execution_context.task_id for workflow-spawned tasks', () => {
    const workflowSpawnedTask: TaskRun = {
      ...mockTaskRuns[0],
      id: 'workflow-spawned-1',
      task_id: undefined,
      cy_script: undefined,
      task_name: 'Ad Hoc Task',
      input_location: '{"workflow": "input data"}',
      execution_context: {
        task_id: 'ctx-task-id-1',
        cy_name: 'some_task',
        tenant_id: 'default',
      },
    };

    render(<TaskRunList taskRuns={[workflowSpawnedTask]} />);

    const viewDetailsButton = screen.getByText(VIEW_DETAILS);
    fireEvent.click(viewDetailsButton);

    const openInWorkbenchButton = screen.getByTitle(OPEN_IN_WORKBENCH_TITLE);
    fireEvent.click(openInWorkbenchButton);

    expect(mockNavigate).toHaveBeenCalledWith(
      '/workbench?taskId=ctx-task-id-1&taskRunId=workflow-spawned-1',
      {
        state: {
          inputData: JSON.stringify({ workflow: 'input data' }, null, 2),
          cyScript: undefined,
          isAdHoc: false,
        },
      }
    );
  });

  it('does not show Open in Workbench button for tasks without task_id or cy_script', () => {
    const taskWithoutIdOrScript: TaskRun = {
      ...mockTaskRuns[0],
      task_id: undefined,
      cy_script: undefined,
    };

    render(<TaskRunList taskRuns={[taskWithoutIdOrScript]} />);

    // Click View Details to expand
    const viewDetailsButton = screen.getByText(VIEW_DETAILS);
    fireEvent.click(viewDetailsButton);

    // Check that Open in Workbench button is not present
    expect(screen.queryByText(OPEN_IN_WORKBENCH)).not.toBeInTheDocument();
  });

  it('handles input parsing errors gracefully', () => {
    const taskWithInvalidJson: TaskRun = {
      ...mockTaskRuns[0],
      input_location: 'invalid json',
    };

    render(<TaskRunList taskRuns={[taskWithInvalidJson]} />);

    // Click View Details to expand
    const viewDetailsButton = screen.getByText(VIEW_DETAILS);
    fireEvent.click(viewDetailsButton);

    // Click Open in Workbench
    const openInWorkbenchButton = screen.getByTitle(OPEN_IN_WORKBENCH_TITLE);
    fireEvent.click(openInWorkbenchButton);

    // Should navigate with the raw input when JSON parsing fails
    expect(mockNavigate).toHaveBeenCalledWith(`/workbench?taskId=${TASK_ID_1}&taskRunId=task-1`, {
      state: {
        inputData: 'invalid json',
        cyScript: undefined,
        isAdHoc: false,
      },
    });
  });

  it('shows loading state correctly', () => {
    render(<TaskRunList taskRuns={[]} loading={true} />);

    expect(screen.getByText('Loading task runs...')).toBeInTheDocument();
  });

  it('shows empty state when no task runs', () => {
    render(<TaskRunList taskRuns={[]} />);

    expect(screen.getByText('No task runs found')).toBeInTheDocument();
  });

  it('expands and collapses task run details', () => {
    render(<TaskRunList taskRuns={[mockTaskRuns[0]]} />);

    // Initially, details should not be visible
    expect(screen.queryByText('Task Run Details - TRID: task-1')).not.toBeInTheDocument();

    // Click to expand
    const viewDetailsButton = screen.getByText(VIEW_DETAILS);
    fireEvent.click(viewDetailsButton);

    // Details should now be visible
    expect(screen.getByText('Task Run Details - TRID: task-1')).toBeInTheDocument();

    // Click the X button to collapse
    const closeButton = screen.getByText('❌');
    fireEvent.click(closeButton);

    // Details should be hidden again
    expect(screen.queryByText('Task Run Details - TRID: task-1')).not.toBeInTheDocument();
  });

  it('shows "Task deleted" badge and hides Open in Workbench when task is 404', async () => {
    // Simulate task not found
    mockGetTask.mockRejectedValue({ response: { status: 404 } });

    const workflowSpawnedTask: TaskRun = {
      ...mockTaskRuns[0],
      id: 'deleted-task-run-1',
      task_id: undefined,
      cy_script: undefined,
      task_name: 'Ad Hoc Task',
      execution_context: {
        task_id: 'deleted-task-id',
        cy_name: 'deleted_task',
        tenant_id: 'default',
      },
    };

    render(<TaskRunList taskRuns={[workflowSpawnedTask]} />);

    // Expand details
    fireEvent.click(screen.getByText(VIEW_DETAILS));

    // Wait for the async task check to complete and show the badge
    await waitFor(() => {
      expect(screen.getByText('Task deleted')).toBeInTheDocument();
    });

    // Open in Workbench button should be hidden
    expect(screen.queryByText(OPEN_IN_WORKBENCH)).not.toBeInTheDocument();
  });

  it('does not show "Task deleted" badge when task exists', async () => {
    // Task exists (default mock)
    mockGetTask.mockResolvedValue({ id: TASK_ID_1, task_name: REGULAR_TASK });

    render(<TaskRunList taskRuns={[mockTaskRuns[0]]} />);

    // Expand details
    fireEvent.click(screen.getByText(VIEW_DETAILS));

    // Wait for async check
    await waitFor(() => {
      expect(mockGetTask).toHaveBeenCalledWith(TASK_ID_1);
    });

    // No deleted badge
    expect(screen.queryByText('Task deleted')).not.toBeInTheDocument();

    // Open in Workbench button should be visible
    expect(screen.getByTitle(OPEN_IN_WORKBENCH_TITLE)).toBeInTheDocument();
  });
});
