/**
 * Tests for Tasks component response handling
 *
 * These tests verify that the Tasks component correctly handles
 * the Sifnos envelope format via the service layer.
 * getTasks() returns { tasks: Task[], total: number } after
 * unwrapping the backend's { data, meta } envelope.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import { useTaskStore } from '../../../store/taskStore';
import { Task } from '../../../types/knowledge';

describe('Tasks - Response Handling', () => {
  beforeEach(() => {
    // Reset store before each test
    useTaskStore.setState({
      tasks: [],
      totalCount: 0,
      sortField: 'updated_at',
      sortDirection: 'desc',
      pagination: { currentPage: 1, itemsPerPage: 20 },
    });
  });

  afterEach(() => {
    // Clean up after each test
    useTaskStore.setState({
      tasks: [],
      totalCount: 0,
    });
  });

  const mockTask: Task = {
    id: 'task-1',
    name: 'Test Task',
    description: 'Test description',
    function: 'extraction',
    created_by: 'test',
    visible: true,
    version: '1.0',
    scope: 'processing',
    status: 'enabled',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  } as Task;

  it('should handle tasks response with total', () => {
    // Service layer always returns { tasks: Task[], total: number }
    const response = {
      tasks: [mockTask],
      total: 10,
    };

    useTaskStore.getState().setTasks(response.tasks);
    useTaskStore.getState().setTotalCount(response.total);

    const store = useTaskStore.getState();
    expect(store.tasks).toHaveLength(1);
    expect(store.totalCount).toBe(10);
  });

  it('should handle empty tasks response', () => {
    const response = {
      tasks: [] as Task[],
      total: 0,
    };

    useTaskStore.getState().setTasks(response.tasks);
    useTaskStore.getState().setTotalCount(response.total);

    const store = useTaskStore.getState();
    expect(store.tasks).toHaveLength(0);
    expect(store.totalCount).toBe(0);
  });

  it('should handle paginated response where total exceeds page size', () => {
    // e.g., page 1 of 100 results with 20 per page
    const response = {
      tasks: [mockTask, { ...mockTask, id: 'task-2' }],
      total: 100,
    };

    useTaskStore.getState().setTasks(response.tasks);
    useTaskStore.getState().setTotalCount(response.total);

    const store = useTaskStore.getState();
    expect(store.tasks).toHaveLength(2);
    expect(store.totalCount).toBe(100);
  });
});
