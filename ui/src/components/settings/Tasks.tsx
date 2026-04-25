import React, { useState, useEffect, useCallback, useMemo } from 'react';

import { ArrowPathIcon } from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { useTaskStore, TaskSortField } from '../../store/taskStore';
import { Task, TaskQueryParams } from '../../types/knowledge';
import ErrorBoundary from '../common/ErrorBoundary';

import { CategoryFilter } from './CategoryFilter';
import { DropdownFilter } from './DropdownFilter';
import { TasksTable } from './TasksTable';
import { UnifiedSearch } from './UnifiedSearch';

export const Tasks: React.FC = () => {
  // Use the store for state management
  const {
    tasks: storeTasks,
    setTasks,
    totalCount,
    setTotalCount,
    searchTerm,
    setSearchTerm,
    sortField,
    sortDirection,
    setSorting,
    pagination,
    setPagination,
    categoryFilter,
    toggleCategory,
    setCategoryFilter,
    filters,
    setFunctionFilters,
    setScopeFilters,
    setStatusFilters,
    getApiParams,
  } = useTaskStore();

  const [loading, setLoading] = useState(true);
  const [scheduledFilter, setScheduledFilter] = useState<'all' | 'scheduled' | 'unscheduled'>(
    'all'
  );

  // Use proper error handling
  const { error, clearError, runSafe } = useErrorHandler('Tasks');

  const fetchTasks = useCallback(async () => {
    setLoading(true);

    try {
      // Use store's getApiParams to get all filter, sort, and pagination params
      const params = getApiParams();

      // Check if we should return no results due to filter settings
      if (params.no_results) {
        setTasks([]);
        setTotalCount(0);
        return;
      }

      // getTasks() returns { tasks: Task[], total: number } (Sifnos envelope unwrapped by service layer)
      const [response] = await runSafe(
        backendApi.getTasks(params as TaskQueryParams),
        'fetchTasks',
        {
          action: 'fetching tasks',
          params,
        }
      );

      if (response) {
        setTasks(response.tasks);
        setTotalCount(response.total);
      }
    } finally {
      setLoading(false);
    }
  }, [getApiParams, runSafe, setTasks, setTotalCount]);

  // Client-side filtering by function, scope, status, and scheduled
  const filteredTasks = useMemo(() => {
    if (storeTasks.length === 0) return storeTasks;

    const selectedFunctions = new Set(
      (Object.entries(filters.function) as [string, boolean][]).filter(([, v]) => v).map(([k]) => k)
    );
    const selectedScopes = new Set(
      (Object.entries(filters.scope) as [string, boolean][]).filter(([, v]) => v).map(([k]) => k)
    );
    const selectedStatuses = new Set(
      (Object.entries(filters.status) as [string, boolean][]).filter(([, v]) => v).map(([k]) => k)
    );

    // If any category has nothing selected, show no results
    if (selectedFunctions.size === 0 || selectedScopes.size === 0 || selectedStatuses.size === 0) {
      return [];
    }

    const allFunctions = selectedFunctions.size === Object.keys(filters.function).length;
    const allScopes = selectedScopes.size === Object.keys(filters.scope).length;
    const allStatuses = selectedStatuses.size === Object.keys(filters.status).length;
    const noScheduleFilter = scheduledFilter === 'all';

    // If everything is "all", skip filtering
    if (allFunctions && allScopes && allStatuses && noScheduleFilter) return storeTasks;

    return storeTasks.filter((task) => {
      if (!allFunctions && !selectedFunctions.has(task.function ?? '')) return false;
      if (!allScopes && !selectedScopes.has(task.scope ?? '')) return false;
      if (!allStatuses && !selectedStatuses.has(task.status ?? '')) return false;
      const isScheduled = task.categories?.includes('scheduled') ?? false;
      if (scheduledFilter === 'scheduled' && !isScheduled) return false;
      if (scheduledFilter === 'unscheduled' && isScheduled) return false;
      return true;
    });
  }, [storeTasks, filters, scheduledFilter]);

  // Client-side sorting of tasks
  const sortedTasks = useMemo(() => {
    if (filteredTasks.length === 0) return filteredTasks;

    return [...filteredTasks].sort((a, b) => {
      let aValue: string | Date = '';
      let bValue: string | Date = '';

      switch (sortField) {
        case 'name': {
          aValue = a.name || '';
          bValue = b.name || '';
          break;
        }
        case 'description': {
          aValue = a.description || '';
          bValue = b.description || '';
          break;
        }
        case 'function': {
          aValue = a.function || '';
          bValue = b.function || '';
          break;
        }
        case 'owner': {
          aValue = a.created_by || '';
          bValue = b.created_by || '';
          break;
        }
        case 'scope': {
          aValue = a.scope || '';
          bValue = b.scope || '';
          break;
        }
        case 'status': {
          aValue = a.status || '';
          bValue = b.status || '';
          break;
        }
        case 'version': {
          aValue = a.version || '';
          bValue = b.version || '';
          break;
        }
        case 'created_at': {
          aValue = new Date(a.created_at || 0);
          bValue = new Date(b.created_at || 0);
          break;
        }
        case 'updated_at': {
          aValue = new Date(a.updated_at || 0);
          bValue = new Date(b.updated_at || 0);
          break;
        }
        default: {
          return 0;
        }
      }

      // Handle string comparison
      if (typeof aValue === 'string' && typeof bValue === 'string') {
        const comparison = aValue.toLowerCase().localeCompare(bValue.toLowerCase());
        return sortDirection === 'asc' ? comparison : -comparison;
      }

      // Handle date comparison
      if (aValue instanceof Date && bValue instanceof Date) {
        const comparison = aValue.getTime() - bValue.getTime();
        return sortDirection === 'asc' ? comparison : -comparison;
      }

      return 0;
    });
  }, [filteredTasks, sortField, sortDirection]);

  // Derive available categories from loaded data for filter dropdown
  const availableCategories = useMemo(() => {
    const cats = new Set(storeTasks.flatMap((t: Task) => t.categories || []));
    for (const c of categoryFilter) cats.add(c);
    return Array.from(cats).sort((a, b) => a.localeCompare(b));
  }, [storeTasks, categoryFilter]);

  // Fetch tasks when pagination, search, or category changes
  // (function/scope/status filters and sort are applied client-side)
  useEffect(() => {
    void fetchTasks();
  }, [pagination.currentPage, pagination.itemsPerPage, searchTerm, categoryFilter, fetchTasks]);

  const handleSort = (field: string) => {
    setSorting(field as TaskSortField);
  };

  const handlePageChange = (newPage: number) => {
    setPagination({ currentPage: newPage });
  };

  const handleItemsPerPageChange = (newItemsPerPage: number) => {
    setPagination({ itemsPerPage: newItemsPerPage, currentPage: 1 });
  };

  // More efficient search handler that prevents double API calls
  const handleSearch = useCallback(
    (query: string) => {
      // Directly update the search term without additional checks
      // The store will handle deduplication if needed
      setSearchTerm(query);
    },
    [setSearchTerm]
  );

  // Handle task deletion
  const handleDeleteTask = useCallback(
    async (taskId: string) => {
      const [, deleteError] = await runSafe(backendApi.deleteTask(taskId), 'deleteTask', {
        action: 'deleting task',
        entityId: taskId,
      });

      if (!deleteError) {
        // Refresh the tasks list after successful deletion
        void fetchTasks();
      }
    },
    [runSafe, fetchTasks]
  );

  return (
    <ErrorBoundary component="Tasks">
      <div>
        <div className="mb-6 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-white">Tasks</h1>
              {totalCount > 0 && (
                <span className="px-2.5 py-0.5 rounded-full text-sm font-medium bg-dark-700 text-gray-100">
                  {totalCount} {totalCount === 1 ? 'task' : 'tasks'}
                </span>
              )}
            </div>
            <p className="mt-1 text-sm text-gray-400">
              View and manage tasks that use knowledge units
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label htmlFor="tasks-items-per-page" className="text-sm text-gray-400">
                Show:
              </label>
              <select
                id="tasks-items-per-page"
                value={pagination.itemsPerPage}
                onChange={(e) => handleItemsPerPageChange(Number(e.target.value))}
                className="bg-dark-700 border border-gray-600 text-gray-100 text-sm rounded-md px-2 py-1 focus:ring-primary focus:border-primary"
              >
                <option value="10">10</option>
                <option value="20">20</option>
                <option value="50">50</option>
                <option value="100">100</option>
              </select>
              <span className="text-sm text-gray-400">per page</span>
            </div>
            <button
              onClick={() => void fetchTasks()}
              disabled={loading}
              className="inline-flex items-center px-3 py-1.5 border border-gray-600 shadow-xs text-sm font-medium rounded-md text-gray-100 bg-dark-800 hover:bg-dark-700 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ArrowPathIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''} mr-1.5`} />
              Refresh
            </button>
          </div>
        </div>

        {error.hasError && (
          <div className="mb-6 bg-red-900/30 border border-red-700 p-4 rounded-md">
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-gray-100">{error.message}</p>
              </div>
              <button onClick={clearError} className="text-gray-400 hover:text-gray-100 text-sm">
                Dismiss
              </button>
            </div>
          </div>
        )}

        <div className="mb-6">
          <UnifiedSearch
            onSearch={handleSearch}
            value={searchTerm}
            placeholder="Search tasks by name, description, or function..."
          />
        </div>

        {/* Inline filters: Function, Scope, Status, Categories */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <DropdownFilter
            label="Function"
            options={Object.keys(filters.function)}
            selected={Object.entries(filters.function)
              .filter(([, v]) => v)
              .map(([k]) => k)}
            onToggle={(key) =>
              setFunctionFilters({
                [key]: !filters.function[key as keyof typeof filters.function],
              })
            }
            onClear={() =>
              setFunctionFilters(
                Object.fromEntries(Object.keys(filters.function).map((k) => [k, false]))
              )
            }
            onSelectAll={() =>
              setFunctionFilters(
                Object.fromEntries(Object.keys(filters.function).map((k) => [k, true]))
              )
            }
          />
          <DropdownFilter
            label="Scope"
            options={Object.keys(filters.scope)}
            selected={Object.entries(filters.scope)
              .filter(([, v]) => v)
              .map(([k]) => k)}
            onToggle={(key) =>
              setScopeFilters({
                [key]: !filters.scope[key as keyof typeof filters.scope],
              })
            }
            onClear={() =>
              setScopeFilters(Object.fromEntries(Object.keys(filters.scope).map((k) => [k, false])))
            }
            onSelectAll={() =>
              setScopeFilters(Object.fromEntries(Object.keys(filters.scope).map((k) => [k, true])))
            }
          />
          <DropdownFilter
            label="Status"
            options={Object.keys(filters.status)}
            selected={Object.entries(filters.status)
              .filter(([, v]) => v)
              .map(([k]) => k)}
            onToggle={(key) =>
              setStatusFilters({
                [key]: !filters.status[key as keyof typeof filters.status],
              })
            }
            onClear={() =>
              setStatusFilters(
                Object.fromEntries(Object.keys(filters.status).map((k) => [k, false]))
              )
            }
            onSelectAll={() =>
              setStatusFilters(
                Object.fromEntries(Object.keys(filters.status).map((k) => [k, true]))
              )
            }
          />
          <DropdownFilter
            label="Scheduled"
            options={['scheduled', 'unscheduled']}
            selected={scheduledFilter === 'all' ? ['scheduled', 'unscheduled'] : [scheduledFilter]}
            onToggle={(key) => {
              if (scheduledFilter === 'all') {
                // Deselect the clicked one, keep the other
                setScheduledFilter(key === 'scheduled' ? 'unscheduled' : 'scheduled');
              } else if (scheduledFilter === key) {
                // Deselecting the only selected one — show all
                setScheduledFilter('all');
              } else {
                // Selecting the other one — both selected = all
                setScheduledFilter('all');
              }
            }}
            onClear={() => setScheduledFilter('all')}
            onSelectAll={() => setScheduledFilter('all')}
          />
          {availableCategories.length > 0 && (
            <CategoryFilter
              available={availableCategories}
              selected={categoryFilter}
              onToggle={toggleCategory}
              onClear={() => setCategoryFilter([])}
            />
          )}
        </div>

        <div className={`relative ${loading ? 'opacity-75 transition-opacity duration-200' : ''}`}>
          <TasksTable
            tasks={sortedTasks}
            loading={loading}
            totalCount={totalCount}
            currentPage={pagination.currentPage}
            itemsPerPage={pagination.itemsPerPage}
            sortField={sortField}
            sortDirection={sortDirection}
            onPageChange={handlePageChange}
            onSort={handleSort}
            onDeleteTask={(taskId) => void handleDeleteTask(taskId)}
          />
        </div>
      </div>
    </ErrorBoundary>
  );
};
