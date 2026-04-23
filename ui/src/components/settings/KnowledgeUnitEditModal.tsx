import React, { useState, useEffect } from 'react';

import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react';
import { XMarkIcon, PlusIcon, TrashIcon, CheckIcon } from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { extractApiErrorMessage } from '../../services/apiClient';
import { backendApi } from '../../services/backendApi';
import { useKnowledgeUnitStore } from '../../store/knowledgeUnitStore';
import {
  KnowledgeUnit,
  ColumnSchema,
  TableSchema,
  TableKU,
  TableCellValue,
  DirectiveKU,
  DocumentKU,
} from '../../types/knowledge';
import { ConfirmDialog } from '../common/ConfirmDialog';

interface KnowledgeUnitEditModalProps {
  isOpen: boolean;
  onClose: () => void;
  knowledgeUnit: KnowledgeUnit | null;
  onSave?: () => void;
}

/** Parse table content from backend (rows-format or columns+data format) */
function parseTableContent(table: TableKU): {
  columns: string[];
  data: TableCellValue[][];
  schema: ColumnSchema[];
} {
  if (!table.content) {
    return { columns: [], data: [], schema: [] };
  }

  // Check if content is in rows-format (backend) vs columns+data (UI)
  const contentRecord = table.content as Record<string, unknown>;
  const rawRows = contentRecord['rows'];

  if (Array.isArray(rawRows)) {
    // Backend format: { rows: [{col1: val, col2: val}, ...] }
    const rows = rawRows as Record<string, TableCellValue>[];
    if (rows.length > 0) {
      const columns = Object.keys(rows[0]);
      const dataRows: TableCellValue[][] = rows.map((row: Record<string, TableCellValue>) =>
        // eslint-disable-next-line sonarjs/function-return-type -- returns string (JSON.stringify) or TableCellValue
        columns.map((col): TableCellValue => {
          const value: unknown = row[col];
          if (typeof value === 'object' && value !== null) {
            return JSON.stringify(value);
          }
          return value as TableCellValue;
        })
      );
      const schema: ColumnSchema[] = columns.map((col) => ({
        name: col,
        type: 'string' as const,
      }));
      return { columns, data: dataRows, schema };
    }
    return { columns: [], data: [], schema: [] };
  }

  // UI format: { columns: [...], data: [...] }
  const columns = (contentRecord['columns'] as string[] | undefined) ?? [];
  const rawData = (contentRecord['data'] as unknown[][] | undefined) ?? [];
  // Normalize object/array cell values to JSON strings
  const data: TableCellValue[][] = rawData.map((row) =>
    row.map((cell) =>
      typeof cell === 'object' && cell !== null ? JSON.stringify(cell) : (cell as TableCellValue)
    )
  );

  let schema: ColumnSchema[];
  if (table.schema && typeof table.schema === 'object' && 'columns' in table.schema) {
    schema = (table.schema as TableSchema).columns || [];
  } else {
    schema = columns.map((col: string) => ({
      name: col,
      type: 'string' as const,
    }));
  }

  return { columns, data, schema };
}

function validateCellValue(value: TableCellValue, type: ColumnSchema['type']): boolean {
  switch (type) {
    case 'number': {
      return !isNaN(Number(value));
    }
    case 'boolean': {
      return value === 'true' || value === 'false' || typeof value === 'boolean';
    }
    case 'date':
    case 'datetime': {
      return !isNaN(Date.parse(String(value)));
    }
    case 'json': {
      try {
        JSON.parse(String(value));
        return true;
      } catch {
        return false;
      }
    }
    default: {
      return true;
    }
  }
}

// sonarjs/function-return-type: each branch returns a different subtype of TableCellValue (number/boolean/string) which is intentional
// eslint-disable-next-line sonarjs/function-return-type
function convertCellValue(value: TableCellValue, type: ColumnSchema['type']): TableCellValue {
  switch (type) {
    case 'number': {
      return Number(value);
    }
    case 'boolean': {
      return value === 'true' || value === true;
    }
    case 'date':
    case 'datetime': {
      return String(value);
    }
    case 'json': {
      // Keep JSON as a string — parsing would produce objects/arrays
      // that String() can't round-trip (e.g. "[object Object]")
      return String(value);
    }
    default: {
      return String(value);
    }
  }
}

