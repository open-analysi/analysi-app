import React, { useState, useCallback, memo } from 'react';

import {
  ChevronDownIcon,
  ChevronRightIcon,
  ClockIcon,
  PencilSquareIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router';

import useErrorHandler from '../../hooks/useErrorHandler';
import { useUserDisplay } from '../../hooks/useUserDisplay';
import { backendApi } from '../../services/backendApi';
import type { TaskSchedule } from '../../services/tasksApi';
import { useTaskStore } from '../../store/taskStore';
import { componentStyles } from '../../styles/components';
import { Task } from '../../types/knowledge';
import { highlightText } from '../../utils/highlight';
import { ConfirmDialog } from '../common/ConfirmDialog';

// The generated Task type may not include all fields returned by the API detail endpoint
// (e.g. knowledge_units, knowledge_modules, usage_stats). Extend with extra fields.
type TaskWithExtras = Task & {
  knowledge_units?: { id: string; name: string; type: string }[];
  knowledge_modules?: { id: string; name: string }[];
  usage_stats?: { count: number; last_used: string | null };
};

interface TaskTableRowProps {
  task: TaskWithExtras;
  expanded: boolean;
  onToggleExpand: () => void;
  onDelete?: (taskId: string) => void;
}

const ScheduleDetails: React.FC<{
  taskSchedule: TaskSchedule | null;
  task: { schedule?: string | null; last_run_at?: string | null };
  formatDate: (d: string) => string;
}> = ({ taskSchedule, task, formatDate }) => {
  if (taskSchedule) {
    return (
      <div className="mt-1.5 grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="flex items-center gap-2">
          <ClockIcon className="h-3.5 w-3.5 text-blue-400 shrink-0" />
          <span className="text-sm text-gray-300">
            {taskSchedule.schedule_type === 'every'
              ? `Every ${taskSchedule.schedule_value}`
              : taskSchedule.schedule_value}
          </span>
        </div>
        <div>
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
              taskSchedule.enabled
                ? 'bg-green-900/40 text-green-300 border border-green-700/40'
                : 'bg-gray-700 text-gray-400 border border-gray-600'
            }`}
          >
            {taskSchedule.enabled ? 'Enabled' : 'Disabled'}
          </span>
        </div>
        {taskSchedule.next_run_at && (
          <div className="text-xs text-gray-400">
            <span className="text-gray-500">Next run:</span> {formatDate(taskSchedule.next_run_at)}
          </div>
        )}
        {taskSchedule.last_run_at && (
          <div className="text-xs text-gray-400">
            <span className="text-gray-500">Last run:</span> {formatDate(taskSchedule.last_run_at)}
          </div>
        )}
        {taskSchedule.timezone && taskSchedule.timezone !== 'UTC' && (
          <div className="text-xs text-gray-400">
            <span className="text-gray-500">Timezone:</span> {taskSchedule.timezone}
          </div>
        )}
        {taskSchedule.integration_id && (
          <div className="text-xs text-gray-400">
            <span className="text-gray-500">Integration:</span> {taskSchedule.integration_id}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 mt-1">
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-900/40 text-blue-300 border border-blue-700/40">
        <ClockIcon className="h-3.5 w-3.5" />
        {task.schedule || 'Managed by integration'}
      </span>
      {task.last_run_at && (
        <span className="text-xs text-gray-400">Last run: {formatDate(task.last_run_at)}</span>
      )}
    </div>
  );
};

const TaskTableRowComponent: React.FC<TaskTableRowProps> = ({
  task,
  expanded,
  onToggleExpand,
  onDelete,
}) => {
  const [detailedTask, setDetailedTask] = useState<TaskWithExtras | undefined>();
  const [taskSchedule, setTaskSchedule] = useState<TaskSchedule | null>(null);
  const [loading, setLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showCannotDeleteInfo, setShowCannotDeleteInfo] = useState(false);
  const [cannotDeleteMessage, setCannotDeleteMessage] = useState('');
  const [checkingDeletable, setCheckingDeletable] = useState(false);
  const { runSafe } = useErrorHandler('TaskTableRow');
  const navigate = useNavigate();

  // Get search term from store for highlighting
  const searchTerm = useTaskStore((state) => state.searchTerm);

  // Resolve user UUID to display name
  const createdByDisplay = useUserDisplay(task.created_by ?? undefined);

  // Fetch detailed information when row is expanded
  React.useEffect(() => {
    if (expanded && !detailedTask) {
      const fetchDetailedInfo = async () => {
        setLoading(true);
        try {
          // Fetch the detailed task data
          const [taskResult, taskError] = await runSafe(backendApi.getTask(task.id), 'fetchTask', {
            action: 'fetching task details',
            entityId: task.id,
          });

          if (taskResult) {
            setDetailedTask(taskResult);
          } else if (taskError) {
            // If we can't fetch task details, at least use the basic task data we have
            setDetailedTask(task);
          }

          // Fetch schedule details for scheduled tasks
          if (task.categories?.includes('scheduled')) {
            const [scheduleResult] = await runSafe(
              backendApi.getTaskSchedule(task.id),
              'fetchTaskSchedule',
              { action: 'fetching task schedule', entityId: task.id }
            );
            if (scheduleResult) {
              setTaskSchedule(scheduleResult);
            }
          }
        } finally {
          setLoading(false);
        }
      };

      void fetchDetailedInfo();
    }
  }, [expanded, task, detailedTask, runSafe]);

  const formatDate = useCallback((dateString: string) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
  }, []);

  // Open task in Workbench
  const openInWorkbench = useCallback(() => {
    // Get the first data sample as example input, or use empty object
    let inputData = '{}';
    if (task.data_samples && task.data_samples.length > 0) {
      try {
        inputData = JSON.stringify(task.data_samples[0], undefined, 2);
      } catch {
        inputData = '{}';
      }
    }

    // Navigate to Workbench with task information
    void navigate('/workbench', {
      state: {
        taskId: task.id,
        inputData: inputData,
        taskName: task.name,
      },
    });
  }, [task, navigate]);

  const getFunctionColor = useCallback((func: string) => {
    switch (func) {
      case 'summarization': {
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300';
      }
      case 'data_conversion': {
        return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300';
      }
      case 'extraction': {
        return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300';
      }
      case 'decision_making': {
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300';
      }
      case 'planning': {
        return 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-300';
      }
      case 'visualization': {
        return 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-300';
      }
      case 'search': {
        return 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300';
      }
      default: {
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300';
      }
    }
  }, []);

  const getScopeColor = useCallback((scope: string) => {
    switch (scope) {
      case 'input': {
        return 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-300';
      }
      case 'processing': {
        return 'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-300';
      }
      case 'output': {
        return 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300';
      }
      default: {
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300';
      }
    }
  }, []);

  const getStatusColor = useCallback((status: string) => {
    switch (status) {
      case 'enabled': {
        return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300';
      }
      case 'disabled': {
        return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300';
      }
      case 'active': {
        return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300';
      }
      case 'deprecated': {
        return 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300';
      }
      case 'experimental': {
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300';
      }
      default: {
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300';
      }
    }
  }, []);

  const getKnowledgeUnitColor = useCallback((type: string) => {
    switch (type) {
      case 'directive': {
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300';
      }
      case 'table': {
        return 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300';
      }
      case 'tool': {
        return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300';
      }
      default: {
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300';
      }
    }
  }, []);

  const handleDeleteClick = useCallback(async () => {
    setCheckingDeletable(true);
    try {
      const [result] = await runSafe(backendApi.checkTaskDeletable(task.id), 'checkTaskDeletable', {
        action: 'checking if task can be deleted',
        entityId: task.id,
      });

      if (result) {
        if (result.can_delete) {
          setShowDeleteConfirm(true);
        } else {
          setCannotDeleteMessage(result.message || 'This task cannot be deleted.');
          setShowCannotDeleteInfo(true);
        }
      } else {
        // API call failed — still show the delete confirmation so the user isn't stuck
        setShowDeleteConfirm(true);
      }
    } finally {
      setCheckingDeletable(false);
    }
  }, [task.id, runSafe]);

  const handleConfirmDelete = useCallback(() => {
    setShowDeleteConfirm(false);
    onDelete?.(task.id);
  }, [onDelete, task.id]);

  return (
    <>
      <tr
        className={`${componentStyles.tableRow} cursor-pointer`}
        onClick={onToggleExpand}
        data-testid={`task-row-${task.id}`}
      >
        <td className={`${componentStyles.tableCell}`}>
          <div className="flex items-start">
            <span
              className="mr-2 mt-1 text-gray-500 shrink-0"
              aria-label={expanded ? 'Collapse row' : 'Expand row'}
            >
              {expanded ? (
                <ChevronDownIcon className="h-4 w-4" />
              ) : (
                <ChevronRightIcon className="h-4 w-4" />
              )}
            </span>
            <div className="wrap-break-word min-w-0">
              {highlightText(task.name, searchTerm)}
              {task.categories?.includes('scheduled') && (
                <ClockIcon
                  className="h-3.5 w-3.5 inline-block ml-1.5 text-blue-400 shrink-0"
                  aria-label="Scheduled task"
                />
              )}
            </div>
          </div>
        </td>
        <td className={componentStyles.tableCell}>
          <div className="wrap-break-word line-clamp-2">
            {highlightText(task.description ?? '', searchTerm)}
          </div>
          {task.categories && task.categories.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {task.categories.slice(0, 3).map((cat) => (
                <span
                  key={cat}
                  className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] leading-tight bg-dark-600 text-gray-300 border border-gray-600/50"
                >
                  {cat}
                </span>
              ))}
              {task.categories.length > 3 && (
                <span className="text-[11px] text-gray-500">+{task.categories.length - 3}</span>
              )}
            </div>
          )}
        </td>
        <td className={componentStyles.tableCell}>
          <span
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getFunctionColor(task.function ?? '')}`}
          >
            {highlightText(task.function ?? '', searchTerm)}
          </span>
        </td>
        <td className={componentStyles.tableCell}>
          {task.scope ? (
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getScopeColor(task.scope ?? '')}`}
            >
              {highlightText(task.scope ?? '', searchTerm)}
            </span>
          ) : (
            'N/A'
          )}
        </td>
        <td className={componentStyles.tableCell}>{createdByDisplay}</td>
        <td className={componentStyles.tableCell}>
          <span
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(task.status)}`}
          >
            {highlightText(task.status, searchTerm)}
          </span>
        </td>
        <td className={componentStyles.tableCell}>{highlightText(task.version, searchTerm)}</td>
        <td className={componentStyles.tableCell}>{formatDate(task.created_at)}</td>
        <td className={componentStyles.tableCell}>
          <div className="flex items-center space-x-1">
            <button
              onClick={(e) => {
                e.stopPropagation();
                openInWorkbench();
              }}
              className="p-1.5 rounded-sm hover:bg-pink-100 dark:hover:bg-pink-900/30 transition-colors"
              title="Open in Workbench"
            >
              <PencilSquareIcon className="h-4 w-4 text-pink-500" />
            </button>
            {onDelete && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  void handleDeleteClick();
                }}
                disabled={checkingDeletable}
                className="p-1.5 rounded-sm hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors disabled:opacity-50"
                title="Delete Task"
              >
                {checkingDeletable ? (
                  <div className="h-4 w-4 border-2 border-red-500 border-t-transparent rounded-full animate-spin" />
                ) : (
                  <TrashIcon className="h-4 w-4 text-red-500" />
                )}
              </button>
            )}
          </div>
        </td>
      </tr>

      {expanded && (
        <tr>
          <td colSpan={9} className="bg-dark-700 px-6 py-4 border-t border-b border-gray-700/50">
            {loading ? (
              <div className="flex justify-center py-6" role="status" aria-label="Loading">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
              </div>
            ) : (
              <div>
                <div className="mb-3">
                  <h3 className="text-sm font-semibold mb-1 text-gray-100">
                    {highlightText(task.name, searchTerm)}
                  </h3>
                  <p className="text-sm text-gray-400">
                    {highlightText(task.description ?? '', searchTerm)}
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm text-gray-300">
                  <div>
                    <p className="mb-1">
                      <span className="font-medium text-gray-100">ID:</span>{' '}
                      <span className="font-mono text-xs text-gray-400">{task.id || 'N/A'}</span>
                    </p>
                    <p className="mb-1">
                      <span className="font-medium text-gray-100">Function:</span>{' '}
                      {highlightText(task.function ?? 'N/A', searchTerm)}
                    </p>
                    <p className="mb-1">
                      <span className="font-medium text-gray-100">Created by:</span>{' '}
                      {createdByDisplay}
                    </p>
                  </div>
                  <div>
                    <p className="mb-1">
                      <span className="font-medium text-gray-100">Status:</span>{' '}
                      {highlightText(task.status || 'N/A', searchTerm)}
                    </p>
                    <p className="mb-1">
                      <span className="font-medium text-gray-100">Version:</span>{' '}
                      {highlightText(task.version || 'N/A', searchTerm)}
                    </p>
                    <p className="mb-1">
                      <span className="font-medium text-gray-100">Created:</span>{' '}
                      {formatDate(task.created_at || '')}
                    </p>
                    <p className="mb-1">
                      <span className="font-medium text-gray-100">Updated:</span>{' '}
                      {formatDate(task.updated_at || '')}
                    </p>
                  </div>
                </div>

                {/* Schedule */}
                {task.categories?.includes('scheduled') && (
                  <div className="mt-3 pt-3 border-t border-gray-700/50">
                    <span className="font-medium text-gray-100 text-sm">Schedule:</span>
                    <ScheduleDetails
                      taskSchedule={taskSchedule}
                      task={task}
                      formatDate={formatDate}
                    />
                  </div>
                )}

                {/* Categories */}
                {task.categories && task.categories.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-gray-700/50">
                    <span className="font-medium text-gray-100 text-sm">Categories:</span>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {task.categories.map((cat) => (
                        <span
                          key={cat}
                          className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-dark-600 text-gray-300 border border-gray-700/50"
                        >
                          {highlightText(cat, searchTerm)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Knowledge Units used by this Task */}
                {task.knowledge_units &&
                  Array.isArray(task.knowledge_units) &&
                  task.knowledge_units.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-700/50">
                      <span className="font-medium text-gray-100 text-sm">Knowledge Units:</span>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {task.knowledge_units.map((ku) => (
                          <span
                            key={ku.id}
                            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getKnowledgeUnitColor(ku.type)}`}
                          >
                            {highlightText(ku.name, searchTerm)} (
                            {highlightText(ku.type, searchTerm)})
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                {/* Knowledge Modules used by this Task */}
                {task.knowledge_modules &&
                  Array.isArray(task.knowledge_modules) &&
                  task.knowledge_modules.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-700/50">
                      <span className="font-medium text-gray-100 text-sm">Knowledge Modules:</span>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {task.knowledge_modules.map((km) => (
                          <span
                            key={km.id}
                            className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-dark-600 text-gray-300 border border-gray-700/50"
                          >
                            {highlightText(km.name, searchTerm)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                {/* Execution Runs section awaits backend endpoint implementation */}

                {task.usage_stats && (
                  <div className="mt-3 pt-3 border-t border-gray-700/50">
                    <span className="font-medium text-gray-100 text-sm">Usage Statistics:</span>
                    <p className="text-sm text-gray-300 mt-1">
                      <span className="font-medium text-gray-100">Count:</span>{' '}
                      {task.usage_stats?.count || 0}
                    </p>
                    {task.usage_stats?.last_used && (
                      <p className="text-sm text-gray-300">
                        <span className="font-medium text-gray-100">Last Used:</span>{' '}
                        {formatDate(task.usage_stats.last_used)}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </td>
        </tr>
      )}

      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleConfirmDelete}
        title="Delete Task?"
        message={`Are you sure you want to delete "${task.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="warning"
      />

      <ConfirmDialog
        isOpen={showCannotDeleteInfo}
        onClose={() => setShowCannotDeleteInfo(false)}
        onConfirm={() => setShowCannotDeleteInfo(false)}
        title="Cannot Delete Task"
        message={cannotDeleteMessage}
        confirmLabel="OK"
        cancelLabel=""
        variant="info"
      />
    </>
  );
};

// Memoize the component to prevent unnecessary re-renders
export const TaskTableRow = memo(TaskTableRowComponent);
