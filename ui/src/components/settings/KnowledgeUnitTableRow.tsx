import React, { useEffect, useState, useCallback, memo } from 'react';

import {
  ChevronDownIcon,
  ChevronRightIcon,
  PencilSquareIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { useUserDisplay } from '../../hooks/useUserDisplay';
import { backendApi } from '../../services/backendApi';
import { useKnowledgeUnitStore } from '../../store/knowledgeUnitStore';
import { componentStyles } from '../../styles/components';
import {
  ColumnSchema,
  DirectiveKU,
  DocumentKU,
  KnowledgeUnit,
  TableCellValue,
  TableKU,
  TableSchema,
  ToolKU,
} from '../../types/knowledge';
import { highlightText } from '../../utils/highlight';

interface KnowledgeUnitTableRowProps {
  knowledgeUnit: KnowledgeUnit;
  expanded: boolean;
  onRowClick: () => void;
  onToggleExpand: (e: React.MouseEvent) => void;
  onEdit?: (knowledgeUnit: KnowledgeUnit) => void;
  onDelete?: (knowledgeUnit: KnowledgeUnit) => void;
}

const KnowledgeUnitTableRowComponent: React.FC<KnowledgeUnitTableRowProps> = ({
  knowledgeUnit,
  expanded,
  onRowClick,
  onToggleExpand,
  onEdit,
  onDelete,
}) => {
  const [detailedKnowledgeUnit, setDetailedKnowledgeUnit] = useState<KnowledgeUnit>();
  const [loading, setLoading] = useState(false);
  const { runSafe } = useErrorHandler('KnowledgeUnitTableRow');

  // Get search term from store for highlighting
  const searchTerm = useKnowledgeUnitStore((state) => state.searchTerm);

  // Resolve user UUID to display name
  const createdByDisplay = useUserDisplay(knowledgeUnit.created_by);

  useEffect(() => {
    // Fetch detailed information when row is expanded
    if (expanded && !detailedKnowledgeUnit) {
      const fetchDetailedInfo = async () => {
        setLoading(true);
        try {
          let result;

          // Fetch the appropriate type-specific data
          switch (knowledgeUnit.type) {
            case 'directive': {
              [result] = await runSafe(
                backendApi.getDirective(knowledgeUnit.id),
                'fetchDirective',
                { action: 'fetching directive details', entityId: knowledgeUnit.id }
              );
              break;
            }
            case 'table': {
              [result] = await runSafe(backendApi.getTable(knowledgeUnit.id), 'fetchTable', {
                action: 'fetching table details',
                entityId: knowledgeUnit.id,
              });
              break;
            }
            case 'tool': {
              // Tool detail endpoint not available on backend — use list data directly
              // (list response already includes mcp_endpoint and integration_id)
              result = knowledgeUnit;
              break;
            }
            case 'document': {
              [result] = await runSafe(backendApi.getDocument(knowledgeUnit.id), 'fetchDocument', {
                action: 'fetching document details',
                entityId: knowledgeUnit.id,
              });
              break;
            }
            // No default needed — all KnowledgeUnit types handled above
          }

          if (result) {
            // Service functions return the KU directly (no wrapper)
            setDetailedKnowledgeUnit(result as KnowledgeUnit);

            // Don't try to fetch dependent tasks since the API endpoint
            // is giving CORS and 500 errors - this is a backend issue
            // We'll just skip this part for now

            /* Commented out to prevent CORS errors
            try {
              // Fetch tasks that depend on this KU
              const [tasksResult] = await runSafe(
                backendApi.getKnowledgeUnitTasks(knowledgeUnit.id),
                'fetchKnowledgeUnitTasks',
                { action: 'fetching dependent tasks', entityId: knowledgeUnit.id }
              );
              
              if (tasksResult && tasksResult.data) {
                setDependentTasks(tasksResult.data);
              }
            } catch (error) {
              console.log('Could not fetch dependent tasks, skipping this section');
            }
            */
          }
        } finally {
          setLoading(false);
        }
      };

      void fetchDetailedInfo();
    }
  }, [expanded, knowledgeUnit, detailedKnowledgeUnit, runSafe]);

  const formatDate = useCallback((dateString: string) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString();
  }, []);

  const getTypeColor = useCallback((type: string) => {
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
      case 'document': {
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300';
      }
      case 'index': {
        return 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-100 font-semibold dark:border dark:border-purple-600';
      }
      default: {
        return 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300';
      }
    }
  }, []);

  const getStatusColor = useCallback((status: string) => {
    switch (status) {
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

  const renderDirectiveContent = useCallback(
    (directive: DirectiveKU) => (
      <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-700 rounded-md">
        <h4 className="text-sm font-medium mb-2 text-gray-700 dark:text-gray-200">
          Directive Content:
        </h4>
        <div className="p-3 bg-gray-200 dark:bg-gray-600 rounded-sm whitespace-pre-wrap text-gray-800 dark:text-gray-200 text-sm font-mono">
          {highlightText(directive.content, searchTerm)}
        </div>

        {directive.referenced_tables && directive.referenced_tables.length > 0 && (
          <div className="mt-3">
            <h4 className="text-sm font-medium mb-2 text-gray-700 dark:text-gray-200">
              Referenced Tables:
            </h4>
            <ul className="list-disc list-inside text-sm text-gray-700 dark:text-gray-300">
              {directive.referenced_tables.map((table, index) => (
                <li key={index}>
                  {highlightText(typeof table === 'string' ? table : table.name, searchTerm)}
                </li>
              ))}
            </ul>
          </div>
        )}

        {directive.referenced_documents && directive.referenced_documents.length > 0 && (
          <div className="mt-3">
            <h4 className="text-sm font-medium mb-2 text-gray-700 dark:text-gray-200">
              Referenced Documents:
            </h4>
            <ul className="list-disc list-inside text-sm text-gray-700 dark:text-gray-300">
              {directive.referenced_documents.map((doc, index) => (
                <li key={index}>
                  {highlightText(typeof doc === 'string' ? doc : doc.name, searchTerm)}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    ),
    [searchTerm]
  );

  interface TableWithMetadata {
    content?: Record<string, unknown>;
    row_count?: number;
    column_count?: number;
  }

  const renderTableContent = useCallback(
    (table: TableWithMetadata) => {
      const tableKU = table as TableKU;
      const hasSchema =
        tableKU.schema && typeof tableKU.schema === 'object' && 'columns' in tableKU.schema;

      // Handle both backend formats: { rows: [...] } and { columns: [...], data: [...] }
      const contentRecord = table.content;
      let columns: string[] = [];
      let rows: Record<string, TableCellValue>[] = [];
      let hasData = false;

      const rawRows = contentRecord?.['rows'];
      const rawColumns = contentRecord?.['columns'];
      const rawData = contentRecord?.['data'];

      if (Array.isArray(rawRows) && rawRows.length > 0) {
        // Format 1: { rows: [{col1: val, col2: val}, ...] }
        columns = Object.keys(rawRows[0] as Record<string, unknown>);
        rows = rawRows as Record<string, TableCellValue>[];
        hasData = true;
      } else if (Array.isArray(rawColumns) && rawColumns.length > 0) {
        // Format 2: { columns: [...], data: [[val, val], ...] }
        columns = rawColumns as string[];
        if (Array.isArray(rawData) && rawData.length > 0) {
          // Convert array format to object format for rendering
          rows = (rawData as TableCellValue[][]).map((rowData) => {
            const rowObj: Record<string, TableCellValue> = {};
            for (const [idx, col] of columns.entries()) {
              rowObj[col] = rowData[idx];
            }
            return rowObj;
          });
          hasData = true;
        }
      }

      return (
        <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-700 rounded-md">
          <h4 className="text-sm font-medium mb-2 text-gray-700 dark:text-gray-200">
            Table Content:{' '}
            <span className="text-xs text-gray-500">
              ({table.row_count || 0} rows, {table.column_count || 0} columns)
            </span>
            {hasSchema && <span className="ml-2 text-xs text-primary">(Schema defined)</span>}
          </h4>

          {hasData ? (
            <div className="overflow-x-auto">
              <table className="min-w-full bg-white dark:bg-gray-600 rounded-sm border border-gray-200 dark:border-gray-700">
                <thead>
                  <tr className="bg-gray-200 dark:bg-gray-800">
                    {columns.map((col, index) => {
                      const columnSchema =
                        hasSchema &&
                        (tableKU.schema as TableSchema).columns?.find(
                          (c: ColumnSchema) => c.name === col
                        );
                      return (
                        <th
                          key={index}
                          className="px-3 py-2 text-left text-xs font-medium text-gray-600 dark:text-gray-200 uppercase tracking-wider"
                        >
                          <div>
                            {highlightText(col, searchTerm)}
                            {columnSchema && (
                              <span className="ml-1 text-xs font-normal text-gray-500 dark:text-gray-400">
                                ({columnSchema.type})
                              </span>
                            )}
                          </div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row: Record<string, TableCellValue>, rowIndex: number) => (
                    <tr key={rowIndex} className="border-t border-gray-200 dark:border-gray-700">
                      {columns.map((col, cellIndex) => {
                        const cellContent =
                          typeof row[col] === 'object' && row[col] !== null
                            ? JSON.stringify(row[col])
                            : String(row[col] ?? '');
                        return (
                          <td
                            key={cellIndex}
                            className="px-3 py-2 text-xs text-gray-700 dark:text-gray-200"
                          >
                            {highlightText(cellContent, searchTerm)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-sm text-gray-600 dark:text-gray-400">No table data available</div>
          )}
        </div>
      );
    },
    [searchTerm]
  );

  const renderToolContent = useCallback(
    (tool: ToolKU) => (
      <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-700 rounded-md">
        <h4 className="text-sm font-medium mb-2 text-gray-700 dark:text-gray-200">Tool Details:</h4>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
          <span className="font-medium">MCP Endpoint:</span>{' '}
          {highlightText(tool.mcp_endpoint, searchTerm)}
        </p>

        {tool.integration_id && (
          <p className="text-sm text-gray-600 dark:text-gray-400">
            <span className="font-medium">Integration ID:</span>{' '}
            {highlightText(tool.integration_id, searchTerm)}
          </p>
        )}
      </div>
    ),
    [searchTerm]
  );

  const renderDocumentContent = useCallback(
    (document: DocumentKU) => (
      <div className="mt-4 p-3 bg-gray-50 dark:bg-gray-700 rounded-md">
        <h4 className="text-sm font-medium mb-2 text-gray-700 dark:text-gray-200">
          Document Details:{' '}
          <span className="text-xs text-gray-500">
            ({highlightText(document.document_type, searchTerm)})
          </span>
        </h4>

        <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
          <span className="font-medium">Source:</span>{' '}
          {highlightText(document.content_source, searchTerm)}
          {document.source_url && highlightText(` (${document.source_url})`, searchTerm)}
        </p>

        {document.content && (
          <div className="mt-2">
            <h5 className="text-xs font-medium mb-1 text-gray-700 dark:text-gray-300">
              Content Preview:
            </h5>
            <div className="p-3 bg-gray-200 dark:bg-gray-600 rounded-sm text-xs text-gray-800 dark:text-gray-200 max-h-32 overflow-y-auto whitespace-pre-wrap font-mono">
              {highlightText(
                document.content.length > 500
                  ? `${document.content.slice(0, 500)}...`
                  : document.content,
                searchTerm
              )}
            </div>
          </div>
        )}

        {document.vectorized && (
          <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
            <p className="flex items-center">
              <span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-2"></span>
              Vectorized for semantic search
            </p>
          </div>
        )}
      </div>
    ),
    [searchTerm]
  );

  const renderDependentTasks = useCallback(() => {
    // Dependent tasks feature is disabled due to backend API issues
    return null;
  }, []);

  // Render type-specific content section
  const renderTypeSpecificContent = useCallback(() => {
    if (!detailedKnowledgeUnit) return null;

    switch (knowledgeUnit.type) {
      case 'directive': {
        return renderDirectiveContent(detailedKnowledgeUnit as DirectiveKU);
      }
      case 'table': {
        return renderTableContent(detailedKnowledgeUnit as TableKU);
      }
      case 'tool': {
        return renderToolContent(detailedKnowledgeUnit as ToolKU);
      }
      case 'document': {
        return renderDocumentContent(detailedKnowledgeUnit as DocumentKU);
      }
      default: {
        return null;
      }
    }
  }, [
    detailedKnowledgeUnit,
    knowledgeUnit.type,
    renderDirectiveContent,
    renderTableContent,
    renderToolContent,
    renderDocumentContent,
  ]);

  return (
    <>
      <tr
        className={componentStyles.tableRow}
        onClick={onRowClick}
        data-testid={`knowledge-unit-row-${knowledgeUnit.id}`}
      >
        <td className={`${componentStyles.tableCell}`}>
          <div className="flex items-start">
            <button
              onClick={onToggleExpand}
              className="mr-2 mt-1 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 shrink-0"
              aria-label={expanded ? 'Collapse row' : 'Expand row'}
            >
              {expanded ? (
                <ChevronDownIcon className="h-4 w-4" />
              ) : (
                <ChevronRightIcon className="h-4 w-4" />
              )}
            </button>
            <div className="wrap-break-word min-w-0">
              {highlightText(knowledgeUnit.name, searchTerm)}
            </div>
          </div>
        </td>
        <td className={componentStyles.tableCell}>
          <div className="wrap-break-word line-clamp-2">
            {highlightText(knowledgeUnit.description, searchTerm)}
          </div>
          {knowledgeUnit.tags && knowledgeUnit.tags.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {knowledgeUnit.tags.slice(0, 3).map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] leading-tight bg-dark-600 text-gray-300 border border-gray-600/50"
                >
                  {tag}
                </span>
              ))}
              {knowledgeUnit.tags.length > 3 && (
                <span className="text-[11px] text-gray-500">+{knowledgeUnit.tags.length - 3}</span>
              )}
            </div>
          )}
        </td>
        <td className={componentStyles.tableCell}>
          <span
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getTypeColor(knowledgeUnit.type)}`}
          >
            {highlightText(knowledgeUnit.type, searchTerm)}
          </span>
        </td>
        <td className={componentStyles.tableCell}>{createdByDisplay}</td>
        <td className={componentStyles.tableCell}>{formatDate(knowledgeUnit.created_at)}</td>
        <td className={componentStyles.tableCell}>
          <span
            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(knowledgeUnit.status)}`}
          >
            {knowledgeUnit.status}
          </span>
        </td>
        <td className={componentStyles.tableCell}>{knowledgeUnit.version}</td>
        <td className={componentStyles.tableCell}>
          <div className="flex items-center gap-2">
            {knowledgeUnit.editable && knowledgeUnit.type !== 'tool' && onEdit && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(knowledgeUnit);
                }}
                className="text-gray-400 hover:text-primary transition-colors"
                title="Edit"
              >
                <PencilSquareIcon className="h-4 w-4" />
              </button>
            )}
            {knowledgeUnit.editable && knowledgeUnit.type !== 'tool' && onDelete && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(knowledgeUnit);
                }}
                className="text-gray-400 hover:text-red-400 transition-colors"
                title="Delete"
              >
                <TrashIcon className="h-4 w-4" />
              </button>
            )}
          </div>
        </td>
      </tr>

      {expanded && (
        <tr>
          <td
            colSpan={8}
            className="bg-gray-50 dark:bg-gray-800 px-4 py-3 border-t border-b border-gray-200 dark:border-gray-700"
          >
            {loading ? (
              <div className="flex justify-center py-6" role="status" aria-label="Loading">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
              </div>
            ) : (
              <div>
                <h3 className="text-lg font-semibold mb-2 text-gray-800 dark:text-gray-100">
                  {highlightText(knowledgeUnit.name, searchTerm)}
                </h3>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                  {highlightText(knowledgeUnit.description, searchTerm)}
                </p>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm text-gray-700 dark:text-gray-300">
                  <div>
                    <p className="mb-1">
                      <span className="font-medium">ID:</span> {knowledgeUnit.id}
                    </p>
                    <p className="mb-1">
                      <span className="font-medium">Type:</span>{' '}
                      {highlightText(knowledgeUnit.type, searchTerm)}
                    </p>
                    <p className="mb-1">
                      <span className="font-medium">Created by:</span> {createdByDisplay}
                    </p>
                  </div>
                  <div>
                    <p className="mb-1">
                      <span className="font-medium">Status:</span>{' '}
                      {highlightText(knowledgeUnit.status, searchTerm)}
                    </p>
                    <p className="mb-1">
                      <span className="font-medium">Version:</span>{' '}
                      {highlightText(knowledgeUnit.version, searchTerm)}
                    </p>
                    <p className="mb-1">
                      <span className="font-medium">Created:</span>{' '}
                      {formatDate(knowledgeUnit.created_at)}
                    </p>
                    <p className="mb-1">
                      <span className="font-medium">Updated:</span>{' '}
                      {formatDate(knowledgeUnit.updated_at)}
                    </p>
                  </div>
                </div>

                {/* Type-specific content */}
                {renderTypeSpecificContent()}

                {/* Tasks that use this Knowledge Unit */}
                {renderDependentTasks()}

                {knowledgeUnit.tags && knowledgeUnit.tags.length > 0 && (
                  <div className="mt-3">
                    <h4 className="text-sm font-medium mb-1 text-gray-700 dark:text-gray-200">
                      Categories:
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {knowledgeUnit.tags.map((tag) => (
                        <span
                          key={tag}
                          className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-dark-600 text-gray-300 border border-gray-700/50"
                        >
                          {highlightText(tag, searchTerm)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {knowledgeUnit.usage_stats && (
                  <div className="mt-3 p-2 bg-gray-100 dark:bg-gray-700 rounded-sm">
                    <h4 className="text-sm font-medium mb-1 text-gray-700 dark:text-gray-200">
                      Usage Statistics:
                    </h4>
                    <p className="text-sm text-gray-700 dark:text-gray-300">
                      <span className="font-medium">Count:</span> {knowledgeUnit.usage_stats.count}
                    </p>
                    {knowledgeUnit.usage_stats.last_used && (
                      <p className="text-sm text-gray-700 dark:text-gray-300">
                        <span className="font-medium">Last Used:</span>{' '}
                        {formatDate(knowledgeUnit.usage_stats.last_used)}
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
};

// Memoize the component to prevent unnecessary re-renders
export const KnowledgeUnitTableRow = memo(KnowledgeUnitTableRowComponent);