export const KnowledgeUnitEditModal: React.FC<KnowledgeUnitEditModalProps> = ({
  isOpen,
  onClose,
  knowledgeUnit,
  onSave,
}) => {
  const { updateKnowledgeUnit } = useKnowledgeUnitStore();
  const { runSafe } = useErrorHandler('KnowledgeUnitEditModal');

  // Form state
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [content, setContent] = useState('');
  const [tableData, setTableData] = useState<TableCellValue[][]>([]);
  const [tableColumns, setTableColumns] = useState<string[]>([]);
  const [tableSchema, setTableSchema] = useState<ColumnSchema[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [showSchemaEditor, setShowSchemaEditor] = useState(false);
  const [isAddingColumn, setIsAddingColumn] = useState(false);
  const [newColumnName, setNewColumnName] = useState('');
  const [newColumnType, setNewColumnType] = useState<ColumnSchema['type']>('string');
  const [saveError, setSaveError] = useState<string | undefined>(undefined);

  // Confirmation dialog state
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

  // Initialize form when knowledge unit changes
  useEffect(() => {
    if (knowledgeUnit) {
      setName(knowledgeUnit.name);
      setDescription(knowledgeUnit.description);
      setIsDirty(false);

      switch (knowledgeUnit.type) {
        case 'directive': {
          setContent(knowledgeUnit.content || '');
          break;
        }
        case 'document': {
          setContent(knowledgeUnit.content || '');
          break;
        }
        case 'table': {
          const parsed = parseTableContent(knowledgeUnit);
          setTableColumns(parsed.columns);
          setTableData(parsed.data);
          setTableSchema(parsed.schema);
          break;
        }
      }
    }
  }, [knowledgeUnit]);

  // Handle escape key with unsaved changes warning
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || event.key === 'Esc') {
        event.preventDefault();
        event.stopPropagation();

        if (isDirty) {
          setShowDiscardConfirm(true);
        } else {
          onClose();
        }
      }
    };

    document.addEventListener('keydown', handleEscape, true);
    return () => document.removeEventListener('keydown', handleEscape, true);
  }, [isDirty, onClose]);

  const handleSave = async () => {
    if (!knowledgeUnit) return;

    setIsLoading(true);
    setSaveError(undefined);

    try {
      let apiCall: Promise<DirectiveKU | TableKU | DocumentKU>;

      switch (knowledgeUnit.type) {
        case 'directive': {
          apiCall = backendApi.updateDirective(knowledgeUnit.id, {
            name,
            description,
            content,
          });
          break;
        }

        case 'document': {
          apiCall = backendApi.updateDocument(knowledgeUnit.id, {
            name,
            description,
            content,
          });
          break;
        }

        case 'table': {
          const tableUpdate: Partial<TableKU> = {
            name,
            description,
            content: {
              columns: tableColumns,
              data: tableData,
            },
          };
          if (tableSchema.length > 0) {
            tableUpdate.schema = {
              columns: tableSchema,
            };
          }
          apiCall = backendApi.updateTable(knowledgeUnit.id, tableUpdate);
          break;
        }

        default: {
          throw new Error(`Unknown knowledge unit type: ${knowledgeUnit.type}`);
        }
      }

      const [response, apiError] = await runSafe(apiCall, 'updateKnowledgeUnit', {
        action: `updating ${knowledgeUnit.type}`,
        entityId: knowledgeUnit.id,
      });

      if (apiError) {
        setSaveError(extractApiErrorMessage(apiError, 'Failed to save changes'));
        return;
      }

      if (response) {
        // Service functions now return the KU directly (no wrapper)
        updateKnowledgeUnit(knowledgeUnit.id, response as KnowledgeUnit);
        setIsDirty(false);
        onSave?.();
        onClose();
      } else {
        setSaveError('Invalid response from server');
      }
    } catch (error_: unknown) {
      const message = error_ instanceof Error ? error_.message : 'An unexpected error occurred';
      setSaveError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSafeClose = () => {
    if (isDirty) {
      setShowDiscardConfirm(true);
    } else {
      onClose();
    }
  };

  const handleConfirmDiscard = () => {
    setShowDiscardConfirm(false);
    onClose();
  };

  // Table editing functions
  const addTableRow = () => {
    const newRow: TableCellValue[] = Array.from({ length: tableColumns.length }).fill(
      ''
    ) as TableCellValue[];
    setTableData([...tableData, newRow]);
    setIsDirty(true);
  };

  const removeTableRow = (index: number) => {
    setTableData(tableData.filter((_, i) => i !== index));
    setIsDirty(true);
  };

  const addTableColumn = () => {
    setIsAddingColumn(true);
    setNewColumnName('');
    setNewColumnType('string');
  };

  const confirmAddColumn = () => {
    if (newColumnName.trim()) {
      setTableColumns([...tableColumns, newColumnName.trim()]);
      setTableData(tableData.map((row) => [...row, '']));
      // Add to schema
      setTableSchema([...tableSchema, { name: newColumnName.trim(), type: newColumnType }]);
      setIsDirty(true);
      setIsAddingColumn(false);
      setNewColumnName('');
      setNewColumnType('string');
    }
  };

  const cancelAddColumn = () => {
    setIsAddingColumn(false);
    setNewColumnName('');
    setNewColumnType('string');
  };

  const removeTableColumn = (index: number) => {
    setTableColumns(tableColumns.filter((_, i) => i !== index));
    setTableData(tableData.map((row) => row.filter((_, i) => i !== index)));
    // Remove from schema
    setTableSchema(tableSchema.filter((_, i) => i !== index));
    setIsDirty(true);
  };

  const updateTableCell = (rowIndex: number, colIndex: number, value: TableCellValue) => {
    const newData = [...tableData];
    newData[rowIndex] = [...newData[rowIndex]];
    newData[rowIndex][colIndex] = value;
    setTableData(newData);
    setIsDirty(true);
  };

  const updateColumnName = (index: number, newName: string) => {
    const newColumns = [...tableColumns];
    newColumns[index] = newName;
    setTableColumns(newColumns);
    // Update schema column name
    const newSchema = [...tableSchema];
    if (newSchema[index]) {
      newSchema[index] = { ...newSchema[index], name: newName };
      setTableSchema(newSchema);
    }
    setIsDirty(true);
  };

  // Schema management functions
  const updateColumnType = (index: number, newType: ColumnSchema['type']) => {
    const newSchema = [...tableSchema];
    if (newSchema[index]) {
      newSchema[index] = { ...newSchema[index], type: newType };
      setTableSchema(newSchema);
      setIsDirty(true);
    }
  };

  const handleCellChange = (rowIndex: number, colIndex: number, value: string) => {
    updateTableCell(rowIndex, colIndex, value);
  };

  const handleCellBlur = (
    rowIndex: number,
    colIndex: number,
    value: string,
    columnType: ColumnSchema['type']
  ) => {
    if (validateCellValue(value, columnType)) {
      updateTableCell(rowIndex, colIndex, convertCellValue(value, columnType));
    }
  };

  const renderTableCell = (
    cell: TableCellValue,
    rowIndex: number,
    colIndex: number,
    columnType: ColumnSchema['type']
  ) => {
    // For JSON or non-primitive values, use JSON.stringify so objects/arrays
    // render as valid JSON text instead of "[object Object]"
    const displayValue =
      typeof cell === 'object' && cell !== null ? JSON.stringify(cell) : String(cell);
    const isValid = validateCellValue(displayValue, columnType);
    return (
      <td key={colIndex} className="px-2 py-1">
        <input
          type={columnType === 'number' ? 'number' : 'text'}
          value={displayValue}
          onChange={(e) => handleCellChange(rowIndex, colIndex, e.target.value)}
          onBlur={(e) => handleCellBlur(rowIndex, colIndex, e.target.value, columnType)}
          className={`w-full text-sm text-gray-900 dark:text-gray-100 bg-transparent border-b ${
            isValid
              ? 'border-transparent hover:border-gray-300 dark:hover:border-gray-500'
              : 'border-red-500'
          } focus:outline-hidden focus:border-primary`}
          placeholder={columnType === 'boolean' ? 'true/false' : columnType}
        />
      </td>
    );
  };

  if (!knowledgeUnit) return null;

  const renderFormContent = () => {
    switch (knowledgeUnit.type) {
      case 'directive':
      case 'document': {
        return (
          <div>
            <label
              htmlFor="ku-content"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Content
            </label>
            <textarea
              id="ku-content"
              value={content}
              onChange={(e) => {
                setContent(e.target.value);
                setIsDirty(true);
              }}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-xs focus:outline-hidden focus:ring-primary focus:border-primary dark:bg-gray-700 dark:text-gray-300 font-mono text-sm"
              rows={15}
              placeholder={`Enter ${knowledgeUnit.type} content...`}
              required
            />
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {content.length} characters • {content.split('\n').length} lines
            </div>
          </div>
        );
      }

      case 'table': {
        return (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Table Data
              </span>
              <div className="space-x-2">
                <button
                  type="button"
                  onClick={() => setShowSchemaEditor(!showSchemaEditor)}
                  className="inline-flex items-center px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-sm text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  {showSchemaEditor ? 'Hide' : 'Show'} Schema
                </button>
                <button
                  type="button"
                  onClick={addTableRow}
                  className="inline-flex items-center px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-sm text-xs text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  <PlusIcon className="h-3 w-3 mr-1" />
                  Add Row
                </button>
              </div>
            </div>

            <div className="overflow-x-auto overflow-y-auto max-h-96 border border-gray-300 dark:border-gray-600 rounded-sm">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-700">
                  <tr>
                    {tableColumns.map((col, index) => (
                      <th key={index} className="px-2 py-1">
                        <div className="flex items-center space-x-1">
                          <input
                            type="text"
                            value={col}
                            onChange={(e) => updateColumnName(index, e.target.value)}
                            className="flex-1 text-xs font-medium text-gray-900 dark:text-gray-100 bg-transparent border-b border-transparent hover:border-gray-300 dark:hover:border-gray-500 focus:outline-hidden focus:border-primary"
                          />
                          {tableColumns.length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeTableColumn(index)}
                              className="text-red-500 hover:text-red-700"
                            >
                              <TrashIcon className="h-3 w-3" />
                            </button>
                          )}
                        </div>
                      </th>
                    ))}
                    {isAddingColumn ? (
                      <th className="px-2 py-1 min-w-[120px]">
                        <div className="flex items-center space-x-1">
                          <input
                            type="text"
                            value={newColumnName}
                            onChange={(e) => setNewColumnName(e.target.value)}
                            placeholder="Column name"
                            className="flex-1 text-xs font-medium text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 border border-primary rounded-sm px-2 py-1 focus:outline-hidden focus:ring-1 focus:ring-primary"
                            // eslint-disable-next-line jsx-a11y/no-autofocus
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                confirmAddColumn();
                              } else if (e.key === 'Escape') {
                                cancelAddColumn();
                              }
                            }}
                          />
                          <div className="flex space-x-1">
                            <button
                              type="button"
                              onClick={confirmAddColumn}
                              className="text-green-600 hover:text-green-700 p-1"
                              disabled={!newColumnName.trim()}
                            >
                              <CheckIcon className="h-3 w-3" />
                            </button>
                            <button
                              type="button"
                              onClick={cancelAddColumn}
                              className="text-gray-500 hover:text-gray-700 p-1"
                            >
                              <XMarkIcon className="h-3 w-3" />
                            </button>
                          </div>
                        </div>
                      </th>
                    ) : (
                      <th className="px-2 py-1">
                        <button
                          type="button"
                          onClick={addTableColumn}
                          className="flex items-center justify-center w-full text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 border border-dashed border-gray-300 dark:border-gray-600 rounded-sm px-2 py-1 hover:border-gray-400 dark:hover:border-gray-500"
                        >
                          <PlusIcon className="h-3 w-3" />
                        </button>
                      </th>
                    )}
                    <th className="w-10"></th>
                  </tr>
                  {showSchemaEditor && tableColumns.length > 0 && (
                    <tr className="bg-gray-200 dark:bg-gray-800 border-t border-gray-300 dark:border-gray-600">
                      {tableColumns.map((_, index) => (
                        <th key={index} className="px-2 py-2">
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] font-normal text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                              Type
                            </span>
                            <select
                              value={tableSchema[index]?.type || 'string'}
                              onChange={(e) =>
                                updateColumnType(index, e.target.value as ColumnSchema['type'])
                              }
                              className="w-full text-xs text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-sm px-2 py-1 focus:outline-hidden focus:ring-1 focus:ring-primary"
                            >
                              <option value="string">String</option>
                              <option value="number">Number</option>
                              <option value="boolean">Boolean</option>
                              <option value="date">Date</option>
                              <option value="datetime">DateTime</option>
                              <option value="json">JSON</option>
                            </select>
                          </div>
                        </th>
                      ))}
                      {isAddingColumn && (
                        <th className="px-2 py-2">
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] font-normal text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                              Type
                            </span>
                            <select
                              value={newColumnType}
                              onChange={(e) =>
                                setNewColumnType(e.target.value as ColumnSchema['type'])
                              }
                              className="w-full text-xs text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-sm px-2 py-1 focus:outline-hidden focus:ring-1 focus:ring-primary"
                            >
                              <option value="string">String</option>
                              <option value="number">Number</option>
                              <option value="boolean">Boolean</option>
                              <option value="date">Date</option>
                              <option value="datetime">DateTime</option>
                              <option value="json">JSON</option>
                            </select>
                          </div>
                        </th>
                      )}
                      <th></th>
                    </tr>
                  )}
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {tableData.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((cell, colIndex) =>
                        renderTableCell(
                          cell,
                          rowIndex,
                          colIndex,
                          tableSchema[colIndex]?.type || 'string'
                        )
                      )}
                      {isAddingColumn && (
                        <td className="px-2 py-1">
                          <div className="w-full h-8 bg-gray-50 dark:bg-gray-700 border border-dashed border-gray-300 dark:border-gray-600 rounded-sm flex items-center justify-center">
                            <span className="text-xs text-gray-400">New column</span>
                          </div>
                        </td>
                      )}
                      <td className="px-2 py-1">
                        {tableData.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeTableRow(rowIndex)}
                            className="text-red-500 hover:text-red-700"
                          >
                            <TrashIcon className="h-3 w-3" />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {tableData.length === 0 && (
              <div className="text-center py-4 text-sm text-gray-500 dark:text-gray-400">
                No data. Add columns and rows to build your table.
              </div>
            )}
          </div>
        );
      }

      default: {
        return null;
      }
    }
  };

  const getTypeLabel = () => {
    switch (knowledgeUnit.type) {
      case 'directive': {
        return 'Directive';
      }
      case 'table': {
        return 'Table';
      }
      case 'document': {
        return 'Document';
      }
      default: {
        return 'Knowledge Unit';
      }
    }
  };

  return (
    <>
      <Dialog open={isOpen} onClose={handleSafeClose} className="relative z-50">
        <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

        <div className="fixed inset-0 flex items-center justify-center p-4">
          <DialogPanel
            className={`mx-auto rounded-xl bg-white dark:bg-gray-800 p-6 w-full max-h-[90vh] flex flex-col ${knowledgeUnit?.type === 'table' ? 'max-w-6xl' : 'max-w-4xl'}`}
          >
            <div className="flex items-center justify-between mb-4">
              <DialogTitle className="text-lg font-medium text-gray-900 dark:text-gray-100">
                Edit {getTypeLabel()}: {knowledgeUnit.name}
              </DialogTitle>
              <button onClick={handleSafeClose} className="text-gray-400 hover:text-gray-500">
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <div className="space-y-4 flex-1 overflow-y-auto min-h-0">
              {/* Error message */}
              {saveError && (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-3">
                  <div className="flex items-start">
                    <svg
                      className="h-5 w-5 text-red-400 mt-0.5 mr-2"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    <div className="flex-1">
                      <h3 className="text-sm font-medium text-red-800 dark:text-red-200">
                        Save Failed
                      </h3>
                      <p className="mt-1 text-sm text-red-700 dark:text-red-300">{saveError}</p>
                    </div>
                    <button
                      onClick={() => setSaveError(undefined)}
                      className="ml-3 text-red-400 hover:text-red-600"
                      data-testid="dismiss-error"
                    >
                      <XMarkIcon className="h-5 w-5" />
                    </button>
                  </div>
                </div>
              )}

              {/* Basic fields */}
              <div>
                <label
                  htmlFor="ku-name"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Name
                </label>
                <input
                  id="ku-name"
                  type="text"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setIsDirty(true);
                  }}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-xs focus:outline-hidden focus:ring-primary focus:border-primary dark:bg-gray-700 dark:text-gray-300"
                  required
                />
              </div>

              <div>
                <label
                  htmlFor="ku-description"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Description
                </label>
                <textarea
                  id="ku-description"
                  value={description}
                  onChange={(e) => {
                    setDescription(e.target.value);
                    setIsDirty(true);
                  }}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md shadow-xs focus:outline-hidden focus:ring-primary focus:border-primary dark:bg-gray-700 dark:text-gray-300"
                  rows={knowledgeUnit?.type === 'table' ? 2 : 3}
                />
              </div>

              {/* Type-specific content */}
              {renderFormContent()}
            </div>

            {/* Actions - Fixed at bottom */}
            <div className="flex justify-end space-x-2 pt-4 border-t border-gray-200 dark:border-gray-700 mt-4 shrink-0">
              <button
                type="button"
                onClick={handleSafeClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600"
                disabled={isLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleSave()}
                className="px-4 py-2 text-sm font-medium text-white bg-primary rounded-md hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={
                  isLoading ||
                  !name ||
                  (knowledgeUnit.type === 'table' ? tableColumns.length === 0 : !content)
                }
              >
                {isLoading ? 'Saving...' : 'Save'}
              </button>
            </div>
          </DialogPanel>
        </div>
      </Dialog>

      {/* Discard changes confirmation dialog */}
      <ConfirmDialog
        isOpen={showDiscardConfirm}
        onClose={() => setShowDiscardConfirm(false)}
        onConfirm={handleConfirmDiscard}
        title="Discard Unsaved Changes?"
        message="You have unsaved changes. Are you sure you want to exit? All your changes will be lost."
        confirmLabel="Discard Changes"
        cancelLabel="Keep Editing"
        variant="warning"
      />
    </>
  );
};
