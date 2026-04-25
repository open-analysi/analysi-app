/* eslint-disable sonarjs/cognitive-complexity, sonarjs/function-return-type, sonarjs/no-nested-conditional, sonarjs/no-nested-functions */
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';

import { ChevronDownIcon, ChevronUpIcon, MagnifyingGlassIcon } from '@heroicons/react/24/outline';
import ReactMarkdown from 'react-markdown';
import { Link } from 'react-router';

import ErrorBoundary from '../components/common/ErrorBoundary';
import { Pagination } from '../components/common/Pagination';
import { TaskRunList } from '../components/common/TaskRunList';
import UserDisplayName from '../components/common/UserDisplayName';
import useErrorHandler from '../hooks/useErrorHandler';
import { useUrlState } from '../hooks/useUrlState';
import { backendApi } from '../services/backendApi';
import { componentStyles } from '../styles/components';
import { Alert } from '../types/alert';
import {
  TaskRun,
  TaskRunFilters,
  WorkflowRun,
  WorkflowRunFilters,
  TaskBuildingRun,
  TaskBuildingRunFilters,
  ExecutionType,
} from '../types/taskRun';
import { formatBytes, formatDuration, getDurationColorClass } from '../utils/formatUtils';

const TASK_BUILDING: ExecutionType = 'task-building';

