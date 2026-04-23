import React, { useState, useCallback } from 'react';

import {
  ArrowPathIcon,
  DocumentMagnifyingGlassIcon,
  ChevronDoubleDownIcon,
  ChevronDoubleUpIcon,
} from '@heroicons/react/24/outline';

import { TaskRun } from '../../types/taskRun';

import { FindingCard } from './FindingCard';

interface FindingsTabProps {
  taskRuns: TaskRun[];
  loading?: boolean;
}

export const FindingsTab: React.FC<FindingsTabProps> = ({ taskRuns, loading = false }) => {
  // Track which cards are expanded (by task run ID)
  const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());

  const expandableTaskRuns = taskRuns.filter(
    (t) => t.status === 'completed' || t.status === 'failed'
  );

  const handleExpandAll = useCallback(() => {
    setExpandedCards(new Set(expandableTaskRuns.map((t) => t.id)));
  }, [expandableTaskRuns]);

  const handleCollapseAll = useCallback(() => {
    setExpandedCards(new Set());
  }, []);

  const handleToggleCard = useCallback((taskRunId: string) => {
    setExpandedCards((prev) => {
      const next = new Set(prev);
      if (next.has(taskRunId)) {
        next.delete(taskRunId);
      } else {
        next.add(taskRunId);
      }
      return next;
    });
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[400px] text-gray-400">
        <ArrowPathIcon className="h-8 w-8 animate-spin mb-4" />
        <p>Loading findings...</p>
      </div>
    );
  }

  if (taskRuns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[400px] text-gray-400">
        <DocumentMagnifyingGlassIcon className="h-12 w-12 mb-4" />
        <p className="text-lg mb-2">No Findings Available</p>
        <p className="text-sm">No tasks have been executed for this analysis yet.</p>
      </div>
    );
  }

  // Sort task runs: completed first, then failed, then running, then pending
  const sortedTaskRuns = [...taskRuns].sort((a, b) => {
    const statusOrder: Record<string, number> = { completed: 0, failed: 1, running: 2, pending: 3 };
    return (statusOrder[a.status] || 4) - (statusOrder[b.status] || 4);
  });

  const allExpanded =
    expandableTaskRuns.length > 0 && expandedCards.size === expandableTaskRuns.length;
  const someExpanded = expandedCards.size > 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-400">
          {taskRuns.length} task{taskRuns.length !== 1 ? 's' : ''} executed
        </p>
        <div className="flex items-center gap-4">
          {/* Expand/Collapse All buttons */}
          {expandableTaskRuns.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={handleExpandAll}
                disabled={allExpanded}
                className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
                  allExpanded
                    ? 'text-gray-600 cursor-not-allowed'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-dark-700'
                }`}
                title="Expand all findings"
              >
                <ChevronDoubleDownIcon className="h-3.5 w-3.5" />
                Expand All
              </button>
              <button
                onClick={handleCollapseAll}
                disabled={!someExpanded}
                className={`flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors ${
                  !someExpanded
                    ? 'text-gray-600 cursor-not-allowed'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-dark-700'
                }`}
                title="Collapse all findings"
              >
                <ChevronDoubleUpIcon className="h-3.5 w-3.5" />
                Collapse All
              </button>
            </div>
          )}
          {/* Status indicators */}
          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500"></span>
              {taskRuns.filter((t) => t.status === 'completed').length} completed
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500"></span>
              {taskRuns.filter((t) => t.status === 'failed').length} failed
            </span>
            {taskRuns.some((t) => t.status === 'running') && (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
                {taskRuns.filter((t) => t.status === 'running').length} running
              </span>
            )}
          </div>
        </div>
      </div>

      {sortedTaskRuns.map((taskRun) => (
        <FindingCard
          key={taskRun.id}
          taskRun={taskRun}
          isExpanded={expandedCards.has(taskRun.id)}
          onToggle={() => handleToggleCard(taskRun.id)}
        />
      ))}
    </div>
  );
};
