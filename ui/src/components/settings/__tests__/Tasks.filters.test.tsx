/**
 * Tests for Tasks component filter integration.
 *
 * Filters for function, scope, and status are applied client-side.
 * Verifies dropdown rendering, client-side filtering behavior,
 * and that filtered counts are correct.
 */

import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { useTaskStore } from '../../../store/taskStore';
import { Task } from '../../../types/knowledge';
import { Tasks } from '../Tasks';

const mockGetTasks = vi.fn().mockResolvedValue({ tasks: [], total: 0 });

// Mock backend API
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getTasks: (...args: unknown[]) => mockGetTasks(...args),
  },
}));

// Stable mock functions to avoid infinite re-render loops
const stableRunSafe = async (promise: Promise<unknown>) => {
  try {
    const result = await promise;
    return [result, undefined];
  } catch (error) {
    return [undefined, error];
  }
};
const stableClearError = () => {};
const stableHandleError = () => {};
const stableCreateContext = () => ({});
const stableErrorState = { hasError: false, message: '' };

vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: stableErrorState,
    clearError: stableClearError,
    handleError: stableHandleError,
    createContext: stableCreateContext,
    runSafe: stableRunSafe,
  }),
}));

vi.mock('react-router', async () => {
  const actual = await vi.importActual('react-router');
  return { ...actual, useNavigate: () => vi.fn() };
});

vi.mock('../../../hooks/useUserDisplay', () => ({
  useUserDisplay: (userId: string | undefined) => userId || 'Unknown',
}));

vi.mock('../../../hooks/usePageTracking', () => ({
  usePageTracking: vi.fn(),
}));

vi.mock('../../../hooks/useDebounce', () => ({
  useDebounce: <T,>(value: T) => value,
}));

vi.mock('../../common/ConfirmDialog', () => ({
  ConfirmDialog: () => null,
}));

const EXTRACTION_TASK = 'Extraction Task';
const SUMMARY_TASK = 'Summary Task';
const CONVERT_TASK = 'Convert Task';

const mockTasks: Task[] = [
  {
    id: 'task-1',
    name: EXTRACTION_TASK,
    description: 'Extract data',
    function: 'extraction',
    scope: 'input',
    status: 'active',
    created_by: 'user-1',
    visible: true,
    system_only: false,
    app: 'default',
    version: '1.0',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    categories: ['scheduled', 'integration'],
  } as Task,
  {
    id: 'task-2',
    name: SUMMARY_TASK,
    description: 'Summarize data',
    function: 'summarization',
    scope: 'processing',
    status: 'deprecated',
    created_by: 'user-2',
    visible: true,
    system_only: false,
    app: 'default',
    version: '2.0',
    created_at: '2025-01-02T00:00:00Z',
    updated_at: '2025-01-02T00:00:00Z',
    categories: [] as string[],
  } as Task,
  {
    id: 'task-3',
    name: CONVERT_TASK,
    description: 'Convert data',
    function: 'data_conversion',
    scope: 'output',
    status: 'active',
    created_by: 'user-3',
    visible: true,
    system_only: false,
    app: 'default',
    version: '1.0',
    created_at: '2025-01-03T00:00:00Z',
    updated_at: '2025-01-03T00:00:00Z',
  } as Task,
];

const resetStore = () => {
  const store = useTaskStore.getState();
  store.setTasks([]);
  store.resetFilters();
  store.setSorting('created_at', 'desc');
  store.setPagination({ currentPage: 1, itemsPerPage: 20 });
  store.setTotalCount(0);
};

const renderTasks = async () => {
  let result: ReturnType<typeof render>;
  await act(async () => {
    result = render(
      <BrowserRouter>
        <Tasks />
      </BrowserRouter>
    );
    await new Promise((r) => setTimeout(r, 0));
  });
  return result!;
};

