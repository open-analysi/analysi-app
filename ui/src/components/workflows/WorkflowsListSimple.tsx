import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';

import {
  PlayIcon,
  EyeIcon,
  PencilSquareIcon,
  TrashIcon,
  CalendarIcon,
  UserIcon,
  ArrowPathIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  FunnelIcon,
  EllipsisVerticalIcon,
} from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { useWorkflowStore, WorkflowSortField } from '../../store/workflowStore';
import { componentStyles } from '../../styles/components';
import { Workflow } from '../../types/workflow';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { EmptyState } from '../common/EmptyState';
import { Pagination } from '../common/Pagination';
import UserDisplayName from '../common/UserDisplayName';
import { UnifiedSearch } from '../settings/UnifiedSearch';

import { WorkflowExecutionDialog } from './WorkflowExecutionDialog';

const getSchemaFields = (schema: Record<string, unknown>): string[] => {
  if (!schema || typeof schema !== 'object') return [];
  if ('properties' in schema && schema.properties && typeof schema.properties === 'object') {
    return Object.keys(schema.properties);
  }
  return Object.keys(schema).filter(
    (k) => !['type', 'title', 'description', '$schema'].includes(k)
  );
};

export const WorkflowsListSimple: React.FC = () => {
  const navigate = useNavigate();

  // Use the store for workflows data, but local state for pagination
  // This avoids Zustand timing issues with React StrictMode
  const {
    workflows,
    setWorkflows,
    totalCount,
    setTotalCount,
    searchTerm,
    setSearchTerm,
    sortField,
    sortDirection,
    setSorting,
  } = useWorkflowStore();

  // Use local state for pagination to avoid Zustand/React timing issues
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(20);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [executionDialog, setExecutionDialog] = useState<{
    isOpen: boolean;
    workflow: Workflow | null;
    loading: boolean;
  }>({
    isOpen: false,
    workflow: null,
    loading: false,
  });
  const [deleteConfirm, setDeleteConfirm] = useState<{
    isOpen: boolean;
    workflow: Workflow | null;
  }>({
    isOpen: false,
    workflow: null,
  });
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const menuRef = useRef<HTMLDivElement>(null);

  // Close overflow menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const { error, clearError, runSafe } = useErrorHandler('WorkflowsListSimple');

  // Fetch workflows when pagination, sorting, or search changes
  useEffect(() => {
    const fetchWorkflows = async () => {
      setLoading(true);

      try {
        // Build params using local state for pagination
        const params = {
          sort: sortField,
          order: sortDirection,
          limit: itemsPerPage,
          offset: (currentPage - 1) * itemsPerPage,
          ...(searchTerm.trim() ? { search: searchTerm.trim() } : {}),
        };

        const [response] = await runSafe(backendApi.getWorkflows(params as any), 'fetchWorkflows', {
          action: 'fetching workflows',
          params,
        });

        if (response) {
          setWorkflows(response.workflows || []);
          setTotalCount(response.total || 0);
        }
      } finally {
        setLoading(false);
      }
    };

    void fetchWorkflows();
  }, [
    currentPage,
    itemsPerPage,
    sortField,
    sortDirection,
    searchTerm,
    refreshKey,
    runSafe,
    setWorkflows,
    setTotalCount,
  ]);

  const handleExecuteClick = (workflow: Workflow) => {
    setExecutionDialog({
      isOpen: true,
      workflow,
      loading: false,
    });
  };

  const handleExecuteWorkflow = async (inputData: Record<string, any>) => {
    const workflow = executionDialog.workflow;
    if (!workflow) return;

    setExecutionDialog((prev) => ({ ...prev, loading: true }));

    try {
      const [result] = await runSafe(
        backendApi.executeWorkflow(workflow.id, { input_data: inputData }),
        'executeWorkflow',
        { action: 'executing workflow', entityId: workflow.id, params: inputData }
      );

      if (result) {
        // Close dialog and navigate to the dedicated workflow run page
        setExecutionDialog({ isOpen: false, workflow: null, loading: false });
        void navigate(`/workflow-runs/${result.workflow_run_id}`);
      }
    } catch (error) {
      console.error('Failed to execute workflow:', error);
    } finally {
      setExecutionDialog((prev) => ({ ...prev, loading: false }));
    }
  };

  const closeExecutionDialog = () => {
    setExecutionDialog({ isOpen: false, workflow: null, loading: false });
  };

  const handleViewClick = (workflow: Workflow) => {
    void navigate(`/workflows/${workflow.id}`);
  };

  const handleEditClick = (workflow: Workflow) => {
    void navigate(`/workflows/${workflow.id}/edit`);
  };

  const handleDeleteClick = (workflow: Workflow) => {
    setDeleteConfirm({ isOpen: true, workflow });
  };

  const handleConfirmDelete = async () => {
    const workflow = deleteConfirm.workflow;
    if (!workflow) return;

    const [, deleteError] = await runSafe(
      backendApi.deleteWorkflow(workflow.id),
      'deleteWorkflow',
      { action: 'deleting workflow', entityId: workflow.id }
    );

    setDeleteConfirm({ isOpen: false, workflow: null });

    if (!deleteError) {
      // Refresh the workflows list after successful deletion
      setRefreshKey((k) => k + 1);
    }
  };

  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage);
  };

  const handleItemsPerPageChange = (newItemsPerPage: number) => {
    setItemsPerPage(newItemsPerPage);
    setCurrentPage(1);
  };

  const renderSortIndicator = useMemo(
    function renderSortIndicator() {
      return function renderSortIcon(field: WorkflowSortField) {
        if (sortField !== field) return <></>;
        if (sortDirection === 'asc') return <ChevronUpIcon className="w-4 h-4 inline-block ml-1" />;
        return <ChevronDownIcon className="w-4 h-4 inline-block ml-1" />;
      };
    },
    [sortField, sortDirection]
  );

  const handleSort = (field: WorkflowSortField) => {
    // Reset to first page when sorting changes
    if (currentPage !== 1) {
      setCurrentPage(1);
    }
    // Toggle direction if same field, otherwise set new field with asc
    const newDirection = sortField === field && sortDirection === 'asc' ? 'desc' : 'asc';
    setSorting(field, newDirection);
  };

  const handleSearch = useCallback(
    (query: string) => {
      setSearchTerm(query);
      // Reset to first page when search changes
      setCurrentPage(1);
    },
    [setSearchTerm]
  );

  const toggleRowExpanded = (id: string) => {
    setExpandedRows((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="space-y-4">
      {/* Header with title, count and items per page */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-white">Workflows</h1>
            {totalCount > 0 && (
              <span className="px-2.5 py-0.5 rounded-full text-sm font-medium bg-dark-700 text-gray-100">
                {totalCount} {totalCount === 1 ? 'workflow' : 'workflows'}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-gray-400">Manage and execute workflow definitions</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <label htmlFor="workflows-items-per-page" className="text-sm text-gray-400">
              Show:
            </label>
            <select
              id="workflows-items-per-page"
              value={itemsPerPage}
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
            onClick={() => setRefreshKey((k) => k + 1)}
            disabled={loading}
            className="inline-flex items-center px-3 py-1.5 border border-gray-600 shadow-xs text-sm font-medium rounded-md text-gray-100 bg-dark-800 hover:bg-dark-700 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ArrowPathIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''} mr-1.5`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Search */}
      <UnifiedSearch
        value={searchTerm}
        onSearch={handleSearch}
        placeholder="Search workflows by name, description, or creator..."
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
                onClick={() => setRefreshKey((k) => k + 1)}
                className="px-3 py-1 text-sm bg-primary text-white rounded-sm hover:bg-primary/90"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Workflows Table */}
      <div className={componentStyles.card}>
        {totalCount > 0 && (
          <div className="mb-2">
            <Pagination
              currentPage={currentPage}
              totalPages={Math.ceil(totalCount / itemsPerPage)}
              totalItems={totalCount}
              itemsPerPage={itemsPerPage}
              onPageChange={handlePageChange}
            />
          </div>
        )}
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-700 table-fixed">
            <colgroup>
              <col style={{ width: '20%' }} />
              <col style={{ width: '25%' }} />
              <col style={{ width: '8%' }} />
              <col style={{ width: '8%' }} />
              <col style={{ width: '15%' }} />
              <col style={{ width: '12%' }} />
              <col style={{ width: '12%' }} />
            </colgroup>
            <thead className={componentStyles.tableHeader}>
              <tr>
                <th
                  className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                  onClick={() => handleSort('name')}
                >
                  Name {renderSortIndicator('name')}
                </th>
                <th
                  className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                  onClick={() => handleSort('description')}
                >
                  Description {renderSortIndicator('description')}
                </th>
                <th
                  className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                  onClick={() => handleSort('nodes')}
                >
                  Nodes {renderSortIndicator('nodes')}
                </th>
                <th
                  className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                  onClick={() => handleSort('edges')}
                >
                  Edges {renderSortIndicator('edges')}
                </th>
                <th
                  className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                  onClick={() => handleSort('created_by')}
                >
                  Created By {renderSortIndicator('created_by')}
                </th>
                <th
                  className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                  onClick={() => handleSort('created_at')}
                >
                  Created {renderSortIndicator('created_at')}
                </th>
                <th className={componentStyles.tableHeaderCell}>Actions</th>
              </tr>
            </thead>
            <tbody className={componentStyles.tableBody}>
              {loading && (
                <tr>
                  <td colSpan={7} className="text-center py-4">
                    <div className="flex justify-center items-center space-x-2">
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary"></div>
                      <span>Loading workflows...</span>
                    </div>
                  </td>
                </tr>
              )}
              {!loading && workflows.length === 0 && (
                <tr>
                  <td colSpan={7}>
                    <EmptyState
                      icon={FunnelIcon}
                      title="No workflows found"
                      message={
                        searchTerm
                          ? `No workflows match your search term "${searchTerm}".`
                          : 'No workflows are available at this time.'
                      }
                      actionLabel={searchTerm ? 'Clear Search' : undefined}
                      onAction={searchTerm ? () => setSearchTerm('') : undefined}
                    />
                  </td>
                </tr>
              )}
              {!loading &&
                workflows.map((workflow) => (
                  <React.Fragment key={workflow.id}>
                    <tr
                      className="hover:bg-dark-700 cursor-pointer transition-colors"
                      onClick={() => toggleRowExpanded(workflow.id)}
                    >
                      {/* Name */}
                      <td className="px-4 py-3">
                        <div className="flex items-start space-x-2">
                          <span
                            className="mt-0.5 text-gray-500 shrink-0"
                            aria-label={expandedRows[workflow.id] ? 'Collapse row' : 'Expand row'}
                          >
                            {expandedRows[workflow.id] ? (
                              <ChevronDownIcon className="h-4 w-4" />
                            ) : (
                              <ChevronRightIcon className="h-4 w-4" />
                            )}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-white wrap-break-word">
                              {workflow.name}
                            </div>
                            <div className="mt-1">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                                  workflow.is_dynamic
                                    ? 'bg-purple-900 text-purple-300'
                                    : 'bg-blue-900 text-blue-300'
                                }`}
                              >
                                {workflow.is_dynamic ? 'Dynamic' : 'Static'}
                              </span>
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Description */}
                      <td className="px-4 py-3">
                        <div className="text-sm text-gray-400 wrap-break-word line-clamp-2">
                          {workflow.description || (
                            <span className="text-gray-500 italic">No description</span>
                          )}
                        </div>
                      </td>

                      {/* Node Count */}
                      <td className="px-4 py-3 text-center">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-dark-700 text-gray-100">
                          {workflow.nodes?.length || 0}
                        </span>
                      </td>

                      {/* Edge Count */}
                      <td className="px-4 py-3 text-center">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-dark-700 text-gray-100">
                          {workflow.edges?.length || 0}
                        </span>
                      </td>

                      {/* Created By */}
                      <td className="px-4 py-3">
                        <div className="flex items-center space-x-1.5">
                          <UserIcon className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                          <span className="text-sm text-gray-400 wrap-break-word">
                            <UserDisplayName userId={workflow.created_by} />
                          </span>
                        </div>
                      </td>

                      {/* Created At */}
                      <td className="px-4 py-3">
                        <div className="flex items-center space-x-1.5">
                          <CalendarIcon className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                          <span className="text-sm text-gray-400">
                            {new Date(workflow.created_at).toLocaleString()}
                          </span>
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          {/* Primary: labeled Run button */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleExecuteClick(workflow);
                            }}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-sm text-xs font-medium bg-green-900/30 text-green-400 hover:bg-green-900/50 transition-colors border border-green-800/50"
                          >
                            <PlayIcon className="h-3.5 w-3.5" />
                            Run
                          </button>

                          {/* Secondary: ⋮ overflow menu */}
                          <div
                            className="relative"
                            ref={openMenuId === workflow.id ? menuRef : undefined}
                          >
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setOpenMenuId(openMenuId === workflow.id ? null : workflow.id);
                              }}
                              className="p-1.5 rounded-sm text-gray-400 hover:text-gray-200 hover:bg-dark-600 transition-colors"
                              title="More actions"
                            >
                              <EllipsisVerticalIcon className="h-4 w-4" />
                            </button>

                            {openMenuId === workflow.id && (
                              <div className="absolute right-0 top-full mt-1 w-36 z-20 bg-dark-800 border border-gray-700 rounded-lg shadow-xl py-1">
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setOpenMenuId(null);
                                    handleViewClick(workflow);
                                  }}
                                  className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-gray-300 hover:bg-dark-700 hover:text-white"
                                >
                                  <EyeIcon className="h-4 w-4 text-blue-400" />
                                  View
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setOpenMenuId(null);
                                    handleEditClick(workflow);
                                  }}
                                  className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-gray-300 hover:bg-dark-700 hover:text-white"
                                >
                                  <PencilSquareIcon className="h-4 w-4 text-pink-400" />
                                  Edit
                                </button>
                                <div className="my-1 border-t border-gray-700" />
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setOpenMenuId(null);
                                    handleDeleteClick(workflow);
                                  }}
                                  className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-red-400 hover:bg-red-900/20 hover:text-red-300"
                                >
                                  <TrashIcon className="h-4 w-4" />
                                  Delete
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>

                    {/* Expanded row */}
                    {expandedRows[workflow.id] && (
                      <tr>
                        <td
                          colSpan={7}
                          className="bg-dark-700 px-6 py-4 border-t border-b border-gray-700/50"
                        >
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm text-gray-300">
                            {/* Left column: metadata */}
                            <div className="space-y-1.5">
                              <p>
                                <span className="font-medium text-gray-100">ID:</span>{' '}
                                <span className="font-mono text-xs text-gray-400">
                                  {workflow.id}
                                </span>
                              </p>
                              <p>
                                <span className="font-medium text-gray-100">Created by:</span>{' '}
                                <UserDisplayName userId={workflow.created_by} />
                              </p>
                              <p>
                                <span className="font-medium text-gray-100">Created:</span>{' '}
                                {new Date(workflow.created_at).toLocaleString()}
                              </p>
                              {workflow.data_samples && workflow.data_samples.length > 0 && (
                                <p>
                                  <span className="font-medium text-gray-100">Data Samples:</span>{' '}
                                  {workflow.data_samples.length}
                                </p>
                              )}
                            </div>

                            {/* Right column: I/O schema */}
                            <div className="space-y-2">
                              {!!workflow.io_schema?.input &&
                                Object.keys(workflow.io_schema.input as Record<string, unknown>)
                                  .length > 0 && (
                                  <div>
                                    <span className="font-medium text-gray-100">Input Fields:</span>
                                    <div className="flex flex-wrap gap-1 mt-1">
                                      {getSchemaFields(
                                        workflow.io_schema.input as Record<string, unknown>
                                      ).map((field) => (
                                        <span
                                          key={field}
                                          className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-900/40 text-blue-300 border border-blue-800/50"
                                        >
                                          {field}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              {!!workflow.io_schema?.output &&
                                Object.keys(workflow.io_schema.output as Record<string, unknown>)
                                  .length > 0 && (
                                  <div>
                                    <span className="font-medium text-gray-100">
                                      Output Fields:
                                    </span>
                                    <div className="flex flex-wrap gap-1 mt-1">
                                      {getSchemaFields(
                                        workflow.io_schema.output as Record<string, unknown>
                                      ).map((field) => (
                                        <span
                                          key={field}
                                          className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-900/40 text-green-300 border border-green-800/50"
                                        >
                                          {field}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                            </div>
                          </div>

                          {/* Nodes breakdown */}
                          {workflow.nodes && workflow.nodes.length > 0 && (
                            <div className="mt-3 pt-3 border-t border-gray-700/50">
                              <span className="font-medium text-gray-100 text-sm">
                                Nodes ({workflow.nodes.length} total):
                              </span>
                              <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-3">
                                {(() => {
                                  const taskNodes = workflow.nodes.filter((n) => n.kind === 'task');
                                  const uniqueNames = [...new Set(taskNodes.map((n) => n.name))];
                                  return uniqueNames.length > 0 ? (
                                    <div>
                                      <div className="text-xs font-medium text-blue-400 uppercase mb-1">
                                        Tasks ({uniqueNames.length} unique)
                                      </div>
                                      <div className="flex flex-wrap gap-1">
                                        {uniqueNames.map((name) => (
                                          <span
                                            key={name}
                                            className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-blue-900/30 text-blue-300 border border-blue-800/50"
                                          >
                                            {name}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  ) : null;
                                })()}
                                {(() => {
                                  const transformNodes = workflow.nodes.filter(
                                    (n) => n.kind === 'transformation'
                                  );
                                  const uniqueNames = [
                                    ...new Set(transformNodes.map((n) => n.name)),
                                  ];
                                  return uniqueNames.length > 0 ? (
                                    <div>
                                      <div className="text-xs font-medium text-green-400 uppercase mb-1">
                                        Transformations ({uniqueNames.length} unique)
                                      </div>
                                      <div className="flex flex-wrap gap-1">
                                        {uniqueNames.map((name) => (
                                          <span
                                            key={name}
                                            className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-green-900/30 text-green-300 border border-green-800/50"
                                          >
                                            {name}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  ) : null;
                                })()}
                                {(() => {
                                  const foreachNodes = workflow.nodes.filter(
                                    (n) => n.kind === 'foreach'
                                  );
                                  const uniqueNames = [...new Set(foreachNodes.map((n) => n.name))];
                                  return uniqueNames.length > 0 ? (
                                    <div>
                                      <div className="text-xs font-medium text-orange-400 uppercase mb-1">
                                        Foreach ({uniqueNames.length} unique)
                                      </div>
                                      <div className="flex flex-wrap gap-1">
                                        {uniqueNames.map((name) => (
                                          <span
                                            key={name}
                                            className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-orange-900/30 text-orange-300 border border-orange-800/50"
                                          >
                                            {name}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  ) : null;
                                })()}
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
            </tbody>
          </table>
        </div>

        {Math.ceil(totalCount / itemsPerPage) > 1 && (
          <div className="mt-2">
            <Pagination
              currentPage={currentPage}
              totalPages={Math.ceil(totalCount / itemsPerPage)}
              totalItems={totalCount}
              itemsPerPage={itemsPerPage}
              onPageChange={handlePageChange}
            />
          </div>
        )}
      </div>

      {/* Execution Dialog */}
      <WorkflowExecutionDialog
        isOpen={executionDialog.isOpen}
        workflow={executionDialog.workflow}
        onClose={closeExecutionDialog}
        onExecute={(inputData) => void handleExecuteWorkflow(inputData)}
        loading={executionDialog.loading}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={() => setDeleteConfirm({ isOpen: false, workflow: null })}
        onConfirm={() => void handleConfirmDelete()}
        title="Delete Workflow?"
        message={`Are you sure you want to delete "${deleteConfirm.workflow?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="warning"
      />
    </div>
  );
};
