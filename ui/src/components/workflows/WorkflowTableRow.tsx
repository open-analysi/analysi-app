import React, { useCallback, memo } from 'react';

import { PlayIcon, EyeIcon, CalendarIcon, UserIcon } from '@heroicons/react/24/outline';

import { useWorkflowStore } from '../../store/workflowStore';
import { Workflow } from '../../types/workflow';
import { highlightText } from '../../utils/highlight';

interface WorkflowTableRowProps {
  workflow: Workflow;
}

const WorkflowTableRowComponent: React.FC<WorkflowTableRowProps> = ({ workflow }) => {
  // Get search term from store for highlighting
  const searchTerm = useWorkflowStore((state) => state.searchTerm);

  const formatDate = useCallback((dateString: string) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleString();
  }, []);

  const getTypeIndicator = () => {
    if (workflow.is_dynamic) {
      return (
        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300">
          Dynamic
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300">
        Static
      </span>
    );
  };

  const handleExecuteClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    // TODO: Implement workflow execution dialog
    console.log('Execute workflow:', workflow.id);
  };

  const handleViewClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    // TODO: Implement workflow visualizer navigation
    console.log('View workflow:', workflow.id);
  };

  const handleRowClick = () => {
    // TODO: Implement workflow details navigation
    console.log('Navigate to workflow details:', workflow.id);
  };

  return (
    <tr
      className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer transition-colors"
      onClick={handleRowClick}
    >
      {/* Name */}
      <td className="px-6 py-4 wrap-break-word">
        <div className="flex items-center space-x-3">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-gray-900 dark:text-gray-100 wrap-break-word">
              {highlightText(workflow.name, searchTerm)}
            </div>
            <div className="mt-1">{getTypeIndicator()}</div>
          </div>
        </div>
      </td>

      {/* Description */}
      <td className="px-6 py-4 wrap-break-word">
        <div className="text-sm text-gray-900 dark:text-gray-300 wrap-break-word line-clamp-2">
          {workflow.description ? (
            highlightText(workflow.description, searchTerm)
          ) : (
            <span className="text-gray-400 italic">No description</span>
          )}
        </div>
      </td>

      {/* Node Count */}
      <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-300">
        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">
          {workflow.nodes?.length || 0}
        </span>
      </td>

      {/* Edge Count */}
      <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-300">
        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300">
          {workflow.edges?.length || 0}
        </span>
      </td>

      {/* Created By */}
      <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-300">
        <div className="flex items-center space-x-2">
          <UserIcon className="h-4 w-4 text-gray-400" />
          <span className="wrap-break-word">
            {highlightText(workflow.created_by || 'Unknown', searchTerm)}
          </span>
        </div>
      </td>

      {/* Created At */}
      <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-300">
        <div className="flex items-center space-x-2">
          <CalendarIcon className="h-4 w-4 text-gray-400" />
          <span>{formatDate(workflow.created_at)}</span>
        </div>
        <div className="mt-2 flex items-center space-x-2">
          {/* Execute Button */}
          <button
            onClick={handleExecuteClick}
            className="inline-flex items-center px-2 py-1 border border-transparent text-xs font-medium rounded-md text-white bg-primary hover:bg-primary/90 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary transition-colors"
            title="Execute workflow"
          >
            <PlayIcon className="h-3 w-3 mr-1" />
            Execute
          </button>

          {/* View Button */}
          <button
            onClick={handleViewClick}
            className="inline-flex items-center px-2 py-1 border border-gray-300 dark:border-gray-600 text-xs font-medium rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary transition-colors"
            title="View workflow blueprint"
          >
            <EyeIcon className="h-3 w-3 mr-1" />
            View
          </button>
        </div>
      </td>
    </tr>
  );
};

export const WorkflowTableRow = memo(WorkflowTableRowComponent);
