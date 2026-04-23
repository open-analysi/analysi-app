import React, { useCallback, useState, useMemo } from 'react';

import { ChevronUpIcon, ChevronDownIcon, FunnelIcon } from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { componentStyles } from '../../styles/components';
import { Task } from '../../types/knowledge';
import { EmptyState } from '../common/EmptyState';
import { ErrorMessage } from '../common/ErrorMessage';
import { Pagination } from '../common/Pagination';

import { TaskTableRow } from './TaskTableRow';

interface TasksTableProps {
  tasks: Task[];
  loading: boolean;
  totalCount: number;
  currentPage: number;
  itemsPerPage: number;
  sortField: string;
  sortDirection: 'asc' | 'desc';
  onPageChange: (page: number) => void;
  onSort: (field: string) => void;
  onDeleteTask?: (taskId: string) => void;
}

export const TasksTable: React.FC<TasksTableProps> = ({
  tasks,
  loading,
  totalCount,
  currentPage,
  itemsPerPage,
  sortField,
  sortDirection,
  onPageChange,
  onSort,
  onDeleteTask,
}) => {
  const { error, clearError } = useErrorHandler('TasksTable');
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});

  const toggleRowExpanded = useCallback((id: string) => {
    setExpandedRows((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  }, []);

  const isRowExpanded = useCallback(
    (id: string): boolean => {
      return !!expandedRows[id];
    },
    [expandedRows]
  );

  const renderSortIndicator = useMemo(
    function renderSortIndicator() {
      return function renderSortIcon(field: string) {
        if (sortField !== field) {
          return <></>;
        }
        if (sortDirection === 'asc') {
          return <ChevronUpIcon className="w-4 h-4 inline-block ml-1" />;
        }
        return <ChevronDownIcon className="w-4 h-4 inline-block ml-1" />;
      };
    },
    [sortField, sortDirection]
  );

  const totalPages = Math.ceil(totalCount / itemsPerPage);

  const getTableBodyContent = (): React.JSX.Element[] => {
    if (loading) {
      return [
        <tr key="loading">
          <td colSpan={9} className="text-center py-4">
            <div className="flex justify-center items-center space-x-2">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary"></div>
              <span>Loading tasks...</span>
            </div>
          </td>
        </tr>,
      ];
    }

    if (tasks.length === 0) {
      return [
        <tr key="empty">
          <td colSpan={9}>
            <EmptyState
              icon={FunnelIcon}
              title="No tasks found"
              message="No tasks match your current filters. Try selecting at least one option in each filter category."
              actionLabel="Reset All Filters"
              onAction={() => window.dispatchEvent(new CustomEvent('resetFilters'))}
            />
          </td>
        </tr>,
      ];
    }

    return tasks.map((task) => (
      <TaskTableRow
        key={task.id}
        task={task}
        expanded={isRowExpanded(task.id)}
        onToggleExpand={() => toggleRowExpanded(task.id)}
        onDelete={onDeleteTask}
      />
    ));
  };

  return (
    <div className={componentStyles.card}>
      {error.hasError && <ErrorMessage message={error.message} onDismiss={clearError} />}
      {totalCount > 0 && (
        <div className="mb-2">
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
            <col style={{ width: '20%' }} />
            <col style={{ width: '28%' }} />
            <col style={{ width: '10%' }} />
            <col style={{ width: '7%' }} />
            <col style={{ width: '9%' }} />
            <col style={{ width: '7%' }} />
            <col style={{ width: '4%' }} />
            <col style={{ width: '10%' }} />
            <col style={{ width: '5%' }} />
          </colgroup>
          <thead className={componentStyles.tableHeader}>
            <tr>
              <th
                className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                onClick={() => onSort('name')}
              >
                Name {renderSortIndicator('name')}
              </th>
              <th
                className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                onClick={() => onSort('description')}
              >
                Description {renderSortIndicator('description')}
              </th>
              <th
                className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                onClick={() => onSort('function')}
              >
                Function {renderSortIndicator('function')}
              </th>
              <th
                className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                onClick={() => onSort('scope')}
              >
                Scope {renderSortIndicator('scope')}
              </th>
              <th
                className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                onClick={() => onSort('owner')}
              >
                Created By {renderSortIndicator('owner')}
              </th>
              <th
                className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                onClick={() => onSort('status')}
              >
                Status {renderSortIndicator('status')}
              </th>
              <th
                className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                onClick={() => onSort('version')}
              >
                Version {renderSortIndicator('version')}
              </th>
              <th
                className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                onClick={() => onSort('created_at')}
              >
                Created {renderSortIndicator('created_at')}
              </th>
              <th className={componentStyles.tableHeaderCell}>Actions</th>
            </tr>
          </thead>
          <tbody className={componentStyles.tableBody}>{getTableBodyContent()}</tbody>
        </table>
      </div>
      {totalCount > itemsPerPage && (
        <div className="mt-2">
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={totalCount}
            itemsPerPage={itemsPerPage}
            onPageChange={onPageChange}
          />
        </div>
      )}
    </div>
  );
};
