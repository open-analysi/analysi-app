import React from 'react';

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import type { Task } from '../../../types/knowledge';
import { TaskSelector } from '../TaskSelector';

// Mock the backend API
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getTasks: vi.fn(),
  },
}));

// Mock the error handler
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
    runSafe: vi.fn(async (promise) => {
      try {
        const result = await promise;
        return [result, null];
      } catch (error) {
        return [null, error];
      }
    }),
  }),
}));

const mockTasks: Task[] = Array.from({ length: 50 }, (_, i) => ({
  id: `task-${i + 1}`,
  name: `Task ${i + 1}`,
  description: `Description for task ${i + 1}`,
  script: `print('Task ${i + 1}')`,
  function: 'summarization' as const,
  created_by: 'test-user',
  visible: true,
  version: '1.0.0',
  scope: 'processing' as const,
  status: 'enabled' as const,
  system_only: false,
  app: 'default',
  mode: 'normal',
  tenant_id: 'test-tenant',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  embedding_vector: undefined,
  knowledge_units: [],
  knowledge_modules: [],
  data_samples: [],
}));

// Helper function to create delayed promise
const delayedResolve = <T,>(value: T, delay: number): Promise<T> => {
  return new Promise((resolve) => {
    setTimeout(() => resolve(value), delay);
  });
};

