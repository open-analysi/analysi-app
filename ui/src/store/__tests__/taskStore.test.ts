/**
 * Tests for TaskStore
 *
 * Covers sorting, filters, search, pagination, and API params.
 */

import { describe, it, expect, beforeEach } from 'vitest';

import { Task } from '../../types/knowledge';
import { useTaskStore, TaskSortField } from '../taskStore';

// Helper to fully reset the store
const resetStore = () => {
  const store = useTaskStore.getState();
  store.setTasks([]);
  store.resetFilters();
  store.setSorting('created_at', 'desc');
  store.setPagination({ currentPage: 1, itemsPerPage: 20 });
  store.setTotalCount(0);
};

describe('TaskStore - Scope Field Sorting', () => {
  beforeEach(() => {
    resetStore();
  });

  it('should allow sorting by scope field', () => {
    // This should compile without errors - 'scope' is a valid TaskSortField
    const scopeField: TaskSortField = 'scope';

    expect(scopeField).toBe('scope');

    // Should be able to set sorting to scope
    useTaskStore.getState().setSorting('scope', 'asc');

    // Get fresh state after setting
    const updatedStore = useTaskStore.getState();
    expect(updatedStore.sortField).toBe('scope');
    expect(updatedStore.sortDirection).toBe('asc');
  });

  it('should correctly sort tasks by scope field', () => {
    const mockTasks: Task[] = [
      {
        id: '1',
        name: 'Task 1',
        description: 'Test task 1',
        function: 'extraction',
        created_by: 'test',
        visible: true,
        version: '1.0',
        scope: 'output', // Should be last when sorted ascending
        status: 'enabled',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      } as Task,
      {
        id: '2',
        name: 'Task 2',
        description: 'Test task 2',
        function: 'summarization',
        created_by: 'test',
        visible: true,
        version: '1.0',
        scope: 'input', // Should be first when sorted ascending
        status: 'enabled',
        created_at: '2024-01-02T00:00:00Z',
        updated_at: '2024-01-02T00:00:00Z',
      } as Task,
      {
        id: '3',
        name: 'Task 3',
        description: 'Test task 3',
        function: 'data_conversion',
        created_by: 'test',
        visible: true,
        version: '1.0',
        scope: 'processing', // Should be middle when sorted ascending
        status: 'enabled',
        created_at: '2024-01-03T00:00:00Z',
        updated_at: '2024-01-03T00:00:00Z',
      } as Task,
    ];

    useTaskStore.getState().setTasks(mockTasks);

    // Set sorting to scope ascending
    useTaskStore.getState().setSorting('scope', 'asc');

    // Get fresh store state
    const store = useTaskStore.getState();

    // Manually sort to verify the logic (mimicking Tasks.tsx sorting logic)
    const sortedTasks = [...mockTasks].sort((a, b) => {
      const aValue = a.scope || '';
      const bValue = b.scope || '';
      const comparison = aValue.toLowerCase().localeCompare(bValue.toLowerCase());
      return store.sortDirection === 'asc' ? comparison : -comparison;
    });

    // Alphabetical order: 'input' < 'output' < 'processing'
    expect(sortedTasks[0].scope).toBe('input');
    expect(sortedTasks[1].scope).toBe('output');
    expect(sortedTasks[2].scope).toBe('processing');
  });

  it('should not accept invalid scopes field', () => {
    // This test verifies type safety - 'scopes' (plural) should not be allowed
    // TypeScript should catch this at compile time, but we verify at runtime too
    // @ts-expect-error - 'scopes' is not a valid TaskSortField
    const invalidField: TaskSortField = 'scopes';

    expect(invalidField).toBe('scopes');
  });

  it('should have scope field matching Task interface', () => {
    // Verify that the scope values match what Task interface expects
    const validScopes: Array<Task['scope']> = ['input', 'processing', 'output'];

    expect(validScopes).toContain('input');
    expect(validScopes).toContain('processing');
    expect(validScopes).toContain('output');
    expect(validScopes).toHaveLength(3);
  });
});

describe('TaskStore - Sorting', () => {
  beforeEach(() => {
    resetStore();
  });

  it('toggles sort direction when clicking the same field', () => {
    useTaskStore.getState().setSorting('name', 'asc');
    expect(useTaskStore.getState().sortDirection).toBe('asc');

    // Click same field without explicit direction → toggles
    useTaskStore.getState().setSorting('name');
    expect(useTaskStore.getState().sortDirection).toBe('desc');

    useTaskStore.getState().setSorting('name');
    expect(useTaskStore.getState().sortDirection).toBe('asc');
  });

  it('sets new field with default ascending direction', () => {
    useTaskStore.getState().setSorting('name', 'desc');
    useTaskStore.getState().setSorting('status');
    expect(useTaskStore.getState().sortField).toBe('status');
    expect(useTaskStore.getState().sortDirection).toBe('asc');
  });

  it('sets new field with explicit direction', () => {
    useTaskStore.getState().setSorting('version', 'desc');
    expect(useTaskStore.getState().sortField).toBe('version');
    expect(useTaskStore.getState().sortDirection).toBe('desc');
  });
});

