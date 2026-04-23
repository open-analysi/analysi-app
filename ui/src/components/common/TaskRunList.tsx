/* eslint-disable @typescript-eslint/no-floating-promises */
import React, { useState, useCallback, useMemo, useEffect } from 'react';

import { BeakerIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { Link, useNavigate } from 'react-router';

import { backendApi } from '../../services/backendApi';
import { componentStyles } from '../../styles/components';
import { TaskRun } from '../../types/taskRun';
import { WorkflowRun } from '../../types/workflow';
import { formatDuration, formatBytes, getDurationColorClass } from '../../utils/formatUtils';

import { Pagination } from './Pagination';

interface AlertInfo {
  alert_id: string;
  human_readable_id?: string;
  title?: string;
}

// Fetches and renders workflow run + workflow + alert links for a task run detail panel.
const WorkflowRunInfo: React.FC<{ workflowRunId: string; alertId?: string }> = ({
  workflowRunId,
  alertId,
}) => {
  const [workflowRun, setWorkflowRun] = useState<WorkflowRun | null>(null);
  const [alert, setAlert] = useState<AlertInfo | null>(null);

  useEffect(() => {
    let cancelled = false;

    backendApi
      .getWorkflowRun(workflowRunId)
      .then((run) => {
        if (!cancelled) setWorkflowRun(run);
      })
      .catch(() => {
        /* silently ignore — not critical */
      });

    // If alertId is provided directly, fetch alert details using that
    if (alertId) {
      backendApi
        .getAlert(alertId)
        .then((a) => {
          if (!cancelled && a?.alert_id) {
            setAlert({
              alert_id: a.alert_id,
              human_readable_id: a.human_readable_id,
              title: a.title,
            });
          }
        })
        .catch(() => {
          /* silently ignore — not critical */
        });
    }

    return () => {
      cancelled = true;
    };
  }, [workflowRunId, alertId]);

  return (
    <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-600 space-y-1">
      <div className="font-medium text-gray-900 dark:text-gray-100 mb-1">Source</div>
      <div>
        Workflow Run:{' '}
        <Link
          to={`/workflow-runs/${workflowRunId}`}
          className="text-primary hover:underline font-mono text-xs"
        >
          {workflowRunId.slice(0, 8)}…
        </Link>
      </div>
      {workflowRun && (
        <div>
          Workflow:{' '}
          <Link
            to={`/workflows/${workflowRun.workflow_id}`}
            className="text-primary hover:underline"
          >
            {workflowRun.workflow_name ?? workflowRun.workflow_id}
          </Link>
        </div>
      )}
      {alert && (
        <div>
          Alert:{' '}
          <Link to={`/alerts/${alert.alert_id}`} className="text-primary hover:underline">
            {alert.human_readable_id ?? alert.alert_id.slice(0, 8)}
          </Link>
        </div>
      )}
    </div>
  );
};

const ITEMS_PER_PAGE = 10;

// Small helper to render LLM cost as a formatted string (or dash)
const formatLlmCost = (usage: TaskRun['llm_usage']): string =>
  usage?.cost_usd != null ? `$${usage.cost_usd.toFixed(4)}` : '-';

// Small helper to render LLM usage breakdown in expanded rows
const LlmUsageDetails: React.FC<{ usage: TaskRun['llm_usage'] }> = ({ usage }) => {
  if (!usage) return null;
  return (
    <div className="mt-2 pt-2 border-t border-gray-200 dark:border-gray-600">
      <div className="font-medium text-gray-900 dark:text-gray-100 mb-1">LLM Usage</div>
      {usage.cost_usd != null && (
        <div>
          Cost:{' '}
          <span className="text-emerald-600 dark:text-emerald-400 font-semibold">
            ${usage.cost_usd.toFixed(4)}
          </span>
        </div>
      )}
      <div>Tokens in: {usage.input_tokens.toLocaleString()}</div>
      <div>Tokens out: {usage.output_tokens.toLocaleString()}</div>
      <div>Total tokens: {usage.total_tokens.toLocaleString()}</div>
    </div>
  );
};

interface TaskRunListProps {
  taskRuns: TaskRun[];
  loading?: boolean;
  showWorkflowRunId?: boolean;
  className?: string;
  /** When true, hides internal pagination (use when parent handles pagination) */
  hidePagination?: boolean;
}

export const TaskRunList: React.FC<TaskRunListProps> = ({
  taskRuns,
  loading = false,
  showWorkflowRunId = false,
  className = '',
  hidePagination = false,
}) => {
  const navigate = useNavigate();
  const [expandedTaskRun, setExpandedTaskRun] = useState<string | undefined>();
  const [currentPage, setCurrentPage] = useState(1);
  // Tracks task IDs confirmed as deleted (404) so we can show a badge and hide "Open in Workbench"
  const [deletedTaskIds, setDeletedTaskIds] = useState<Set<string>>(new Set());

  // Calculate pagination
  const totalItems = taskRuns.length;
  const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);

  // Get paginated items
  const paginatedTaskRuns = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const endIndex = startIndex + ITEMS_PER_PAGE;
    return taskRuns.slice(startIndex, endIndex);
  }, [taskRuns, currentPage]);

  // Reset to page 1 when task runs change
  React.useEffect(() => {
    setCurrentPage(1);
  }, [taskRuns.length]);

  // Resolve the effective task_id: top-level field, or fallback to execution_context
  const getEffectiveTaskId = useCallback((taskRun: TaskRun): string | undefined => {
    if (taskRun.task_id) return taskRun.task_id;
    // Workflow-spawned tasks store the real task_id inside execution_context
    const ctxTaskId = (taskRun.execution_context as Record<string, unknown> | undefined)?.task_id;
    return typeof ctxTaskId === 'string' ? ctxTaskId : undefined;
  }, []);

  // Whether this task run can be opened in Workbench
  const canOpenInWorkbench = useCallback(
    (taskRun: TaskRun): boolean => {
      const effectiveId = getEffectiveTaskId(taskRun);
      // If the only task reference points to a deleted task, hide the button
      if (effectiveId && deletedTaskIds.has(effectiveId) && !taskRun.cy_script) return false;
      return !!effectiveId || !!taskRun.cy_script;
    },
    [getEffectiveTaskId, deletedTaskIds]
  );

  // Whether this task run's referenced task has been deleted
  const isTaskDeleted = useCallback(
    (taskRun: TaskRun): boolean => {
      const effectiveId = getEffectiveTaskId(taskRun);
      return !!effectiveId && deletedTaskIds.has(effectiveId);
    },
    [getEffectiveTaskId, deletedTaskIds]
  );

  // Check if the referenced task still exists when details are expanded
  useEffect(() => {
    if (!expandedTaskRun) return;
    const taskRun = taskRuns.find((tr) => tr.id === expandedTaskRun);
    if (!taskRun) return;
    const effectiveId = getEffectiveTaskId(taskRun);
    if (!effectiveId || deletedTaskIds.has(effectiveId)) return;

    let cancelled = false;
    backendApi.getTask(effectiveId).catch((err: { response?: { status?: number } }) => {
      if (!cancelled && err?.response?.status === 404) {
        setDeletedTaskIds((prev) => new Set(prev).add(effectiveId));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [expandedTaskRun, taskRuns, getEffectiveTaskId, deletedTaskIds]);

  // Open task in Workbench with the same input
  const openInWorkbench = useCallback(
    (taskRun: TaskRun) => {
      // Parse the input data from the task run
      let inputData = '';
      try {
        if (taskRun.input_location || taskRun.input) {
          // Parse the input and stringify it nicely for the workbench
          const inputStr = taskRun.input_location || taskRun.input;
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
          const parsed = typeof inputStr === 'string' ? JSON.parse(inputStr) : inputStr;
          // Extract the actual input data if it's wrapped
          // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment, @typescript-eslint/no-unsafe-member-access
          const actualInput = parsed.input || parsed;
          inputData = JSON.stringify(actualInput, undefined, 2);
        }
      } catch {
        // If parsing fails, use the raw input
        inputData = taskRun.input_location || taskRun.input || '{}';
      }

      const effectiveTaskId = getEffectiveTaskId(taskRun);

      // Navigate to Workbench page with taskId/taskRunId in URL query params
      // Large data (inputData, cyScript) stays in navigation state
      const params = new URLSearchParams();
      if (effectiveTaskId) params.set('taskId', effectiveTaskId);
      params.set('taskRunId', taskRun.id);

      navigate(`/workbench?${params.toString()}`, {
        state: {
          inputData: inputData,
          cyScript: taskRun.cy_script,
          isAdHoc: !!taskRun.cy_script && !effectiveTaskId,
        },
      });
    },
    [navigate, getEffectiveTaskId]
  );

  const getStatusBadge = useCallback((status: TaskRun['status']) => {
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
  }, []);

  const getStatusIcon = useCallback((status: TaskRun['status']) => {
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
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <ArrowPathIcon className="h-8 w-8 animate-spin text-gray-400" />
        <span className="ml-2 text-gray-400">Loading task runs...</span>
      </div>
    );
  }

  if (taskRuns.length === 0) {
    return (
      <div className="text-center text-gray-400 py-8">
        <p>No task runs found</p>
      </div>
    );
  }

  // When hidePagination is true, show all items instead of paginating
  const displayedTaskRuns = hidePagination ? taskRuns : paginatedTaskRuns;
  const expandedColSpan = showWorkflowRunId ? 10 : 9;

  return (
    <div className={className}>
      {/* Top Pagination */}
      {!hidePagination && totalItems > 0 && (
        <div className="mb-2">
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={totalItems}
            itemsPerPage={ITEMS_PER_PAGE}
            onPageChange={setCurrentPage}
          />
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead className={componentStyles.tableHeader}>
            <tr>
              <th className={componentStyles.tableHeaderCell}>Task Name</th>
              <th className={componentStyles.tableHeaderCell}>Status</th>
              <th className={componentStyles.tableHeaderCell}>Start Time</th>
              <th className={componentStyles.tableHeaderCell}>Duration</th>
              <th className={componentStyles.tableHeaderCell}>Input Size</th>
              <th className={componentStyles.tableHeaderCell}>Output Size</th>
              <th className={componentStyles.tableHeaderCell}>LLM Cost</th>
              {showWorkflowRunId && (
                <th className={componentStyles.tableHeaderCell}>Workflow Run</th>
              )}
              <th className={componentStyles.tableHeaderCell}>Actions</th>
            </tr>
          </thead>
          <tbody className={componentStyles.tableBody}>
            {displayedTaskRuns.map((taskRun) => (
              <React.Fragment key={taskRun.id}>
                <tr className={componentStyles.tableRow}>
                  <td className={`${componentStyles.tableCell} font-medium`}>
                    <button
                      onClick={() =>
                        setExpandedTaskRun(expandedTaskRun === taskRun.id ? undefined : taskRun.id)
                      }
                      className="text-left hover:text-primary"
                    >
                      {taskRun.task_name || taskRun.task_id || 'Unnamed Task'}
                    </button>
                  </td>
                  <td className={componentStyles.tableCell}>
                    <span className={getStatusBadge(taskRun.status)}>
                      {getStatusIcon(taskRun.status)} {taskRun.status}
                    </span>
                  </td>
                  <td className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}>
                    {taskRun.started_at ? new Date(taskRun.started_at).toLocaleString() : '-'}
                  </td>
                  <td className={`${componentStyles.tableCell}`}>
                    {taskRun.duration ? (
                      <span className={`font-medium ${getDurationColorClass(taskRun.duration)}`}>
                        {formatDuration(taskRun.duration)}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}>
                    {taskRun.input_location
                      ? formatBytes(new TextEncoder().encode(taskRun.input_location).length)
                      : '-'}
                  </td>
                  <td className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}>
                    {taskRun.output_location
                      ? formatBytes(new TextEncoder().encode(taskRun.output_location).length)
                      : '-'}
                  </td>
                  <td className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}>
                    <span className="text-emerald-600 dark:text-emerald-400 font-medium">
                      {formatLlmCost(taskRun.llm_usage)}
                    </span>
                  </td>
                  {showWorkflowRunId && (
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400 font-mono">
                      {taskRun.workflow_run_id ? taskRun.workflow_run_id.slice(0, 8) : '-'}
                    </td>
                  )}
                  <td className={`${componentStyles.tableCell} text-gray-600 dark:text-gray-400`}>
                    <button
                      onClick={() =>
                        setExpandedTaskRun(expandedTaskRun === taskRun.id ? undefined : taskRun.id)
                      }
                      className="text-primary hover:text-primary/80 font-medium"
                    >
                      {taskRun.status === 'running' ? 'Live Status' : 'View Details'}
                    </button>
                  </td>
                </tr>
                {expandedTaskRun === taskRun.id && (
                  <tr>
                    <td
                      colSpan={expandedColSpan}
                      className="px-6 py-4 bg-gray-50 dark:bg-gray-700 border-t"
                    >
                      <div className="space-y-4">
                        <div className="flex justify-between items-center">
                          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                            Task Run Details - TRID: {taskRun.id}
                          </h3>
                          <div className="flex items-center gap-2">
                            {canOpenInWorkbench(taskRun) && (
                              <button
                                onClick={() => openInWorkbench(taskRun)}
                                className="inline-flex items-center gap-1 px-3 py-1.5 bg-primary text-white text-sm font-medium rounded-sm hover:bg-primary/90 transition-colors"
                                title={
                                  taskRun.cy_script
                                    ? 'Open Ad Hoc script in Workbench'
                                    : 'Open this task in Workbench with the same input'
                                }
                              >
                                <BeakerIcon className="h-4 w-4" />
                                Open in Workbench
                              </button>
                            )}
                            <button
                              onClick={() => setExpandedTaskRun(undefined)}
                              className="text-gray-400 hover:text-gray-600"
                            >
                              ❌
                            </button>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div className="bg-white dark:bg-gray-800 p-4 rounded-sm border">
                            <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-2">
                              Basic Info
                            </h4>
                            <div className="text-sm space-y-1 text-gray-700 dark:text-gray-300">
                              <div className="flex items-center gap-2">
                                <span>
                                  Task: {taskRun.task_name || taskRun.task_id || 'Unnamed Task'}
                                </span>
                                {isTaskDeleted(taskRun) && (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-red-900/30 text-red-400 border border-red-700/50">
                                    Task deleted
                                  </span>
                                )}
                              </div>
                              <div>
                                Status: {getStatusIcon(taskRun.status)} {taskRun.status}
                              </div>
                              <div>TRID: {taskRun.id}</div>
                              <LlmUsageDetails usage={taskRun.llm_usage} />
                              {taskRun.workflow_run_id && (
                                <WorkflowRunInfo
                                  workflowRunId={taskRun.workflow_run_id}
                                  alertId={(() => {
                                    try {
                                      const input = taskRun.input_location || taskRun.input;
                                      if (!input) return undefined;
                                      const parsed = (
                                        typeof input === 'string' ? JSON.parse(input) : input
                                      ) as { alert_id?: string } | undefined;
                                      return parsed?.alert_id;
                                    } catch {
                                      return undefined;
                                    }
                                  })()}
                                />
                              )}
                            </div>
                          </div>

                          <div className="bg-white dark:bg-gray-800 p-4 rounded-sm border">
                            <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-2">
                              Timing
                            </h4>
                            <div className="text-sm space-y-1 text-gray-700 dark:text-gray-300">
                              <div>
                                Started:{' '}
                                {taskRun.started_at
                                  ? new Date(taskRun.started_at).toLocaleString()
                                  : 'N/A'}
                              </div>
                              {taskRun.completed_at && (
                                <div>Ended: {new Date(taskRun.completed_at).toLocaleString()}</div>
                              )}
                              <div>
                                Duration:{' '}
                                {taskRun.duration ? formatDuration(taskRun.duration) : 'N/A'}
                              </div>
                            </div>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div className="bg-white dark:bg-gray-800 p-4 rounded-sm border">
                            <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-2">
                              Input Data (
                              {taskRun.input_location
                                ? formatBytes(
                                    new TextEncoder().encode(taskRun.input_location).length
                                  )
                                : 'N/A'}
                              )
                            </h4>
                            <pre className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 p-2 rounded-sm max-h-32 overflow-auto">
                              {taskRun.input_location
                                ? (() => {
                                    try {
                                      const input = taskRun.input_location || taskRun.input;
                                      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                                      const parsed =
                                        typeof input === 'string' ? JSON.parse(input) : input;
                                      return JSON.stringify(parsed, undefined, 2);
                                    } catch {
                                      return taskRun.input_location || 'No input data';
                                    }
                                  })()
                                : 'No input data available'}
                            </pre>
                          </div>

                          <div className="bg-white dark:bg-gray-800 p-4 rounded-sm border">
                            <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-2">
                              Output Data (
                              {taskRun.output_location
                                ? formatBytes(
                                    new TextEncoder().encode(taskRun.output_location).length
                                  )
                                : 'N/A'}
                              )
                            </h4>
                            {taskRun.output_location ? (
                              <pre className="text-xs bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 p-2 rounded-sm max-h-32 overflow-auto">
                                {(() => {
                                  try {
                                    const output = taskRun.output_location || taskRun.output;
                                    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                                    const parsed =
                                      typeof output === 'string' ? JSON.parse(output) : output;
                                    return JSON.stringify(parsed, undefined, 2);
                                  } catch {
                                    return taskRun.output_location || 'No output data';
                                  }
                                })()}
                              </pre>
                            ) : (
                              <div className="text-xs text-gray-500 p-2">
                                No output data available
                              </div>
                            )}
                          </div>
                        </div>

                        {taskRun.error && (
                          <div className="bg-white dark:bg-gray-800 p-4 rounded-sm border">
                            <h4 className="font-medium text-red-600 dark:text-red-400 mb-2">
                              Error
                            </h4>
                            <pre className="text-xs bg-red-50 dark:bg-red-950 text-red-800 dark:text-red-300 p-2 rounded-sm overflow-auto">
                              {taskRun.error}
                            </pre>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* Bottom Pagination */}
      {!hidePagination && totalItems > ITEMS_PER_PAGE && (
        <div className="mt-2">
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={totalItems}
            itemsPerPage={ITEMS_PER_PAGE}
            onPageChange={setCurrentPage}
          />
        </div>
      )}
    </div>
  );
};