describe('TaskSelector', () => {
  const mockOnTaskChange = vi.fn();
  const SEARCH_PLACEHOLDER = 'Search tasks...';

  beforeEach(() => {
    vi.clearAllMocks();

    // Setup default mock implementation
    vi.mocked(backendApi.getTasks).mockResolvedValue({
      tasks: mockTasks.slice(0, 20),
      total: mockTasks.length,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  const renderTaskSelector = (props: Partial<React.ComponentProps<typeof TaskSelector>> = {}) => {
    return render(
      <MemoryRouter>
        <TaskSelector
          selectedTask={null}
          onTaskChange={mockOnTaskChange}
          isAdHocMode={false}
          {...props}
        />
      </MemoryRouter>
    );
  };

  it('renders the task selector with placeholder text', () => {
    renderTaskSelector();

    expect(screen.getByPlaceholderText(SEARCH_PLACEHOLDER)).toBeInTheDocument();
  });

  it('loads tasks on mount', async () => {
    renderTaskSelector();

    await waitFor(() => {
      expect(backendApi.getTasks).toHaveBeenCalledWith({
        limit: 100,
        offset: 0,
        search: undefined,
      });
    });
  });

  it('displays tasks in the dropdown when opened', async () => {
    const user = userEvent.setup();
    renderTaskSelector();

    await waitFor(() => {
      expect(backendApi.getTasks).toHaveBeenCalled();
    });

    // Click the button to open the dropdown
    const button = screen.getByRole('button');
    await user.click(button);

    // Check that tasks are displayed
    await waitFor(() => {
      expect(screen.getByText('Task 1')).toBeInTheDocument();
      expect(screen.getByText('Task 2')).toBeInTheDocument();
    });
  });

  it('calls onTaskChange when a task is selected', async () => {
    const user = userEvent.setup();
    renderTaskSelector();

    await waitFor(() => {
      expect(backendApi.getTasks).toHaveBeenCalled();
    });

    // Click button to open the dropdown
    const button = screen.getByRole('button');
    await user.click(button);

    // Wait for tasks to load and click one
    const task1Option = await screen.findByText('Task 1');
    await user.click(task1Option);

    // Check that the callback was called with the correct task ID
    expect(mockOnTaskChange).toHaveBeenCalledWith('task-1');
  });

  it('filters tasks when search query is entered', async () => {
    const user = userEvent.setup();

    // Mock filtered results
    vi.mocked(backendApi.getTasks)
      .mockResolvedValueOnce({
        tasks: mockTasks.slice(0, 20),
        total: mockTasks.length,
      })
      .mockResolvedValueOnce({
        tasks: [mockTasks[4]], // Only Task 5
        total: 1,
      });

    renderTaskSelector();

    await waitFor(() => {
      expect(backendApi.getTasks).toHaveBeenCalledTimes(1);
    });

    // Type search query
    const input = screen.getByPlaceholderText(SEARCH_PLACEHOLDER);
    await user.type(input, 'Task 5');

    // Wait for the filtered API call
    await waitFor(() => {
      expect(backendApi.getTasks).toHaveBeenCalledWith({
        limit: 100,
        offset: 0,
        search: 'Task 5',
      });
    });
  });

  it('displays loading indicator while loading', async () => {
    const user = userEvent.setup();

    // Delay the API response using helper function
    const mockResponse = { tasks: mockTasks.slice(0, 20), total: mockTasks.length };
    vi.mocked(backendApi.getTasks).mockImplementation(() => delayedResolve(mockResponse, 500));

    renderTaskSelector();

    // Click button to open dropdown while still loading
    const button = screen.getByRole('button');
    await user.click(button);

    // Check for loading indicator in the dropdown
    await waitFor(() => {
      expect(screen.getByText('Loading tasks...')).toBeInTheDocument();
    });

    // Wait for tasks to load
    await waitFor(
      () => {
        expect(screen.queryByText('Loading tasks...')).not.toBeInTheDocument();
      },
      { timeout: 1000 }
    );
  });

  it('shows empty display value when in Ad Hoc mode', () => {
    renderTaskSelector({ isAdHocMode: true });

    // In ad-hoc mode, the selector shows empty (no task selected)
    expect(screen.getByPlaceholderText(SEARCH_PLACEHOLDER)).toHaveValue('');
  });

  it('shows the selected task name when a task is selected', () => {
    renderTaskSelector({
      selectedTask: mockTasks[0],
      isAdHocMode: false,
    });

    expect(screen.getByDisplayValue('Task 1')).toBeInTheDocument();
  });

  it('handles empty task list gracefully', async () => {
    const user = userEvent.setup();

    vi.mocked(backendApi.getTasks).mockResolvedValue({
      tasks: [],
      total: 0,
    });

    renderTaskSelector();

    // Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading tasks...')).not.toBeInTheDocument();
    });

    // Click button to open dropdown
    const button = screen.getByRole('button');
    await user.click(button);

    // Should show "no tasks" message
    await waitFor(() => {
      expect(screen.getByText('No tasks available.')).toBeInTheDocument();
    });
  });

  it('renders search icon in the input field', () => {
    renderTaskSelector();

    // The search icon (MagnifyingGlassIcon) should be rendered as an SVG
    // It's inside a container with pointer-events-none class
    const container = document.querySelector('.pointer-events-none');
    expect(container).toBeInTheDocument();

    // Check that an SVG icon is present inside
    const svgIcon = container?.querySelector('svg');
    expect(svgIcon).toBeInTheDocument();
  });

  it('shows recently selected tasks in the Recent section', async () => {
    const user = userEvent.setup();

    // Clear localStorage before test
    localStorage.removeItem('workbench_recent_tasks');

    renderTaskSelector();

    await waitFor(() => {
      expect(backendApi.getTasks).toHaveBeenCalled();
    });

    // Open the dropdown
    const button = screen.getByRole('button');
    await user.click(button);

    // Select a task
    const task1Option = await screen.findByText('Task 1');
    await user.click(task1Option);

    // Verify onTaskChange was called
    expect(mockOnTaskChange).toHaveBeenCalledWith('task-1');

    // Verify the task was stored in localStorage
    const storedRecent = JSON.parse(localStorage.getItem('workbench_recent_tasks') || '[]');
    expect(storedRecent).toContain('task-1');

    // Re-open the dropdown to see the Recent section
    await user.click(button);

    // The Recent section should now be visible with the selected task
    await waitFor(() => {
      expect(screen.getByText('Recent')).toBeInTheDocument();
      expect(screen.getByText('All Tasks')).toBeInTheDocument();
    });
  });
});