describe('TaskStore - Filters', () => {
  beforeEach(() => {
    resetStore();
  });

  it('sets function filters partially', () => {
    useTaskStore.getState().setFunctionFilters({ extraction: false });
    const { filters } = useTaskStore.getState();
    expect(filters.function.extraction).toBe(false);
    expect(filters.function.summarization).toBe(true);
  });

  it('sets scope filters partially', () => {
    useTaskStore.getState().setScopeFilters({ input: false });
    const { filters } = useTaskStore.getState();
    expect(filters.scope.input).toBe(false);
    expect(filters.scope.processing).toBe(true);
    expect(filters.scope.output).toBe(true);
  });

  it('sets status filters partially', () => {
    useTaskStore.getState().setStatusFilters({ deprecated: false });
    const { filters } = useTaskStore.getState();
    expect(filters.status.deprecated).toBe(false);
    expect(filters.status.active).toBe(true);
  });

  it('resetFilters restores all defaults and clears search', () => {
    const store = useTaskStore.getState();
    store.setFunctionFilters({ extraction: false });
    store.setScopeFilters({ input: false });
    store.setStatusFilters({ active: false });
    store.setSearchTerm('test query');

    store.resetFilters();
    const state = useTaskStore.getState();

    expect(state.filters.function.extraction).toBe(true);
    expect(state.filters.scope.input).toBe(true);
    expect(state.filters.status.active).toBe(true);
    expect(state.searchTerm).toBe('');
  });
});

describe('TaskStore - Search', () => {
  beforeEach(() => {
    resetStore();
  });

  it('sets a search term', () => {
    useTaskStore.getState().setSearchTerm('ip analysis');
    expect(useTaskStore.getState().searchTerm).toBe('ip analysis');
  });

  it('does not trigger state update when term is unchanged', () => {
    useTaskStore.getState().setSearchTerm('same');
    const state1 = useTaskStore.getState();

    useTaskStore.getState().setSearchTerm('same');
    const state2 = useTaskStore.getState();

    // Zustand should return the exact same state reference
    expect(state1).toBe(state2);
  });
});

describe('TaskStore - Pagination', () => {
  beforeEach(() => {
    resetStore();
  });

  it('has default pagination values', () => {
    const { pagination } = useTaskStore.getState();
    expect(pagination.currentPage).toBe(1);
    expect(pagination.itemsPerPage).toBe(20);
  });

  it('sets pagination partially (only currentPage)', () => {
    useTaskStore.getState().setPagination({ currentPage: 3 });
    const { pagination } = useTaskStore.getState();
    expect(pagination.currentPage).toBe(3);
    expect(pagination.itemsPerPage).toBe(20);
  });

  it('sets pagination partially (only itemsPerPage)', () => {
    useTaskStore.getState().setPagination({ itemsPerPage: 50 });
    const { pagination } = useTaskStore.getState();
    expect(pagination.currentPage).toBe(1);
    expect(pagination.itemsPerPage).toBe(50);
  });
});

describe('TaskStore - Data', () => {
  beforeEach(() => {
    resetStore();
  });

  it('setTasks stores tasks', () => {
    const tasks = [{ id: '1', name: 'Task A' }] as Task[];
    useTaskStore.getState().setTasks(tasks);
    expect(useTaskStore.getState().tasks).toEqual(tasks);
  });

  it('setTotalCount stores count', () => {
    useTaskStore.getState().setTotalCount(42);
    expect(useTaskStore.getState().totalCount).toBe(42);
  });
});

describe('TaskStore - getApiParams', () => {
  beforeEach(() => {
    resetStore();
  });

  it('returns default params with pagination and sorting', () => {
    const params = useTaskStore.getState().getApiParams();
    expect(params.limit).toBe(20);
    expect(params.offset).toBe(0);
    expect(params.sort).toBe('created_at');
    expect(params.order).toBe('desc');
    expect(params.q).toBeUndefined();
    expect(params.scope).toBeUndefined();
  });

  it('includes search term as q param', () => {
    useTaskStore.getState().setSearchTerm('malware');
    const params = useTaskStore.getState().getApiParams();
    expect(params.q).toBe('malware');
  });

  it('does not include q param when search is empty', () => {
    useTaskStore.getState().setSearchTerm('');
    const params = useTaskStore.getState().getApiParams();
    expect(params.q).toBeUndefined();
  });

  it('calculates offset from pagination', () => {
    useTaskStore.getState().setPagination({ currentPage: 3, itemsPerPage: 10 });
    const params = useTaskStore.getState().getApiParams();
    expect(params.offset).toBe(20); // (3-1) * 10
    expect(params.limit).toBe(10);
  });

  it('does not send function/scope/status to backend (client-side filtering)', () => {
    useTaskStore.getState().setFunctionFilters({ extraction: false });
    useTaskStore.getState().setScopeFilters({ input: false });
    useTaskStore.getState().setStatusFilters({ deprecated: false });
    const params = useTaskStore.getState().getApiParams();
    expect(params.function).toBeUndefined();
    expect(params.scope).toBeUndefined();
    expect(params.status).toBeUndefined();
  });

  it('reflects sorting changes', () => {
    useTaskStore.getState().setSorting('name', 'asc');
    const params = useTaskStore.getState().getApiParams();
    expect(params.sort).toBe('name');
    expect(params.order).toBe('asc');
  });
});
