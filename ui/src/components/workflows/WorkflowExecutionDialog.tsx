import React, { useState, useEffect } from 'react';

import { XMarkIcon, PlayIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';

import { Workflow } from '../../types/workflow';

interface WorkflowExecutionDialogProps {
  isOpen: boolean;
  workflow: Workflow | null;
  onClose: () => void;
  onExecute: (inputData: Record<string, any>) => void;
  loading?: boolean;
}

export const WorkflowExecutionDialog: React.FC<WorkflowExecutionDialogProps> = ({
  isOpen,
  workflow,
  onClose,
  onExecute,
  loading = false,
}) => {
  const [inputData, setInputData] = useState<string>('');
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Initialize with first sample data if available, otherwise generate from schema
  /* eslint-disable react-hooks/set-state-in-effect -- Intentional initialization on open, React 18 batches these */
  useEffect(() => {
    if (!workflow || !isOpen) return;

    // Check if workflow has data_samples
    if (
      workflow.data_samples &&
      Array.isArray(workflow.data_samples) &&
      workflow.data_samples.length > 0
    ) {
      // Use the first sample data
      const firstSample = workflow.data_samples[0] as Record<string, unknown> | undefined;
      // Extract 'input' field if present (workflow data_samples use {name, input, description, expected_output} structure)
      // If no 'input' field, use the sample as-is (fallback for legacy workflows)
      const actualInput = (firstSample as any)?.input || firstSample;
      setInputData(JSON.stringify(actualInput, null, 2));
      setJsonError(null);
    } else {
      // Generate sample input data from schema as fallback
      const generateSampleInput = (schema: any): Record<string, any> => {
        if (!schema || !schema.properties) return {};

        const sampleData: Record<string, any> = {};

        for (const [key, prop] of Object.entries(schema.properties)) {
          const property = prop as any;
          switch (property.type) {
            case 'string': {
              sampleData[key] = key === 'ip' ? '192.0.2.1' : `sample_${key}`; // RFC 5737 documentation IP
              break;
            }
            case 'number':
            case 'integer': {
              sampleData[key] = 42;
              break;
            }
            case 'boolean': {
              sampleData[key] = true;
              break;
            }
            case 'array': {
              sampleData[key] = [];
              break;
            }
            case 'object': {
              sampleData[key] = {};
              break;
            }
            default: {
              sampleData[key] = null;
            }
          }
        }

        return sampleData;
      };

      const sampleInput = generateSampleInput(workflow.io_schema.input);
      setInputData(JSON.stringify(sampleInput, null, 2));
      setJsonError(null);
    }
  }, [workflow, isOpen]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const handleInputChange = (value: string) => {
    setInputData(value);

    // Validate JSON
    try {
      JSON.parse(value);
      setJsonError(null);
    } catch (error) {
      setJsonError(error instanceof Error ? error.message : 'Invalid JSON');
    }
  };

  const handleExecute = () => {
    if (!workflow || jsonError || loading) return;

    try {
      const parsedInput = JSON.parse(inputData);
      onExecute(parsedInput);
    } catch (error) {
      setJsonError(error instanceof Error ? error.message : 'Invalid JSON');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose();
    } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      handleExecute();
    }
  };

  // Schema documentation helper
  const renderSchemaInfo = (schema: any) => {
    if (!schema || !schema.properties) {
      return <div className="text-gray-500 text-sm">No schema information available</div>;
    }

    return (
      <div className="space-y-2">
        {Object.entries(schema.properties).map(([key, prop]) => {
          const property = prop as any;
          const isRequired = schema.required?.includes(key);

          return (
            <div key={key} className="flex items-start space-x-3">
              <div className="shrink-0">
                <span
                  className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                    isRequired
                      ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300'
                      : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                  }`}
                >
                  {property.type}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center space-x-2">
                  <span className="font-medium text-sm text-gray-900 dark:text-gray-100">
                    {key}
                  </span>
                  {isRequired && <span className="text-red-500 text-xs">required</span>}
                </div>
                {property.description && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {property.description}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  if (!isOpen || !workflow) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        {/* Backdrop */}
        <div
          role="button"
          tabIndex={0}
          aria-label="Close dialog"
          className="fixed inset-0 bg-black bg-opacity-25 transition-opacity"
          onClick={onClose}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') onClose();
          }}
        />

        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- Dialog needs onKeyDown for Escape handling */}
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Execute Workflow"
          className="relative w-full max-w-4xl bg-white dark:bg-gray-800 rounded-lg shadow-xl"
          onKeyDown={handleKeyDown}
          tabIndex={-1}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center space-x-3">
              <div className="shrink-0">
                <PlayIcon className="h-6 w-6 text-primary" />
              </div>
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
                  Execute Workflow
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">{workflow.name}</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="rounded-md text-gray-400 hover:text-gray-500 focus:outline-hidden focus:ring-2 focus:ring-primary"
              disabled={loading}
            >
              <XMarkIcon className="h-6 w-6" />
            </button>
          </div>

          {/* Content */}
          <div className="p-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Input Data Editor */}
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label
                      htmlFor="workflow-input-json"
                      className="block text-sm font-medium text-gray-700 dark:text-gray-300"
                    >
                      Input Data (JSON)
                    </label>
                    {/* Sample Data Selector */}
                    {workflow.data_samples &&
                      Array.isArray(workflow.data_samples) &&
                      workflow.data_samples.length > 0 && (
                        <select
                          defaultValue="0"
                          onChange={(e) => {
                            const index = Number.parseInt(e.target.value);
                            if (
                              index >= 0 &&
                              workflow.data_samples &&
                              index < workflow.data_samples.length
                            ) {
                              const sample = workflow.data_samples[index] as Record<
                                string,
                                unknown
                              >;
                              // Extract 'input' field if present (workflow data_samples use {name, input, description, expected_output} structure)
                              // If no 'input' field, use the sample as-is (fallback for legacy workflows)
                              const actualInput = (sample as any)?.input || sample;
                              setInputData(JSON.stringify(actualInput, null, 2));
                              setJsonError(null);
                            } else if (e.target.value === '') {
                              // Clear option selected
                              setInputData('{}');
                              setJsonError(null);
                            }
                          }}
                          className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                          disabled={loading}
                        >
                          <option value="">Clear input</option>
                          {workflow.data_samples.map((rawSample: unknown, index: number) => {
                            // Try to create a descriptive label for each sample
                            const sample = rawSample as Record<string, unknown>;
                            const label =
                              sample.context || sample.name || sample.ip || `Example ${index + 1}`;
                            return (
                              <option key={index} value={index}>
                                {typeof label === 'string' ? label : `Example ${index + 1}`}
                              </option>
                            );
                          })}
                        </select>
                      )}
                  </div>
                  <div className="relative">
                    <textarea
                      id="workflow-input-json"
                      value={inputData}
                      onChange={(e) => handleInputChange(e.target.value)}
                      className={`w-full h-64 px-3 py-2 border rounded-md font-mono text-sm focus:outline-hidden focus:ring-2 focus:ring-primary ${
                        jsonError
                          ? 'border-red-300 dark:border-red-600'
                          : 'border-gray-300 dark:border-gray-600'
                      } bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100`}
                      placeholder="Enter JSON input data..."
                      disabled={loading}
                    />
                    {jsonError && (
                      <div className="absolute -bottom-6 left-0 flex items-center space-x-1 text-red-500 text-xs">
                        <ExclamationTriangleIcon className="h-4 w-4" />
                        <span>{jsonError}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Schema Information */}
              <div className="space-y-4">
                <div>
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                    Expected Input Schema
                  </h4>
                  <div className="bg-gray-50 dark:bg-gray-900 rounded-md p-4 max-h-64 overflow-y-auto">
                    {renderSchemaInfo(workflow.io_schema.input)}
                  </div>
                </div>

                {/* Workflow Info */}
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-md p-4">
                  <h4 className="text-sm font-medium text-blue-900 dark:text-blue-300 mb-2">
                    Workflow Information
                  </h4>
                  <div className="space-y-1 text-xs text-blue-700 dark:text-blue-400">
                    <div>Description: {workflow.description}</div>
                    <div>Nodes: {workflow.nodes.length}</div>
                    <div>Edges: {workflow.edges.length}</div>
                    <div>Type: {workflow.is_dynamic ? 'Dynamic' : 'Static'}</div>
                    <div>Created by: {workflow.created_by}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between p-6 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 rounded-b-lg">
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Press Ctrl+Enter to execute, Esc to cancel
            </div>
            <div className="flex items-center space-x-3">
              <button
                onClick={onClose}
                className="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary"
                disabled={loading}
              >
                Cancel
              </button>
              <button
                onClick={handleExecute}
                disabled={!!jsonError || loading || !inputData.trim()}
                className="px-4 py-2 bg-primary text-white rounded-md text-sm font-medium hover:bg-primary/90 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
              >
                {loading && (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                )}
                <PlayIcon className="h-4 w-4" />
                <span>{loading ? 'Starting...' : 'Start Execution'}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
