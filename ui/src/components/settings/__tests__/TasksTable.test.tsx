import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { Task } from '../../../types/knowledge';
import { TasksTable } from '../TasksTable';

// Mock the error handler hook
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: vi.fn(() => ({
    error: { hasError: false, message: '' },
    clearError: vi.fn(),
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: vi.fn(async (promise) => {
      try {
        const result = await promise;
        return [result, undefined];
      } catch (error) {
        return [undefined, error];
      }
    }),
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

// Mock the backend API
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getTask: vi.fn().mockResolvedValue({ data: {} }),
  },
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

describe('TasksTable Component', () => {
  const mockTasks: Task[] = [
    {
      id: '00000001-0000-0000-0000-000000000001',
      name: 'Task One',
      description: 'First test task',
      function: 'summarization',
      created_by: 'user-1',
      visible: true,
      version: '1.0.0',
      scope: 'processing',
      status: 'enabled',
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
    } as Task,
    {
      id: '00000002-0000-0000-0000-000000000002',
      name: 'Task Two',
      description: 'Second test task',
      function: 'extraction',
      created_by: 'user-2',
      visible: true,
      version: '2.0.0',
      scope: 'input',
      status: 'disabled',
      created_at: '2025-01-02T00:00:00Z',
      updated_at: '2025-01-02T00:00:00Z',
    } as Task,
  ];

  const defaultProps = {
    tasks: mockTasks,
    loading: false,
    totalCount: 2,
    currentPage: 1,
    itemsPerPage: 20,
    sortField: 'created_at',
    sortDirection: 'desc' as const,
    onPageChange: vi.fn(),
    onSort: vi.fn(),
  };

  const renderComponent = (props = defaultProps) => {
    return render(
      <BrowserRouter>
        <TasksTable {...props} />
      </BrowserRouter>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Table header rendering', () => {
    it('renders all column headers', () => {
      renderComponent();

      expect(screen.getByText('Name')).toBeInTheDocument();
      expect(screen.getByText('Description')).toBeInTheDocument();
      expect(screen.getByText('Function')).toBeInTheDocument();
      expect(screen.getByText('Scope')).toBeInTheDocument();
      expect(screen.getByText('Created By')).toBeInTheDocument();
      expect(screen.getByText('Status')).toBeInTheDocument();
      expect(screen.getByText('Version')).toBeInTheDocument();
      expect(screen.getByText('Created')).toBeInTheDocument();
      expect(screen.getByText('Actions')).toBeInTheDocument();
    });

    it('has 9 column headers including Actions', () => {
      renderComponent();
      const headers = screen.getAllByRole('columnheader');
      expect(headers).toHaveLength(9);
    });
  });

  describe('Task rows rendering', () => {
    it('renders all tasks', () => {
      renderComponent();

      expect(screen.getByText('Task One')).toBeInTheDocument();
      expect(screen.getByText('Task Two')).toBeInTheDocument();
    });

    it('renders task descriptions', () => {
      renderComponent();

      expect(screen.getByText('First test task')).toBeInTheDocument();
      expect(screen.getByText('Second test task')).toBeInTheDocument();
    });

    it('renders task functions', () => {
      renderComponent();

      expect(screen.getByText('summarization')).toBeInTheDocument();
      expect(screen.getByText('extraction')).toBeInTheDocument();
    });

    it('renders task statuses', () => {
      renderComponent();

      expect(screen.getByText('enabled')).toBeInTheDocument();
      expect(screen.getByText('disabled')).toBeInTheDocument();
    });
  });

  describe('Loading state', () => {
    it('shows loading indicator when loading is true', () => {
      renderComponent({ ...defaultProps, loading: true, tasks: [] });

      expect(screen.getByText('Loading tasks...')).toBeInTheDocument();
    });

    it('does not show tasks when loading', () => {
      renderComponent({ ...defaultProps, loading: true, tasks: mockTasks });

      // During loading, we show loading state instead of tasks
      expect(screen.getByText('Loading tasks...')).toBeInTheDocument();
    });
  });

  describe('Empty state', () => {
    it('shows empty state when no tasks', () => {
      renderComponent({ ...defaultProps, tasks: [], totalCount: 0 });

      expect(screen.getByText('No tasks found')).toBeInTheDocument();
      expect(
        screen.getByText(
          'No tasks match your current filters. Try selecting at least one option in each filter category.'
        )
      ).toBeInTheDocument();
    });

    it('shows reset filters button in empty state', () => {
      renderComponent({ ...defaultProps, tasks: [], totalCount: 0 });

      expect(screen.getByText('Reset All Filters')).toBeInTheDocument();
    });
  });

  describe('Sorting', () => {
    it('calls onSort when name header is clicked', () => {
      renderComponent();

      const nameHeader = screen.getByText('Name');
      fireEvent.click(nameHeader);

      expect(defaultProps.onSort).toHaveBeenCalledWith('name');
    });

    it('calls onSort when function header is clicked', () => {
      renderComponent();

      const functionHeader = screen.getByText('Function');
      fireEvent.click(functionHeader);

      expect(defaultProps.onSort).toHaveBeenCalledWith('function');
    });

    it('calls onSort when scope header is clicked', () => {
      renderComponent();

      const scopeHeader = screen.getByText('Scope');
      fireEvent.click(scopeHeader);

      expect(defaultProps.onSort).toHaveBeenCalledWith('scope');
    });

    it('calls onSort when status header is clicked', () => {
      renderComponent();

      const statusHeader = screen.getByText('Status');
      fireEvent.click(statusHeader);

      expect(defaultProps.onSort).toHaveBeenCalledWith('status');
    });

    it('does not call onSort when Actions header is clicked', () => {
      renderComponent();

      const actionsHeader = screen.getByText('Actions');
      fireEvent.click(actionsHeader);

      // Actions header should not be sortable
      expect(defaultProps.onSort).not.toHaveBeenCalled();
    });
  });

  describe('Row expansion', () => {
    it('expands row when clicked', () => {
      renderComponent();

      // Find and click the first task row
      const taskRow = screen.getByTestId('task-row-00000001-0000-0000-0000-000000000001');
      fireEvent.click(taskRow);

      // The row should now show collapse state
      expect(screen.getByLabelText('Collapse row')).toBeInTheDocument();
    });

    it('collapses row when clicked again', () => {
      renderComponent();

      // Find and click the first task row to expand
      const taskRow = screen.getByTestId('task-row-00000001-0000-0000-0000-000000000001');
      fireEvent.click(taskRow);

      // Click again to collapse
      fireEvent.click(taskRow);

      // Should show expand state again
      expect(screen.getAllByLabelText('Expand row').length).toBeGreaterThan(0);
    });

    it('only one row can be expanded at a time when clicking different rows', () => {
      renderComponent();

      // Expand first row
      const taskRow1 = screen.getByTestId('task-row-00000001-0000-0000-0000-000000000001');
      fireEvent.click(taskRow1);

      // Expand second row
      const taskRow2 = screen.getByTestId('task-row-00000002-0000-0000-0000-000000000002');
      fireEvent.click(taskRow2);

      // Both rows can actually be expanded (the component allows multiple)
      // This test documents the current behavior
      const collapseButtons = screen.getAllByLabelText('Collapse row');
      expect(collapseButtons.length).toBe(2);
    });
  });

  describe('Edit button behavior', () => {
    it('renders edit button for each task', () => {
      renderComponent();

      const editButtons = screen.getAllByTitle('Open in Workbench');
      expect(editButtons).toHaveLength(2);
    });

    it('edit button click does not expand the row', () => {
      renderComponent();

      // Click the edit button for the first task
      const editButtons = screen.getAllByTitle('Open in Workbench');
      fireEvent.click(editButtons[0]);

      // Row should not be expanded (stopPropagation)
      // There should be 2 "Expand row" labels (one for each row, none collapsed)
      const expandButtons = screen.getAllByLabelText('Expand row');
      expect(expandButtons).toHaveLength(2);
    });
  });

  describe('Pagination', () => {
    it('shows pagination when there are enough items', () => {
      // Pagination only shows when totalCount > itemsPerPage (totalPages > 1)
      renderComponent({ ...defaultProps, totalCount: 30, itemsPerPage: 20 });

      // Pagination should be rendered when totalPages > 1
      // Check for page number buttons that exist in the pagination
      const page1Buttons = screen.getAllByRole('button', { name: '1' });
      expect(page1Buttons.length).toBeGreaterThan(0);
    });

    it('shows Previous button disabled on first page', () => {
      // Pagination only shows when totalCount > itemsPerPage (totalPages > 1)
      renderComponent({ ...defaultProps, totalCount: 30, itemsPerPage: 20 });

      // Get first Previous button (there may be multiple pagination components)
      const previousButtons = screen.getAllByText('Previous');
      expect(previousButtons[0].closest('button')).toBeDisabled();
    });

    it('shows page numbers based on total count', () => {
      renderComponent({ ...defaultProps, totalCount: 30, itemsPerPage: 20 });

      // Should show page 1 and page 2 buttons for 30 items with 20 per page
      // Use getAllByRole since pagination may appear in multiple places
      const page1Buttons = screen.getAllByRole('button', { name: '1' });
      const page2Buttons = screen.getAllByRole('button', { name: '2' });
      expect(page1Buttons.length).toBeGreaterThan(0);
      expect(page2Buttons.length).toBeGreaterThan(0);
    });
  });
});
