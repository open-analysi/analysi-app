import React, { useMemo } from 'react';

import { ChevronUpIcon, ChevronDownIcon, RectangleGroupIcon } from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { WorkflowSortField } from '../../store/workflowStore';
import { componentStyles } from '../../styles/components';
import { Workflow } from '../../types/workflow';
import { EmptyState } from '../common/EmptyState';
import { ErrorMessage } from '../common/ErrorMessage';
import { Pagination } from '../common/Pagination';

import { WorkflowTableRow } from './WorkflowTableRow';

interface WorkflowsTableProps {
  workflows: Workflow[];
  loading: boolean;
  totalCount: number;
  currentPage: number;
  itemsPerPage: number;
  sortField: WorkflowSortField;
  sortDirection: 'asc' | 'desc';
  onPageChange: (page: number) => void;
  onSortChange: (field: WorkflowSortField) => void;
}

export const WorkflowsTable: React.FC<WorkflowsTableProps> = ({
  workflows,
  loading,
  totalCount,
  currentPage,
  itemsPerPage,
  sortField,
  sortDirection,
  onPageChange,
  onSortChange,
}) => {
  const { error, clearError } = useErrorHandler('WorkflowsTable');

  const renderSortIndicator = useMemo(
    function renderSortIndicator() {
      return function renderSortIcon(field: WorkflowSortField) {
        return sortField === field ? (
          sortDirection === 'asc' ? (
            <ChevronUpIcon className="w-4 h-4 inline-block ml-1" />
          ) : (
            <ChevronDownIcon className="w-4 h-4 inline-block ml-1" />
          )
        ) : (
          <></>
        );
      };
    },
    [sortField, sortDirection]
  );

  const handleSort = (field: WorkflowSortField) => {
    onSortChange(field);
  };

  const totalPages = Math.ceil(totalCount / itemsPerPage);

  if (loading) {
    return (
      <div className={componentStyles.card}>
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          <span className="ml-3 text-gray-600 dark:text-gray-300">Loading workflows...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={componentStyles.card}>
      {error.hasError && <ErrorMessage message={error.message} onDismiss={clearError} />}

      {totalPages > 1 && (
        <div className="mb-4">
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={totalCount}
            itemsPerPage={itemsPerPage}
            onPageChange={onPageChange}
          />
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 table-fixed">
          <colgroup>
            <col style={{ width: '25%' }} /> {/* Name */}
            <col style={{ width: '33%' }} /> {/* Description */}
            <col style={{ width: '8%' }} /> {/* Nodes */}
            <col style={{ width: '8%' }} /> {/* Edges */}
            <col style={{ width: '11%' }} /> {/* Created By */}
            <col style={{ width: '15%' }} /> {/* Created At */}
          </colgroup>
          <thead className={componentStyles.tableHeader}>
            <tr>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                onClick={() => handleSort('name')}
              >
                Name {renderSortIndicator('name')}
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                onClick={() => handleSort('description')}
              >
                Description {renderSortIndicator('description')}
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
              >
                Nodes
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
              >
                Edges
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                onClick={() => handleSort('created_by')}
              >
                Created By {renderSortIndicator('created_by')}
              </th>
              <th
                scope="col"
                className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                onClick={() => handleSort('created_at')}
              >
                Created {renderSortIndicator('created_at')}
              </th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
            {workflows.length === 0 ? (
              <tr>
                <td colSpan={6}>
                  <EmptyState
                    icon={RectangleGroupIcon}
                    title={totalCount === 0 ? 'No workflows found' : 'No matches found'}
                    message={
                      totalCount === 0
                        ? 'Create your first workflow to start automating tasks'
                        : 'No workflows match your search criteria. Try adjusting your search terms.'
                    }
                  />
                </td>
              </tr>
            ) : (
              workflows.map((workflow) => (
                <WorkflowTableRow key={workflow.id} workflow={workflow} />
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="mt-4">
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={totalCount}
            itemsPerPage={itemsPerPage}
            onPageChange={onPageChange}
          />
        </div>
      )}

      {workflows.length > 0 && (
        <div className="mt-4 text-sm text-gray-500 dark:text-gray-400 text-center">
          Showing {(currentPage - 1) * itemsPerPage + 1} to{' '}
          {Math.min(currentPage * itemsPerPage, totalCount)} of {totalCount} workflows
        </div>
      )}
    </div>
  );
};