const ExecutionHistory = () => {
  const [executionType, setExecutionType] = useUrlState<ExecutionType>('view', 'tasks');
  const [taskRuns, setTaskRuns] = useState<TaskRun[]>([]);
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [taskFilters, setTaskFilters] = useState<TaskRunFilters>({
    limit: 20,
    skip: 0,
    sort: 'started_at',
    order: 'desc',
  });
  const [workflowFilters, setWorkflowFilters] = useState<WorkflowRunFilters>({
    limit: 20,
    skip: 0,
    sort: 'started_at',
    order: 'desc',
  });
  const [taskBuildingRuns, setTaskBuildingRuns] = useState<TaskBuildingRun[]>([]);
  const [taskBuildingFilters, setTaskBuildingFilters] = useState<TaskBuildingRunFilters>({
    limit: 20,
    offset: 0,
    sort: 'created_at',
    order: 'desc',
  });
  const [expandedRow, setExpandedRow] = useState<string>();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);

  // Cache of fetched workflow run llm_usage (list endpoint returns null; detail endpoint has it)
  const [workflowRunLLMUsage, setWorkflowRunLLMUsage] = useState<
    Record<string, WorkflowRun['llm_usage']>
  >({});

  const { runSafe } = useErrorHandler('ExecutionHistory');
  const refreshIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Check if there are any running executions that need real-time updates
  const hasRunningExecutions = useCallback(() => {
    if (executionType === 'tasks') {
      return taskRuns.some((run) => run.status === 'running' || run.status === 'pending');
    } else if (executionType === 'workflows') {
      return workflowRuns.some(
        (run) => run.status === 'running' || run.status === 'pending' || run.status === 'paused'
      );
    } else {
      return taskBuildingRuns.some((run) => run.status === 'running' || run.status === 'pending');
    }
  }, [executionType, taskRuns, workflowRuns, taskBuildingRuns]);

  const loadTaskRuns = useCallback(
    async (newFilters?: Partial<TaskRunFilters>, silent = false) => {
      if (!silent) setLoading(true);

      try {
        const updatedFilters = { ...taskFilters, ...newFilters };

        const [response] = await runSafe(backendApi.getTaskRuns(updatedFilters), 'loadTaskRuns', {
          action: 'fetching task runs',
          params: updatedFilters,
        });

        if (response) {
          setTaskRuns(response.task_runs ?? []);
          setTotal(response.total ?? response.task_runs?.length ?? 0);
        }
      } finally {
        setLoading(false);
      }
    },
    [taskFilters, runSafe]
  );

  const loadWorkflowRuns = useCallback(
    async (newFilters?: Partial<WorkflowRunFilters>, silent = false) => {
      if (!silent) setLoading(true);

      try {
        const updatedFilters = { ...workflowFilters, ...newFilters };

        const [response] = (await runSafe(
          backendApi.getWorkflowRuns(updatedFilters),
          'loadWorkflowRuns',
          {
            action: 'fetching workflow runs',
            params: updatedFilters,
          }
        )) as [{ runs?: WorkflowRun[]; total?: number } | undefined, unknown];

        if (response) {
          setWorkflowRuns(response.runs ?? []);
          setTotal(response.total ?? response.runs?.length ?? 0);
        }
      } finally {
        setLoading(false);
      }
    },
    [workflowFilters, runSafe]
  );

  const loadTaskBuildingRuns = useCallback(
    async (newFilters?: Partial<TaskBuildingRunFilters>, silent = false) => {
      if (!silent) setLoading(true);

      try {
        const updatedFilters = { ...taskBuildingFilters, ...newFilters };

        const [response] = await runSafe(
          backendApi.getTaskBuildingRuns(updatedFilters),
          'loadTaskBuildingRuns',
          {
            action: 'fetching task building runs',
            params: updatedFilters,
          }
        );

        if (response) {
          setTaskBuildingRuns(response.task_building_runs ?? []);
          setTotal(response.total ?? response.task_building_runs?.length ?? 0);
        }
      } finally {
        setLoading(false);
      }
    },
    [taskBuildingFilters, runSafe]
  );

  // Load alerts for the dropdown filter
  const loadAlerts = useCallback(async () => {
    setAlertsLoading(true);
    try {
      const [response] = await runSafe(
        backendApi.getAlerts({ limit: 100, sort: 'created_at', order: 'desc' }),
        'loadAlerts',
        { action: 'fetching alerts for filter dropdown' }
      );
      if (response && response.alerts) {
        setAlerts(response.alerts);
      }
    } finally {
      setAlertsLoading(false);
    }
  }, [runSafe]);

  // Load data based on execution type
  const loadData = useCallback(
    (silent = false): Promise<void> => {
      if (executionType === 'tasks') return loadTaskRuns(undefined, silent);
      if (executionType === 'workflows') return loadWorkflowRuns(undefined, silent);
      return loadTaskBuildingRuns(undefined, silent);
    },
    [executionType, loadTaskRuns, loadWorkflowRuns, loadTaskBuildingRuns]
  );

  useEffect(() => {
    loadData().catch(() => undefined);
  }, [loadData]);

  // Load alerts on mount for the filter dropdown
  useEffect(() => {
    void loadAlerts();
  }, [loadAlerts]);

  // Auto-refresh effect for running executions
  useEffect(() => {
    const startAutoRefresh = () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }

      if (autoRefresh && hasRunningExecutions()) {
        refreshIntervalRef.current = setInterval(() => {
          console.log('Auto-refreshing due to running executions...');
          loadData(true).catch(() => undefined); // Silent refresh to avoid loading spinners
        }, 5000); // Refresh every 5 seconds when there are running executions
      }
    };

    startAutoRefresh();

    // Cleanup interval on unmount or when conditions change
    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
        refreshIntervalRef.current = null;
      }
    };
  }, [autoRefresh, hasRunningExecutions, loadData]);

  // Handle execution type change
  const handleExecutionTypeChange = (newType: ExecutionType) => {
    setExecutionType(newType);
    setCurrentPage(1);
    setExpandedRow(undefined);
    // Reset to first page
    if (newType === 'tasks') {
      const newFilters = { ...taskFilters, skip: 0 };
      setTaskFilters(newFilters);
    } else if (newType === 'workflows') {
      const newFilters = { ...workflowFilters, skip: 0 };
      setWorkflowFilters(newFilters);
    } else if (newType === TASK_BUILDING) {
      const newFilters = { ...taskBuildingFilters, offset: 0 };
      setTaskBuildingFilters(newFilters);
    }
  };

  const handleSearch = (searchTerm: string) => {
    setCurrentPage(1);
    if (executionType === 'tasks') {
      const newFilters = { ...taskFilters, search: searchTerm, skip: 0 };
      setTaskFilters(newFilters);
      void loadTaskRuns(newFilters, false);
    } else if (executionType === 'workflows') {
      const newFilters = { ...workflowFilters, search: searchTerm, skip: 0 };
      setWorkflowFilters(newFilters);
      void loadWorkflowRuns(newFilters, false);
    } else if (executionType === TASK_BUILDING) {
      // Task building runs filter by workflow_generation_id, not search
      void loadTaskBuildingRuns(undefined, false);
    }
  };

  const handleWorkflowFilter = (workflowId: string) => {
    setCurrentPage(1);
    if (executionType === 'workflows') {
      const newFilters = {
        ...workflowFilters,
        workflow_id: workflowId || undefined,
        skip: 0,
      };
      setWorkflowFilters(newFilters);
      void loadWorkflowRuns(newFilters, false);
    }
  };

  const handleAlertFilter = async (alertId: string) => {
    setCurrentPage(1);
    setSelectedAlertId(alertId || null);

    if (!alertId) {
      // No alert selected - clear the workflow_run_id filter and show all tasks
      const newFilters = {
        ...taskFilters,
        workflow_run_id: undefined,
        skip: 0,
      };
      setTaskFilters(newFilters);
      void loadTaskRuns(newFilters, false);
      return;
    }

    // Alert selected - fetch analyses to get workflow_run_ids
    setLoading(true);
    try {
      const [analyses] = await runSafe(backendApi.getAlertAnalyses(alertId), 'handleAlertFilter', {
        action: 'fetching alert analyses for workflow_run_ids',
        entityId: alertId,
      });

      if (analyses && Array.isArray(analyses)) {
        // Extract unique workflow_run_ids from analyses
        const workflowRunIds = analyses
          .map((a) => a.workflow_run_id)
          .filter((id): id is string => !!id);

        if (workflowRunIds.length > 0) {
          // Use the workflow_run_ids to filter task runs
          // If backend supports multiple IDs, we could pass them as comma-separated
          // For now, we'll use the most recent one (first in the list after sorting by date)
          const newFilters = {
            ...taskFilters,
            workflow_run_id: workflowRunIds.join(','), // Try comma-separated list
            skip: 0,
          };
          setTaskFilters(newFilters);
          void loadTaskRuns(newFilters, false);
        } else {
          // No workflow runs found for this alert - show empty results
          setTaskRuns([]);
          setTotal(0);
          setLoading(false);
        }
      } else {
        // No analyses found - show empty results
        setTaskRuns([]);
        setTotal(0);
        setLoading(false);
      }
    } catch {
      setLoading(false);
    }
  };

  const handleStatusFilter = (status: string) => {
    setCurrentPage(1);
    if (executionType === 'tasks') {
      const newFilters = { ...taskFilters, status: status === 'all' ? undefined : status, skip: 0 };
      setTaskFilters(newFilters);
      void loadTaskRuns(newFilters, false);
    } else if (executionType === 'workflows') {
      const newFilters = {
        ...workflowFilters,
        status: status === 'all' ? undefined : status,
        skip: 0,
      };
      setWorkflowFilters(newFilters);
      void loadWorkflowRuns(newFilters, false);
    } else if (executionType === TASK_BUILDING) {
      const newFilters = {
        ...taskBuildingFilters,
        status: status === 'all' ? undefined : status,
        offset: 0,
      };
      setTaskBuildingFilters(newFilters);
      void loadTaskBuildingRuns(newFilters, false);
    }
  };

  const handleSort = (column: string) => {
    if (executionType === 'tasks') {
      const newOrder: 'asc' | 'desc' =
        taskFilters.sort === column && taskFilters.order === 'asc' ? 'desc' : 'asc';
      const newFilters = { ...taskFilters, sort: column, order: newOrder };
      setTaskFilters(newFilters);
      void loadTaskRuns(newFilters, false);
    } else if (executionType === 'workflows') {
      const newOrder: 'asc' | 'desc' =
        workflowFilters.sort === column && workflowFilters.order === 'asc' ? 'desc' : 'asc';
      const newFilters = { ...workflowFilters, sort: column, order: newOrder };
      setWorkflowFilters(newFilters);
      void loadWorkflowRuns(newFilters, false);
    } else if (executionType === TASK_BUILDING) {
      const newOrder: 'asc' | 'desc' =
        taskBuildingFilters.sort === column && taskBuildingFilters.order === 'asc' ? 'desc' : 'asc';
      const newFilters = { ...taskBuildingFilters, sort: column, order: newOrder };
      setTaskBuildingFilters(newFilters);
      void loadTaskBuildingRuns(newFilters, false);
    }
  };

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    if (executionType === 'tasks') {
      const newSkip = (page - 1) * (taskFilters.limit || 20);
      const newFilters = { ...taskFilters, skip: newSkip };
      setTaskFilters(newFilters);
      void loadTaskRuns(newFilters, false);
    } else if (executionType === 'workflows') {
      const newSkip = (page - 1) * (workflowFilters.limit || 20);
      const newFilters = { ...workflowFilters, skip: newSkip };
      setWorkflowFilters(newFilters);
      void loadWorkflowRuns(newFilters, false);
    } else if (executionType === TASK_BUILDING) {
      const newOffset = (page - 1) * (taskBuildingFilters.limit || 20);
      const newFilters = { ...taskBuildingFilters, offset: newOffset };
      setTaskBuildingFilters(newFilters);
      void loadTaskBuildingRuns(newFilters, false);
    }
  };

  // Fetch individual workflow run detail to get llm_usage (list endpoint returns null for it)
  const handleExpandWorkflowRow = useCallback(
    async (runId: string) => {
      // Toggle: collapse if already expanded
      if (expandedRow === runId) {
        setExpandedRow(undefined);
        return;
      }
      setExpandedRow(runId);

      // Fetch detail only if not already cached
      if (!(runId in workflowRunLLMUsage)) {
        const [detail] = await runSafe(
          backendApi.getWorkflowRun(runId),
          'handleExpandWorkflowRow',
          { action: 'fetching workflow run detail for llm_usage', entityId: runId }
        );
        if (detail) {
          const typedDetail = detail as unknown as WorkflowRun;
          setWorkflowRunLLMUsage((prev) => ({ ...prev, [runId]: typedDetail.llm_usage ?? null }));
        }
      }
    },
    [expandedRow, workflowRunLLMUsage, runSafe]
  );

  // Status badge helpers for workflow runs only
  const getStatusBadge = (status: WorkflowRun['status']) => {
    const baseClasses = 'px-2 py-1 text-xs font-medium rounded-full';
    switch (status) {
      case 'completed': {
        return `${baseClasses} bg-green-100 text-green-800 dark:bg-green-800 dark:text-green-200`;
      }
      case 'failed': {
        return `${baseClasses} bg-red-100 text-red-800 dark:bg-red-800 dark:text-red-200`;
      }
      case 'running': {
        return `${baseClasses} bg-blue-100 text-blue-800 dark:bg-blue-800 dark:text-blue-200`;
      }
      case 'pending': {
        return `${baseClasses} bg-yellow-100 text-yellow-800 dark:bg-yellow-800 dark:text-yellow-200`;
      }
      case 'cancelled': {
        return `${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200`;
      }
      case 'paused': {
        return `${baseClasses} bg-amber-100 text-amber-800 dark:bg-amber-800 dark:text-amber-200`;
      }
      default: {
        return `${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200`;
      }
    }
  };

  const getStatusIcon = (status: WorkflowRun['status']) => {
    switch (status) {
      case 'completed': {
        return '✓';
      }
      case 'failed': {
        return '✗';
      }
      case 'running': {
        return '↻';
      }
      case 'pending': {
        return '⏱';
      }
      case 'cancelled': {
        return '⊘';
      }
      case 'paused': {
        return '⏸';
      }
      default: {
        return '?';
      }
    }
  };

  // Status badge helpers for task building runs
  const getTaskBuildingStatusBadge = (status: TaskBuildingRun['status']) => {
    const baseClasses = 'px-2 py-1 text-xs font-medium rounded-full';
    switch (status) {
      case 'completed': {
        return `${baseClasses} bg-green-100 text-green-800 dark:bg-green-800 dark:text-green-200`;
      }
      case 'failed': {
        return `${baseClasses} bg-red-100 text-red-800 dark:bg-red-800 dark:text-red-200`;
      }
      case 'running': {
        return `${baseClasses} bg-blue-100 text-blue-800 dark:bg-blue-800 dark:text-blue-200`;
      }
      case 'pending': {
        return `${baseClasses} bg-yellow-100 text-yellow-800 dark:bg-yellow-800 dark:text-yellow-200`;
      }
      case 'cancelled': {
        return `${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200`;
      }
      default: {
        return `${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200`;
      }
    }
  };

  const getTaskBuildingStatusIcon = (status: TaskBuildingRun['status']) => {
    switch (status) {
      case 'completed': {
        return '✓';
      }
      case 'failed': {
        return '✗';
      }
      case 'running': {
        return '↻';
      }
      case 'pending': {
        return '⏱';
      }
      case 'cancelled': {
        return '⊘';
      }
      default: {
        return '?';
      }
    }
  };

  const getCurrentFilters = () => {
    if (executionType === 'tasks') return taskFilters;
    if (executionType === 'workflows') return workflowFilters;
    return taskBuildingFilters;
  };
  const currentFilters = getCurrentFilters();
  const totalPages = Math.ceil(total / (currentFilters.limit || 20));

  const renderSortIndicator = useMemo(
    function renderSortIndicator() {
      return function renderSortIcon(field: string) {
        if (currentFilters.sort !== field) return <></>;
        if (currentFilters.order === 'asc')
          return <ChevronUpIcon className="w-4 h-4 inline-block ml-1" />;
        return <ChevronDownIcon className="w-4 h-4 inline-block ml-1" />;
      };
    },
    [currentFilters.sort, currentFilters.order]
  );

  return (
    <ErrorBoundary
      component="ExecutionHistory"
      fallback={
        <div className={componentStyles.pageBackground}>
          <div className="py-6 px-4 sm:px-6 md:px-8">
            <div className="p-6 border border-red-700 bg-red-900/30 rounded-md">
              <h2 className="text-xl font-semibold mb-2 text-gray-100">
                Error loading execution history
              </h2>
              <p className="text-gray-300 mb-4">
                There was an error rendering the execution history page.
              </p>
              <button
                onClick={() => window.location.reload()}
                className="px-4 py-2 bg-primary rounded-md text-white hover:bg-primary/90"
              >
                Reload page
              </button>
            </div>
          </div>
        </div>
      }
    >
      <div className={componentStyles.pageBackground} data-testid="execution-history-page">
        <div className="py-6 px-4 sm:px-6 md:px-8">
          {/* Header */}
          <div className="mb-6">
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
              Execution History
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              Monitor and search all{' '}
              {executionType === 'tasks'
                ? 'task'
                : executionType === 'workflows'
                  ? 'workflow'
                  : 'task building'}{' '}
              execution history
            </p>
          </div>

          {/* Filters Bar */}
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 mb-6">
            <div className="flex flex-col md:flex-row gap-4 mb-4">
              {/* Auto-refresh controls */}
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <input
                    type="checkbox"
                    checked={autoRefresh}
                    onChange={(e) => setAutoRefresh(e.target.checked)}
                    className="rounded-sm border-gray-300 dark:border-gray-600 text-primary focus:ring-primary"
                  />
                  Auto-refresh running executions
                </label>
                {hasRunningExecutions() && autoRefresh && (
                  <div className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
                    <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-600"></div>
                    Live updates active
                  </div>
                )}
                <button
                  onClick={() => {
                    loadData().catch(() => undefined);
                  }}
                  className="px-3 py-1 text-xs bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-sm text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600"
                >
                  ↻ Refresh Now
                </button>
              </div>
            </div>
            <div className="flex flex-col md:flex-row gap-4">
              {/* Search */}
              <div className="flex-1">
                <div className="relative">
                  <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search by task name..."
                    className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-primary focus:border-primary"
                    onChange={(e) => handleSearch(e.target.value)}
                  />
                </div>
              </div>

              {/* Run Type */}
              <div className="relative">
                <select
                  value={executionType}
                  onChange={(e) => handleExecutionTypeChange(e.target.value as ExecutionType)}
                  className="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 text-sm rounded-lg focus:ring-primary focus:border-primary block w-full p-2.5 pr-8 appearance-none"
                >
                  <option value="tasks">Task Runs</option>
                  <option value="workflows">Workflow Runs</option>
                  <option value="task-building">Task Building Runs</option>
                </select>
                <ChevronDownIcon className="absolute right-2 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
              </div>

              {/* Status Filter */}
              <div className="relative">
                <select
                  onChange={(e) => handleStatusFilter(e.target.value)}
                  className="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 text-sm rounded-lg focus:ring-primary focus:border-primary block w-full p-2.5 pr-8 appearance-none"
                >
                  <option value="all">All Statuses</option>
                  <option value="succeeded">Succeeded</option>
                  <option value="failed">Failed</option>
                  <option value="running">Running</option>
                  <option value="pending">Pending</option>
                  <option value="paused">Paused (HITL)</option>
                </select>
                <ChevronDownIcon className="absolute right-2 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
              </div>

              {/* Alert filter — shown for task runs */}
              {executionType === 'tasks' && (
                <div className="relative">
                  <select
                    value={selectedAlertId || ''}
                    onChange={(e) => void handleAlertFilter(e.target.value)}
                    className="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 text-sm rounded-lg focus:ring-primary focus:border-primary block w-full p-2.5 pr-8 appearance-none min-w-[250px]"
                    disabled={alertsLoading || loading}
                  >
                    <option value="">All Alerts</option>
                    {alerts.map((alert) => (
                      <option key={alert.alert_id} value={alert.alert_id}>
                        {alert.human_readable_id} -{' '}
                        {alert.title.length > 40 ? `${alert.title.slice(0, 40)}...` : alert.title}
                      </option>
                    ))}
                  </select>
                  <ChevronDownIcon className="absolute right-2 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
                </div>
              )}

              {/* Workflow filter — shown for workflow runs only */}
              {executionType === 'workflows' && (
                <div className="relative">
                  <input
                    type="text"
                    placeholder="Filter by workflow ID…"
                    className="bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 text-sm rounded-lg focus:ring-primary focus:border-primary block w-full p-2.5 pr-3 min-w-[200px]"
                    onChange={(e) => handleWorkflowFilter(e.target.value.trim())}
                  />
                </div>
              )}
            </div>
          </div>

          {/* Table */}
          <div className={componentStyles.card}>
            {/* Pagination at top for consistency with other tables */}
            {!loading && totalPages > 1 && (
              <div className="mb-2">
                <Pagination
                  currentPage={currentPage}
                  totalPages={totalPages}
                  totalItems={total}
                  itemsPerPage={currentFilters.limit || 20}
                  onPageChange={handlePageChange}
                />
              </div>
            )}

            {executionType === 'tasks' ? (
              <TaskRunList
                taskRuns={taskRuns}
                loading={loading}
                showWorkflowRunId={false}
                hidePagination
              />
            ) : executionType === 'workflows' ? (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 table-auto">
                  <colgroup>
                    <col className="w-[20%] min-w-[180px]" />
                    <col className="w-[10%] min-w-[90px]" />
                    <col className="w-[16%] min-w-[140px]" />
                    <col className="w-[10%] min-w-[90px]" />
                    <col className="w-[10%] min-w-[90px]" />
                    <col className="w-[10%] min-w-[90px]" />
                    <col className="w-[10%] min-w-[90px]" />
                    <col className="w-[14%] min-w-[100px]" />
                  </colgroup>
                  <thead className={componentStyles.tableHeader}>
                    <tr>
                      <th
                        className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                        onClick={() => handleSort('workflow_name')}
                      >
                        Workflow Name
                        {renderSortIndicator('workflow_name')}
                      </th>
                      <th className={componentStyles.tableHeaderCell}>Status</th>
                      <th
                        className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                        onClick={() => handleSort('started_at')}
                      >
                        Started At
                        {renderSortIndicator('started_at')}
                      </th>
                      <th
                        className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                        onClick={() => handleSort('duration')}
                      >
                        Duration
                        {renderSortIndicator('duration')}
                      </th>
                      <th className={componentStyles.tableHeaderCell}>Input Size</th>
                      <th className={componentStyles.tableHeaderCell}>Output Size</th>
                      <th className={componentStyles.tableHeaderCell}>LLM Cost</th>
                      <th className={componentStyles.tableHeaderCell}>Actions</th>
                    </tr>
                  </thead>
                  <tbody className={componentStyles.tableBody}>
                    {loading ? (
                      <tr>
                        <td colSpan={7} className="px-6 py-12 text-center">
                          <div className="flex items-center justify-center space-x-3">
                            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
                            <span className="text-gray-500 dark:text-gray-400">
                              Loading workflow runs...
                            </span>
                          </div>
                        </td>
                      </tr>
                    ) : workflowRuns.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-6 py-12 text-center">
                          <div className="text-gray-500 dark:text-gray-400">
                            <div className="text-lg font-medium mb-2">No Workflow Runs Found</div>
                            <div className="text-sm">
                              No workflows have been executed yet, or your filters are too
                              restrictive.
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      workflowRuns.map((run) => (
                        <React.Fragment key={run.id}>
                          <tr className={componentStyles.tableRow}>
                            <td className={`${componentStyles.tableCell} wrap-break-word`}>
                              <button
                                onClick={() => void handleExpandWorkflowRow(run.id)}
                                className="text-left hover:text-primary font-medium"
                              >
                                {run.workflow_name || run.workflow_id || 'Unnamed Workflow'}
                              </button>
                            </td>
                            <td className={componentStyles.tableCell}>
                              <span className={getStatusBadge(run.status)}>
                                {getStatusIcon(run.status)} {run.status}
                              </span>
                            </td>
                            <td
                              className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}
                            >
                              {run.started_at
                                ? new Date(run.started_at).toLocaleString()
                                : 'Not started'}
                            </td>
                            <td className={componentStyles.tableCell}>
                              {(() => {
                                const durationInput = run.duration
                                  ? run.duration
                                  : run.started_at && run.completed_at
                                    ? `PT${(new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000}S`
                                    : null;
                                if (!durationInput) {
                                  return run.started_at ? (
                                    <span className="text-gray-600 dark:text-gray-400">
                                      Running...
                                    </span>
                                  ) : (
                                    '-'
                                  );
                                }
                                return (
                                  <span
                                    className={`font-medium ${getDurationColorClass(durationInput, 'workflow')}`}
                                  >
                                    {formatDuration(durationInput)}
                                  </span>
                                );
                              })()}
                            </td>
                            <td
                              className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}
                            >
                              {run.input_data
                                ? formatBytes(
                                    new TextEncoder().encode(JSON.stringify(run.input_data)).length
                                  )
                                : '-'}
                            </td>
                            <td
                              className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}
                            >
                              {run.output_data
                                ? formatBytes(
                                    new TextEncoder().encode(JSON.stringify(run.output_data)).length
                                  )
                                : '-'}
                            </td>
                            <td
                              className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}
                            >
                              {(run.llm_usage?.cost_usd ?? workflowRunLLMUsage[run.id]?.cost_usd) !=
                              null ? (
                                <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                                  $
                                  {(
                                    run.llm_usage?.cost_usd ?? workflowRunLLMUsage[run.id]?.cost_usd
                                  )?.toFixed(4)}
                                </span>
                              ) : (
                                '-'
                              )}
                            </td>
                            <td
                              className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}
                            >
                              <button
                                onClick={() => void handleExpandWorkflowRow(run.id)}
                                className="text-primary hover:text-primary/80 font-medium"
                              >
                                {run.status === 'running' ? 'Live Status' : 'View Details'}
                              </button>
                            </td>
                          </tr>
                          {expandedRow === run.id && (
                            <tr>
                              <td
                                colSpan={8}
                                className="px-6 py-4 bg-dark-700/50 border-t border-gray-700"
                              >
                                <div className="space-y-4">
                                  <div className="flex justify-between items-center">
                                    <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                                      Workflow Run Details - WRID: {run.id}
                                    </h3>
                                    <div className="flex items-center gap-2">
                                      <Link
                                        to={`/workflow-runs/${run.id}`}
                                        className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors font-medium text-sm"
                                      >
                                        View Workflow Graph
                                      </Link>
                                      <button
                                        onClick={() => setExpandedRow(undefined)}
                                        className="text-gray-400 hover:text-gray-200"
                                      >
                                        ✕
                                      </button>
                                    </div>
                                  </div>

                                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
                                      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                        Execution Info
                                      </h4>
                                      <div className="text-sm text-gray-800 dark:text-gray-200 space-y-1">
                                        <div>
                                          <strong>Workflow ID:</strong> {run.workflow_id}
                                        </div>
                                        <div>
                                          <strong>Status:</strong> {run.status}
                                        </div>
                                        <div>
                                          <strong>Progress:</strong> {run.progress || 'N/A'}
                                        </div>
                                        <div>
                                          <strong>Created:</strong>{' '}
                                          {new Date(run.created_at).toLocaleString()}
                                        </div>
                                        <div>
                                          <strong>Started:</strong>{' '}
                                          {run.started_at
                                            ? new Date(run.started_at).toLocaleString()
                                            : 'Not started'}
                                        </div>
                                        <div>
                                          <strong>Ended:</strong>{' '}
                                          {run.completed_at
                                            ? new Date(run.completed_at).toLocaleString()
                                            : 'Not finished'}
                                        </div>
                                        {(run.llm_usage || workflowRunLLMUsage[run.id]) && (
                                          <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-600">
                                            <div className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                                              LLM Usage (aggregate)
                                            </div>
                                            {(() => {
                                              const usage =
                                                run.llm_usage ?? workflowRunLLMUsage[run.id];
                                              if (!usage) return null;
                                              return (
                                                <>
                                                  {usage.cost_usd != null && (
                                                    <div>
                                                      <strong>Cost:</strong>{' '}
                                                      <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
                                                        ${usage.cost_usd.toFixed(4)}
                                                      </span>
                                                    </div>
                                                  )}
                                                  <div>
                                                    <strong>Tokens in:</strong>{' '}
                                                    {usage.input_tokens.toLocaleString()}
                                                  </div>
                                                  <div>
                                                    <strong>Tokens out:</strong>{' '}
                                                    {usage.output_tokens.toLocaleString()}
                                                  </div>
                                                  <div>
                                                    <strong>Total tokens:</strong>{' '}
                                                    {usage.total_tokens.toLocaleString()}
                                                  </div>
                                                </>
                                              );
                                            })()}
                                          </div>
                                        )}
                                      </div>
                                    </div>

                                    <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
                                      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                        Input Data
                                      </h4>
                                      <div className="text-sm text-gray-800 dark:text-gray-200">
                                        {run.input_data ? (
                                          <pre className="whitespace-pre-wrap wrap-break-word bg-gray-100 dark:bg-gray-700 p-2 rounded-sm text-xs max-h-32 overflow-y-auto">
                                            {JSON.stringify(run.input_data, null, 2)}
                                          </pre>
                                        ) : (
                                          <span className="text-gray-500">No input data</span>
                                        )}
                                      </div>
                                    </div>

                                    <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
                                      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                        Output Data
                                      </h4>
                                      <div className="text-sm text-gray-800 dark:text-gray-200">
                                        {run.output_data ? (
                                          <pre className="whitespace-pre-wrap wrap-break-word bg-gray-100 dark:bg-gray-700 p-2 rounded-sm text-xs max-h-32 overflow-y-auto">
                                            {JSON.stringify(run.output_data, null, 2)}
                                          </pre>
                                        ) : (
                                          <span className="text-gray-500">No output data yet</span>
                                        )}
                                      </div>
                                    </div>

                                    {run.execution_context && (
                                      <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600 md:col-span-2 lg:col-span-3">
                                        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                          Execution Context
                                        </h4>
                                        <div className="text-sm text-gray-800 dark:text-gray-200">
                                          <pre className="whitespace-pre-wrap wrap-break-word bg-gray-100 dark:bg-gray-700 p-2 rounded-sm text-xs max-h-32 overflow-y-auto">
                                            {JSON.stringify(run.execution_context, null, 2)}
                                          </pre>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              /* Task Building Runs Table */
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 table-auto">
                  <colgroup>
                    <col className="w-[12%] min-w-[100px]" />
                    <col className="w-[10%] min-w-[90px]" />
                    <col className="w-[22%] min-w-[180px]" />
                    <col className="w-[14%] min-w-[120px]" />
                    <col className="w-[16%] min-w-[140px]" />
                    <col className="w-[13%] min-w-[100px]" />
                    <col className="w-[13%] min-w-[100px]" />
                  </colgroup>
                  <thead className={componentStyles.tableHeader}>
                    <tr>
                      <th
                        className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                        onClick={() => handleSort('id')}
                      >
                        Run ID
                        {renderSortIndicator('id')}
                      </th>
                      <th className={componentStyles.tableHeaderCell}>Status</th>
                      <th className={componentStyles.tableHeaderCell}>Created Task</th>
                      <th className={componentStyles.tableHeaderCell}>Source</th>
                      <th
                        className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                        onClick={() => handleSort('created_at')}
                      >
                        Created At
                        {renderSortIndicator('created_at')}
                      </th>
                      <th className={componentStyles.tableHeaderCell}>Created By</th>
                      <th className={componentStyles.tableHeaderCell}>Actions</th>
                    </tr>
                  </thead>
                  <tbody className={componentStyles.tableBody}>
                    {loading ? (
                      <tr>
                        <td colSpan={7} className="px-6 py-12 text-center">
                          <div className="flex items-center justify-center space-x-3">
                            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
                            <span className="text-gray-500 dark:text-gray-400">
                              Loading task building runs...
                            </span>
                          </div>
                        </td>
                      </tr>
                    ) : taskBuildingRuns.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-6 py-12 text-center">
                          <div className="text-gray-500 dark:text-gray-400">
                            <div className="text-lg font-medium mb-2">
                              No Task Building Runs Found
                            </div>
                            <div className="text-sm">
                              No task building runs have been executed yet, or your filters are too
                              restrictive.
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      taskBuildingRuns.map((run) => (
                        <React.Fragment key={run.id}>
                          <tr className={componentStyles.tableRow}>
                            <td className={`${componentStyles.tableCell} wrap-break-word`}>
                              <button
                                onClick={() =>
                                  setExpandedRow(expandedRow === run.id ? undefined : run.id)
                                }
                                className="text-left hover:text-primary font-medium font-mono text-xs"
                              >
                                {run.id?.slice(0, 8) ?? 'N/A'}...
                              </button>
                            </td>
                            <td className={componentStyles.tableCell}>
                              <span className={getTaskBuildingStatusBadge(run.status)}>
                                {getTaskBuildingStatusIcon(run.status)}{' '}
                                {run.status?.replace('_', ' ') ?? 'Unknown'}
                              </span>
                            </td>
                            <td className={componentStyles.tableCell}>
                              {(() => {
                                const result = run.result as {
                                  task_id?: string;
                                  cy_name?: string;
                                } | null;
                                if (run.status === 'completed' && result?.task_id) {
                                  return (
                                    <Link
                                      to={`/workbench?taskId=${result.task_id}`}
                                      className="text-primary hover:text-primary/80 hover:underline font-medium"
                                      title={`Open in Workbench: ${result.cy_name || result.task_id}`}
                                    >
                                      {result.cy_name || result.task_id.slice(0, 8)}
                                    </Link>
                                  );
                                }
                                if (run.status === 'running') {
                                  return <span className="text-gray-500 italic">Building...</span>;
                                }
                                if (run.status === 'failed') {
                                  return <span className="text-red-400">—</span>;
                                }
                                return <span className="text-gray-500">—</span>;
                              })()}
                            </td>
                            <td
                              className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}
                            >
                              {run.workflow_generation_id ? (
                                <span className="font-mono text-xs">
                                  {run.workflow_generation_id.slice(0, 8)}...
                                </span>
                              ) : (
                                <span className="text-yellow-500">Ad-hoc</span>
                              )}
                            </td>
                            <td
                              className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}
                            >
                              {new Date(run.created_at).toLocaleString()}
                            </td>
                            <td
                              className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}
                            >
                              <UserDisplayName userId={run.created_by} />
                            </td>
                            <td
                              className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}
                            >
                              <button
                                onClick={() =>
                                  setExpandedRow(expandedRow === run.id ? undefined : run.id)
                                }
                                className="text-primary hover:text-primary/80 font-medium"
                              >
                                {run.status === 'running' ? 'Live Status' : 'View Details'}
                              </button>
                            </td>
                          </tr>
                          {expandedRow === run.id && (
                            <tr>
                              <td
                                colSpan={7}
                                className="px-6 py-4 bg-dark-700/50 border-t border-gray-700"
                              >
                                <div className="space-y-4">
                                  <div className="flex justify-between items-center">
                                    <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                                      Task Building Run Details
                                    </h3>
                                    <button
                                      onClick={() => setExpandedRow(undefined)}
                                      className="text-gray-400 hover:text-gray-200"
                                    >
                                      ✕
                                    </button>
                                  </div>

                                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                                    <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
                                      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                        Run Info
                                      </h4>
                                      <div className="text-sm text-gray-800 dark:text-gray-200 space-y-1">
                                        <div>
                                          <strong>ID:</strong>{' '}
                                          <span className="font-mono text-xs">{run.id}</span>
                                        </div>
                                        <div>
                                          <strong>Status:</strong> {run.status}
                                        </div>
                                        <div>
                                          <strong>Created:</strong>{' '}
                                          {new Date(run.created_at).toLocaleString()}
                                        </div>
                                        <div>
                                          <strong>Updated:</strong>{' '}
                                          {new Date(run.updated_at).toLocaleString()}
                                        </div>
                                        <div>
                                          <strong>Created By:</strong>{' '}
                                          <UserDisplayName userId={run.created_by} />
                                        </div>
                                      </div>
                                    </div>

                                    <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
                                      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                        Task Proposal
                                      </h4>
                                      <div className="text-sm text-gray-800 dark:text-gray-200">
                                        {(
                                          run.input_context as {
                                            proposal?: { name?: string; description?: string };
                                          }
                                        )?.proposal ? (
                                          <div className="space-y-2">
                                            <div>
                                              <strong className="text-gray-400">Name:</strong>{' '}
                                              <span className="text-cyan-400">
                                                {
                                                  (
                                                    run.input_context as {
                                                      proposal: { name?: string };
                                                    }
                                                  ).proposal.name
                                                }
                                              </span>
                                            </div>
                                            <div>
                                              <strong className="text-gray-400">
                                                Description:
                                              </strong>{' '}
                                              <span className="text-gray-300">
                                                {
                                                  (
                                                    run.input_context as {
                                                      proposal: { description?: string };
                                                    }
                                                  ).proposal.description
                                                }
                                              </span>
                                            </div>
                                          </div>
                                        ) : (
                                          <span className="text-gray-500">No proposal</span>
                                        )}
                                      </div>
                                    </div>

                                    <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
                                      <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                        Result
                                      </h4>
                                      <div className="text-sm text-gray-800 dark:text-gray-200">
                                        {run.result ? (
                                          <pre className="whitespace-pre-wrap wrap-break-word bg-gray-100 dark:bg-gray-700 p-2 rounded-sm text-xs max-h-32 overflow-y-auto">
                                            {JSON.stringify(run.result, null, 2)}
                                          </pre>
                                        ) : (
                                          <span className="text-gray-500">No result yet</span>
                                        )}
                                      </div>
                                    </div>

                                    {run.progress_messages && run.progress_messages.length > 0 && (
                                      <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600 md:col-span-2 lg:col-span-3">
                                        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                          Progress Messages ({run.progress_messages.length})
                                        </h4>
                                        <div className="text-sm text-gray-800 dark:text-gray-200">
                                          <pre className="whitespace-pre-wrap wrap-break-word bg-gray-100 dark:bg-gray-700 p-2 rounded-sm text-xs max-h-48 overflow-y-auto">
                                            {JSON.stringify(run.progress_messages, null, 2)}
                                          </pre>
                                        </div>
                                      </div>
                                    )}

                                    {/* Runbook Rendering with YAML Frontmatter */}
                                    {(run.input_context as { runbook?: string })?.runbook &&
                                      (() => {
                                        const runbookContent = (
                                          run.input_context as { runbook: string }
                                        ).runbook;
                                        // Parse YAML frontmatter (between --- markers)
                                        const frontmatterMatch =
                                          /^---\n([\s\S]*?)\n---\n([\s\S]*)$/.exec(runbookContent);
                                        const yamlContent = frontmatterMatch
                                          ? frontmatterMatch[1]
                                          : null;
                                        const markdownContent = frontmatterMatch
                                          ? frontmatterMatch[2]
                                          : runbookContent;

                                        // Parse YAML into key-value pairs
                                        const yamlData: Record<string, string | string[]> = {};
                                        if (yamlContent) {
                                          yamlContent.split('\n').forEach((line) => {
                                            const match = /^(\w+):\s*([^\n]*)/.exec(line);
                                            if (match) {
                                              const [, key, value] = match;
                                              // Handle array values like [T1190, T1059]
                                              if (value.startsWith('[') && value.endsWith(']')) {
                                                yamlData[key] = value
                                                  .slice(1, -1)
                                                  .split(',')
                                                  .map((v) => v.trim());
                                              } else {
                                                yamlData[key] = value;
                                              }
                                            }
                                          });
                                        }

                                        return (
                                          <div className="p-4 bg-gray-800 rounded-lg border border-gray-700 md:col-span-2 lg:col-span-3">
                                            <h4 className="text-lg font-medium text-gray-200 mb-4">
                                              Investigation Runbook
                                            </h4>

                                            {/* YAML Frontmatter as Metadata Card */}
                                            {yamlContent && Object.keys(yamlData).length > 0 && (
                                              <div className="mb-6 p-4 bg-gray-900 rounded-lg border border-gray-700">
                                                <h5 className="text-sm font-medium text-gray-400 mb-3 uppercase tracking-wide">
                                                  Runbook Metadata
                                                </h5>
                                                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                                                  {Object.entries(yamlData).map(([key, value]) => (
                                                    <div key={key} className="text-sm">
                                                      <span className="text-gray-500 block text-xs uppercase tracking-wide">
                                                        {key.replace(/_/g, ' ')}
                                                      </span>
                                                      {Array.isArray(value) ? (
                                                        <div className="flex flex-wrap gap-1 mt-1">
                                                          {value.map((v, i) => (
                                                            <span
                                                              key={i}
                                                              className="px-2 py-0.5 bg-gray-700 text-cyan-400 rounded-sm text-xs font-mono"
                                                            >
                                                              {v}
                                                            </span>
                                                          ))}
                                                        </div>
                                                      ) : (
                                                        <span className="text-gray-200 font-medium">
                                                          {value}
                                                        </span>
                                                      )}
                                                    </div>
                                                  ))}
                                                </div>
                                              </div>
                                            )}

                                            {/* Markdown Content */}
                                            <div className="prose prose-invert prose-sm max-w-none max-h-[500px] overflow-y-auto">
                                              <ReactMarkdown
                                                components={{
                                                  h1: ({ children }) => (
                                                    <h1 className="text-2xl font-bold mb-4 text-cyan-400 wrap-break-word border-b border-cyan-400/20 pb-2">
                                                      {children}
                                                    </h1>
                                                  ),
                                                  h2: ({ children }) => (
                                                    <h2 className="text-xl font-semibold mb-3 text-emerald-400 wrap-break-word">
                                                      {children}
                                                    </h2>
                                                  ),
                                                  h3: ({ children }) => (
                                                    <h3 className="text-lg font-medium mb-2 text-violet-400 wrap-break-word">
                                                      {children}
                                                    </h3>
                                                  ),
                                                  h4: ({ children }) => (
                                                    <h4 className="text-base font-medium mb-2 text-amber-400 wrap-break-word">
                                                      {children}
                                                    </h4>
                                                  ),
                                                  p: ({ children }) => (
                                                    <p className="mb-3 text-gray-300 leading-relaxed wrap-break-word">
                                                      {children}
                                                    </p>
                                                  ),
                                                  ul: ({ children }) => (
                                                    <ul className="list-disc list-inside mb-3 text-gray-300 space-y-1 ml-2">
                                                      {children}
                                                    </ul>
                                                  ),
                                                  ol: ({ children }) => (
                                                    <ol className="list-decimal list-inside mb-3 text-gray-300 space-y-1 ml-2">
                                                      {children}
                                                    </ol>
                                                  ),
                                                  li: ({ children }) => (
                                                    <li className="text-gray-300 wrap-break-word marker:text-primary">
                                                      {children}
                                                    </li>
                                                  ),
                                                  blockquote: ({ children }) => (
                                                    <blockquote className="border-l-4 border-primary pl-4 italic text-gray-400 mb-3 bg-gray-800/50 py-2 rounded-r">
                                                      {children}
                                                    </blockquote>
                                                  ),
                                                  code: ({ children, className }) => {
                                                    const isInline = !className;
                                                    return isInline ? (
                                                      <code className="bg-gray-900 px-2 py-0.5 rounded-sm text-sm font-mono text-emerald-400 break-all">
                                                        {children}
                                                      </code>
                                                    ) : (
                                                      <pre className="bg-gray-950 p-4 rounded-md overflow-x-auto mb-3 border border-gray-700">
                                                        <code className="text-gray-300 text-sm font-mono">
                                                          {children}
                                                        </code>
                                                      </pre>
                                                    );
                                                  },
                                                  pre: ({ children }) => (
                                                    <div className="bg-gray-950 p-4 rounded-md overflow-x-auto mb-3 border border-gray-700">
                                                      {children}
                                                    </div>
                                                  ),
                                                  strong: ({ children }) => (
                                                    <strong className="font-bold text-white">
                                                      {children}
                                                    </strong>
                                                  ),
                                                  em: ({ children }) => (
                                                    <em className="italic text-gray-200">
                                                      {children}
                                                    </em>
                                                  ),
                                                  a: ({ children, href }) => (
                                                    <a
                                                      href={href}
                                                      className="text-primary hover:text-primary-dark underline decoration-primary/50 underline-offset-2 transition-colors"
                                                      target="_blank"
                                                      rel="noopener noreferrer"
                                                    >
                                                      {children}
                                                    </a>
                                                  ),
                                                  hr: () => <hr className="my-6 border-gray-700" />,
                                                }}
                                              >
                                                {markdownContent}
                                              </ReactMarkdown>
                                            </div>
                                          </div>
                                        );
                                      })()}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* Pagination at bottom as well for convenience */}
            {!loading &&
              totalPages > 1 &&
              (executionType === 'tasks'
                ? taskRuns
                : executionType === 'workflows'
                  ? workflowRuns
                  : taskBuildingRuns
              ).length > 0 && (
                <div className="mt-2">
                  <Pagination
                    currentPage={currentPage}
                    totalPages={totalPages}
                    totalItems={total}
                    itemsPerPage={currentFilters.limit || 20}
                    onPageChange={handlePageChange}
                  />
                </div>
              )}
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default ExecutionHistory;
