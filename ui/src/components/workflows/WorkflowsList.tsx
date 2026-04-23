import React, { useState, useEffect, useCallback, useMemo } from 'react';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { useWorkflowStore, WorkflowSortField } from '../../store/workflowStore';
import { WorkflowQueryParams } from '../../types/workflow';

import { WorkflowSearch } from './WorkflowSearch';
import { WorkflowsTable } from './WorkflowsTable';

export const WorkflowsList: React.FC = () => {
  // Use the store for state management
  const {
    workflows: storeWorkflows,
    setWorkflows,
    totalCount,
    setTotalCount,
    searchTerm,
    setSearchTerm,
    sortField,
    sortDirection,
    setSorting,
    pagination,
    setPagination,
    getApiParams,
  } = useWorkflowStore();

  const [loading, setLoading] = useState(true);

  // Use proper error handling
  const { error, clearError, runSafe } = useErrorHandler('WorkflowsList');

  const fetchWorkflows = useCallback(async () => {
    setLoading(true);

    try {
      // Use store's getApiParams to get all filter, sort, and pagination params
      const params = getApiParams();

      // Use runSafe to handle errors
      const [response] = await runSafe(
        backendApi.getWorkflows(params as WorkflowQueryParams),
        'fetchWorkflows',
        {
          action: 'fetching workflows',
          params,
        }
      );

      if (response) {
        setWorkflows(response.workflows || []);
        setTotalCount(response.total || 0);
      }
    } finally {
      setLoading(false);
    }
  }, [getApiParams, runSafe, setWorkflows, setTotalCount]);

  // Client-side sorting of workflows
  const sortedWorkflows = useMemo(() => {
    if (storeWorkflows.length === 0) return storeWorkflows;

    return [...storeWorkflows].sort((a, b) => {
      let aValue: string | Date = '';
      let bValue: string | Date = '';

      switch (sortField) {
        case 'description': {
          aValue = a.description || '';
          bValue = b.description || '';
          break;
        }
        case 'created_by': {
          aValue = a.created_by || '';
          bValue = b.created_by || '';
          break;
        }
        case 'created_at': {
          aValue = new Date(a.created_at || '');
          bValue = new Date(b.created_at || '');
          break;
        }
        default: {
          // 'name' and any unknown field — sort by name
          aValue = a.name || '';
          bValue = b.name || '';
        }
      }

      if (aValue instanceof Date && bValue instanceof Date) {
        return sortDirection === 'asc'
          ? aValue.getTime() - bValue.getTime()
          : bValue.getTime() - aValue.getTime();
      }

      const comparison = aValue.toString().localeCompare(bValue.toString());
      return sortDirection === 'asc' ? comparison : -comparison;
    });
  }, [storeWorkflows, sortField, sortDirection]);

  // Initial load and refetch when params change
  useEffect(() => {
    void fetchWorkflows();
  }, [fetchWorkflows]);

  const handleSortChange = (field: WorkflowSortField) => {
    const newDirection = sortField === field && sortDirection === 'asc' ? 'desc' : 'asc';
    setSorting(field, newDirection);
  };

  const handlePageChange = (page: number) => {
    setPagination({ currentPage: page });
  };

  const handleSearch = (term: string) => {
    setSearchTerm(term);
    setPagination({ currentPage: 1 }); // Reset to first page when searching
  };

  // Clear error when component unmounts or when user takes action
  useEffect(() => {
    return () => clearError();
  }, [clearError]);

  return (
    <div className="space-y-6">
      {/* Search */}
      <WorkflowSearch
        searchTerm={searchTerm}
        onSearchChange={handleSearch}
        onRefresh={() => void fetchWorkflows()}
        loading={loading}
      />

      {/* Error Display */}
      {error.hasError && (
        <div className="p-4 border border-red-700 bg-red-900/30 rounded-md">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-medium text-red-400">Error loading workflows</h3>
              <p className="text-sm text-gray-300 mt-1">{error.message}</p>
            </div>
            <div className="flex space-x-3">
              <button
                onClick={clearError}
                className="px-3 py-1 text-sm bg-gray-700 text-gray-300 rounded-sm hover:bg-gray-600"
              >
                Dismiss
              </button>
              <button
                onClick={() => void fetchWorkflows()}
                className="px-3 py-1 text-sm bg-primary text-white rounded-sm hover:bg-primary/90"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Workflows Table */}
      <WorkflowsTable
        workflows={sortedWorkflows}
        loading={loading}
        sortField={sortField}
        sortDirection={sortDirection}
        onSortChange={handleSortChange}
        totalCount={totalCount}
        currentPage={pagination.currentPage}
        itemsPerPage={pagination.itemsPerPage}
        onPageChange={handlePageChange}
      />
    </div>
  );
};