describe('Tasks - Filter Integration', () => {
  beforeEach(() => {
    resetStore();
    mockGetTasks.mockResolvedValue({ tasks: mockTasks, total: 3 });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders inline dropdown filter buttons for Function, Scope, and Status', async () => {
    await renderTasks();

    expect(screen.getByRole('group', { name: /Function filters/ })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: /Scope filters/ })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: /Status filters/ })).toBeInTheDocument();
  });

  it('opens dropdown when Function filter button is clicked', async () => {
    await renderTasks();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Function/ }));
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(screen.getByRole('option', { name: /Extraction/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Summarization/ })).toBeInTheDocument();
  });

  it('filters tasks client-side by function', async () => {
    await renderTasks();

    // All 3 tasks visible initially
    expect(screen.getByText(EXTRACTION_TASK)).toBeInTheDocument();
    expect(screen.getByText(SUMMARY_TASK)).toBeInTheDocument();
    expect(screen.getByText(CONVERT_TASK)).toBeInTheDocument();

    // Deselect extraction
    await act(async () => {
      useTaskStore.getState().setFunctionFilters({ extraction: false });
      await new Promise((r) => setTimeout(r, 0));
    });

    // Extraction task should be filtered out, others remain
    expect(screen.queryByText(EXTRACTION_TASK)).not.toBeInTheDocument();
    expect(screen.getByText(SUMMARY_TASK)).toBeInTheDocument();
    expect(screen.getByText(CONVERT_TASK)).toBeInTheDocument();
  });

  it('filters tasks client-side by scope', async () => {
    await renderTasks();

    // Deselect input and output, keep only processing
    await act(async () => {
      useTaskStore.getState().setScopeFilters({ input: false, output: false });
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(screen.queryByText(EXTRACTION_TASK)).not.toBeInTheDocument();
    expect(screen.getByText(SUMMARY_TASK)).toBeInTheDocument();
    expect(screen.queryByText(CONVERT_TASK)).not.toBeInTheDocument();
  });

  it('filters tasks client-side by status', async () => {
    await renderTasks();

    // Deselect active, keep only deprecated
    await act(async () => {
      useTaskStore.getState().setStatusFilters({ active: false, experimental: false });
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(screen.queryByText(EXTRACTION_TASK)).not.toBeInTheDocument();
    expect(screen.getByText(SUMMARY_TASK)).toBeInTheDocument();
    expect(screen.queryByText(CONVERT_TASK)).not.toBeInTheDocument();
  });

  it('combines multiple filters correctly (function AND scope)', async () => {
    await renderTasks();

    // Select only extraction function AND only input scope
    await act(async () => {
      useTaskStore.getState().setFunctionFilters({ summarization: false, data_conversion: false });
      useTaskStore.getState().setScopeFilters({ processing: false, output: false });
      await new Promise((r) => setTimeout(r, 0));
    });

    // Only task-1 matches both extraction + input
    expect(screen.getByText(EXTRACTION_TASK)).toBeInTheDocument();
    expect(screen.queryByText(SUMMARY_TASK)).not.toBeInTheDocument();
    expect(screen.queryByText(CONVERT_TASK)).not.toBeInTheDocument();
  });

  it('shows empty state when no tasks match filters', async () => {
    await renderTasks();

    // Deselect all scopes
    await act(async () => {
      useTaskStore.getState().setScopeFilters({ input: false, processing: false, output: false });
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(screen.getByText('No tasks found')).toBeInTheDocument();
  });

  it('does not send function/scope/status params to backend', async () => {
    useTaskStore.getState().setFunctionFilters({ extraction: false });
    useTaskStore.getState().setStatusFilters({ deprecated: false });

    await renderTasks();

    await waitFor(() => {
      expect(mockGetTasks).toHaveBeenCalled();
    });

    // Backend should NOT receive function/status/scope params
    const lastCall = mockGetTasks.mock.calls.at(-1)![0];
    expect(lastCall.function).toBeUndefined();
    expect(lastCall.status).toBeUndefined();
    expect(lastCall.scope).toBeUndefined();
  });

  it('shows deselected count badge on filter button', async () => {
    useTaskStore.getState().setFunctionFilters({ extraction: false });

    await renderTasks();

    const functionGroup = screen.getByRole('group', { name: /Function filters/ });
    expect(functionGroup.textContent).toContain('1');
  });

  it('renders Scheduled filter dropdown', async () => {
    await renderTasks();

    expect(screen.getByRole('group', { name: /Scheduled filters/ })).toBeInTheDocument();
  });

  it('filters to show only scheduled tasks', async () => {
    await renderTasks();

    // Open Scheduled dropdown and deselect "Unscheduled"
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Scheduled/ }));
      await new Promise((r) => setTimeout(r, 0));
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('option', { name: /Unscheduled/ }));
      await new Promise((r) => setTimeout(r, 0));
    });

    // Only task-1 (has schedule) should be visible; task-2 (null) and task-3 (no field) hidden
    expect(screen.getByText(EXTRACTION_TASK)).toBeInTheDocument();
    expect(screen.queryByText(SUMMARY_TASK)).not.toBeInTheDocument();
  });

  it('passes server totalCount to pagination, not filtered page length', async () => {
    // Regression: Tasks passed filteredTasks.length (max page size) as totalCount,
    // which hid pagination when totalCount <= itemsPerPage.
    // The API returns 3 tasks on this page but total=50 across all pages.
    mockGetTasks.mockResolvedValue({ tasks: mockTasks, total: 50 });

    await renderTasks();

    // Pagination page buttons should render (50 items / 20 per page = 3 pages)
    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: '2' }).length).toBeGreaterThan(0);
    });
    expect(screen.getAllByRole('button', { name: '3' }).length).toBeGreaterThan(0);
  });

  it('shows clock icon on scheduled tasks', async () => {
    await renderTasks();

    // task-1 has 'scheduled' category — should have a clock icon
    const row = screen.getByTestId('task-row-task-1');
    expect(row.querySelector('[aria-label="Scheduled task"]')).not.toBeNull();

    // task-2 has no 'scheduled' category — no clock icon
    const row2 = screen.getByTestId('task-row-task-2');
    expect(row2.querySelector('[aria-label="Scheduled task"]')).toBeNull();
  });
});
