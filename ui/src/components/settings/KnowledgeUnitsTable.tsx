import React, { useState, useCallback, useMemo } from 'react';

import { ChevronUpIcon, ChevronDownIcon } from '@heroicons/react/24/outline';

import { componentStyles } from '../../styles/components';
import { KnowledgeUnit } from '../../types/knowledge';
import { Pagination } from '../common/Pagination';

import { KnowledgeUnitTableRow } from './KnowledgeUnitTableRow';

interface KnowledgeUnitsTableProps {
  knowledgeUnits: KnowledgeUnit[];
  loading: boolean;
  totalCount: number;
  currentPage: number;
  itemsPerPage: number;
  sortField: string;
  sortDirection: 'asc' | 'desc';
  onPageChange: (page: number) => void;
  onSort: (field: string) => void;
  onRowClick: (id: string) => void;
  onEdit?: (knowledgeUnit: KnowledgeUnit) => void;
  onDelete?: (knowledgeUnit: KnowledgeUnit) => void;
}

export const KnowledgeUnitsTable: React.FC<KnowledgeUnitsTableProps> = ({
  knowledgeUnits,
  loading,
  totalCount,
  currentPage,
  itemsPerPage,
  sortField,
  sortDirection,
  onPageChange,
  onSort,
  onRowClick,
  onEdit,
  onDelete,
}) => {
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});

  const toggleRowExpanded = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
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
        if (sortField !== field) return <></>;
        return sortDirection === 'asc' ? (
          <ChevronUpIcon className="w-4 h-4 inline-block ml-1" />
        ) : (
          <ChevronDownIcon className="w-4 h-4 inline-block ml-1" />
        );
      };
    },
    [sortField, sortDirection]
  );

  const totalPages = Math.ceil(totalCount / itemsPerPage);

  return (
    <div className={componentStyles.card}>
      {totalPages > 1 && (
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
        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 table-auto">
          <colgroup>
            <col className="w-[23%] min-w-[200px]" />
            <col className="w-[32%] min-w-[250px]" />
            <col className="w-[10%] min-w-[100px]" />
            <col className="w-[10%] min-w-[100px]" />
            <col className="w-[8%] min-w-[80px]" />
            <col className="w-[7%] min-w-[80px]" />
            <col className="w-[5%] min-w-[70px]" />
            <col className="w-[5%] min-w-[50px]" />
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
                onClick={() => onSort('type')}
              >
                Type {renderSortIndicator('type')}
              </th>
              <th
                className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                onClick={() => onSort('owner')}
              >
                Created By {renderSortIndicator('owner')}
              </th>
              <th
                className={`${componentStyles.tableHeaderCell} cursor-pointer hover:bg-dark-600`}
                onClick={() => onSort('created_at')}
              >
                Created {renderSortIndicator('created_at')}
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
              <th className={componentStyles.tableHeaderCell}>Actions</th>
            </tr>
          </thead>
          <tbody className={componentStyles.tableBody}>
            {loading && (
              <tr>
                <td colSpan={8} className="text-center py-4">
                  <div className="flex justify-center items-center space-x-2">
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary"></div>
                    <span>Loading knowledge units...</span>
                  </div>
                </td>
              </tr>
            )}
            {!loading && knowledgeUnits.length === 0 && (
              <tr>
                <td colSpan={8} className="text-center py-8">
                  <div className="flex flex-col items-center space-y-3">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-10 w-10 text-gray-400"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"
                      />
                    </svg>
                    <p className="text-lg font-medium text-gray-400">No knowledge units found</p>
                    <p className="text-sm text-gray-500 max-w-md">
                      No knowledge units match your current filters. Try selecting at least one
                      option in each filter category.
                    </p>
                    <button
                      onClick={() => window.dispatchEvent(new CustomEvent('resetFilters'))}
                      className="mt-2 px-4 py-2 bg-dark-700 hover:bg-dark-600 text-gray-300 rounded-sm text-sm"
                    >
                      Reset All Filters
                    </button>
                  </div>
                </td>
              </tr>
            )}
            {!loading &&
              knowledgeUnits.length > 0 &&
              knowledgeUnits
                .filter((ku) => ku != undefined && ku.id != undefined)
                .map((ku) => (
                  <KnowledgeUnitTableRow
                    key={ku.id}
                    knowledgeUnit={ku}
                    expanded={isRowExpanded(ku.id)}
                    onRowClick={() => onRowClick(ku.id)}
                    onToggleExpand={(e) => toggleRowExpanded(ku.id, e)}
                    onEdit={onEdit}
                    onDelete={onDelete}
                  />
                ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
