import React, { useState, useEffect, useRef } from 'react';

import {
  Combobox,
  ComboboxInput,
  ComboboxButton,
  ComboboxOptions,
  ComboboxOption,
} from '@headlessui/react';
import {
  ChevronUpDownIcon,
  CheckIcon,
  MagnifyingGlassIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { Task } from '../../types/knowledge';

const RECENT_TASKS_KEY = 'workbench_recent_tasks';
const MAX_RECENT_TASKS = 5;

// Helper to get recent task IDs from localStorage
const getRecentTaskIds = (): string[] => {
  try {
    const stored = localStorage.getItem(RECENT_TASKS_KEY);
    return stored ? (JSON.parse(stored) as string[]) : [];
  } catch {
    return [];
  }
};

// Helper to add a task ID to recent tasks
const addToRecentTasks = (taskId: string): void => {
  try {
    const recent = getRecentTaskIds().filter((id) => id !== taskId);
    recent.unshift(taskId);
    localStorage.setItem(RECENT_TASKS_KEY, JSON.stringify(recent.slice(0, MAX_RECENT_TASKS)));
  } catch {
    // Ignore localStorage errors
  }
};

interface TaskSelectorProps {
  selectedTask: Task | null;
  onTaskChange: (taskId: string) => void;
  disabled?: boolean;
  isAdHocMode: boolean;
}

export const TaskSelector: React.FC<TaskSelectorProps> = ({
  selectedTask,
  onTaskChange,
  disabled = false,
  isAdHocMode,
}) => {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [recentTaskIds, setRecentTaskIds] = useState<string[]>(() => getRecentTaskIds());
  const isLoadingRef = useRef(false);
  const hasMoreRef = useRef(true);
  const { runSafe } = useErrorHandler('TaskSelector');

  // Handle task selection - track in recent tasks
  const handleTaskChange = (taskId: string | null) => {
    if (!taskId) return;
    if (taskId !== '__adhoc__') {
      addToRecentTasks(taskId);
      setRecentTaskIds(getRecentTaskIds());
    }
    onTaskChange(taskId);
  };

  // Initial load - load ALL tasks at once since there are only ~23 total
  useEffect(() => {
    const loadAllTasks = async () => {
      setIsLoading(true);
      isLoadingRef.current = true;

      const [result] = await runSafe(
        backendApi.getTasks({
          limit: 100, // Load up to 100 tasks at once (more than we need)
          offset: 0,
          search: searchQuery || undefined,
        }),
        'loadAllTasks',
        { action: 'loading all tasks for selector', params: { search: searchQuery } }
      );

      if (result) {
        const tasksList = result.tasks || result;
        const allTasks = Array.isArray(tasksList) ? tasksList : [];
        // Sort alphabetically using toSorted for immutability
        const sortedTasks = [...allTasks].sort((a, b) => a.name.localeCompare(b.name));
        setTasks(sortedTasks);
        // No more tasks to load since we loaded them all
        setHasMore(false);
        hasMoreRef.current = false;
      }

      setIsLoading(false);
      isLoadingRef.current = false;
    };

    void loadAllTasks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery]);

  const displayValue = isAdHocMode ? '' : selectedTask?.name || '';

  // Client-side filtering based on search query
  const filteredTasks = searchQuery
    ? tasks.filter(
        (task) =>
          task.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          task.description?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : tasks;

  // Get recent tasks (only when not searching)
  const recentTasks = !searchQuery
    ? recentTaskIds
        .map((id) => tasks.find((t) => t.id === id))
        .filter((t): t is Task => t !== undefined)
    : [];

  // Filter out recent tasks from the main list to avoid duplicates
  const nonRecentTasks = !searchQuery
    ? filteredTasks.filter((t) => !recentTaskIds.includes(t.id))
    : filteredTasks;

  return (
    <Combobox
      value={isAdHocMode ? '__adhoc__' : selectedTask?.id || ''}
      onChange={handleTaskChange}
      disabled={disabled}
    >
      <div className="relative">
        <div className="relative">
          <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
            <MagnifyingGlassIcon className="h-4 w-4 text-gray-400" aria-hidden="true" />
          </div>
          <ComboboxInput
            className="min-w-64 w-full pl-9 pr-10 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
            displayValue={() => displayValue}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search tasks..."
            autoComplete="off"
          />
          <ComboboxButton className="absolute inset-y-0 right-0 flex items-center pr-2">
            <ChevronUpDownIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
          </ComboboxButton>
        </div>

        <ComboboxOptions className="absolute z-10 mt-1 max-h-96 min-w-full w-max max-w-2xl overflow-auto rounded-md bg-white dark:bg-gray-700 py-1 text-sm shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-hidden">
          {/* Recent tasks section */}
          {recentTasks.length > 0 && (
            <>
              <div className="px-3 py-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider flex items-center gap-1.5">
                <ClockIcon className="h-3.5 w-3.5" />
                Recent
              </div>
              {recentTasks.map((task) => (
                <ComboboxOption
                  key={`recent-${task.id}`}
                  value={task.id}
                  className={({ focus }) =>
                    `relative cursor-pointer select-none py-2 pl-10 pr-4 ${
                      focus ? 'bg-blue-600 text-white' : 'text-gray-900 dark:text-gray-100'
                    }`
                  }
                >
                  {({ selected, focus }) => (
                    <>
                      <span
                        className={`block truncate ${selected ? 'font-medium' : 'font-normal'}`}
                      >
                        {task.name}
                      </span>
                      {selected && (
                        <span
                          className={`absolute inset-y-0 left-0 flex items-center pl-3 ${
                            focus ? 'text-white' : 'text-blue-600'
                          }`}
                        >
                          <CheckIcon className="h-5 w-5" aria-hidden="true" />
                        </span>
                      )}
                    </>
                  )}
                </ComboboxOption>
              ))}
              {/* Divider between recent and all tasks */}
              {nonRecentTasks.length > 0 && (
                <div className="border-t border-gray-200 dark:border-gray-600 my-1" />
              )}
            </>
          )}

          {/* All tasks section header (only show when we have recent tasks) */}
          {recentTasks.length > 0 && nonRecentTasks.length > 0 && (
            <div className="px-3 py-1.5 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              All Tasks
            </div>
          )}

          {/* Task options */}
          {filteredTasks.length === 0 && !isLoading ? (
            <div className="relative cursor-default select-none py-2 px-4 text-gray-700 dark:text-gray-300">
              {searchQuery ? 'No tasks found.' : 'No tasks available.'}
            </div>
          ) : (
            nonRecentTasks.map((task) => (
              <ComboboxOption
                key={task.id}
                value={task.id}
                className={({ focus }) =>
                  `relative cursor-pointer select-none py-2 pl-10 pr-4 ${
                    focus ? 'bg-blue-600 text-white' : 'text-gray-900 dark:text-gray-100'
                  }`
                }
              >
                {({ selected, focus }) => (
                  <>
                    <span className={`block truncate ${selected ? 'font-medium' : 'font-normal'}`}>
                      {task.name}
                    </span>
                    {selected && (
                      <span
                        className={`absolute inset-y-0 left-0 flex items-center pl-3 ${
                          focus ? 'text-white' : 'text-blue-600'
                        }`}
                      >
                        <CheckIcon className="h-5 w-5" aria-hidden="true" />
                      </span>
                    )}
                  </>
                )}
              </ComboboxOption>
            ))
          )}

          {/* Loading indicator */}
          {isLoading && (
            <div className="relative cursor-default select-none py-2 px-4 text-gray-700 dark:text-gray-300 flex items-center justify-center">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500" />
              <span className="ml-2">Loading tasks...</span>
            </div>
          )}

          {/* Load more indicator */}
          {hasMore && filteredTasks.length > 0 && (
            <div className="relative cursor-default select-none py-2 px-4 text-gray-500 dark:text-gray-400 text-center text-xs">
              {isLoading ? 'Loading more...' : 'Scroll for more...'}
            </div>
          )}
        </ComboboxOptions>
      </div>
    </Combobox>
  );
};
