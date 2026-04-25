/**
 * WorkflowBuilderProperties - Properties panel for selected nodes/edges
 *
 * Shows workflow settings when nothing selected, or element properties when selected.
 */
/* eslint-disable jsx-a11y/label-has-associated-control */
/* eslint-disable sonarjs/cognitive-complexity */
/* eslint-disable sonarjs/no-nested-conditional */
import React, { useEffect, useState } from 'react';

import {
  CubeTransparentIcon,
  CodeBracketIcon,
  ArrowPathIcon,
  TrashIcon,
  PlusIcon,
  DocumentTextIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  XMarkIcon,
  PencilIcon,
  CheckIcon,
} from '@heroicons/react/24/outline';

import { backendApi } from '../../../services/backendApi';
import { useWorkflowBuilderStore } from '../../../store/workflowBuilderStore';
import type { Alert } from '../../../types/alert';
import type { Task } from '../../../types/knowledge';

interface WorkflowBuilderPropertiesProps {
  className?: string;
}

/**
 * Get icon for node kind
 */
// eslint-disable-next-line sonarjs/function-return-type -- returns different JSX icons based on kind
function getNodeKindIcon(kind: string): React.ReactNode {
  const iconClass = 'h-5 w-5';
  switch (kind) {
    case 'task':
      return <CubeTransparentIcon className={iconClass} />;
    case 'foreach':
      return <ArrowPathIcon className={iconClass} />;
    case 'transformation':
    default:
      return <CodeBracketIcon className={iconClass} />;
  }
}

/**
 * Get label for node kind
 */
function getNodeKindLabel(kind: string): string {
  switch (kind) {
    case 'task':
      return 'Task Node';
    case 'foreach':
      return 'ForEach Loop';
    case 'transformation':
      return 'Transformation';
    default:
      return 'Node';
  }
}

/**
 * Get color class for node kind
 */
function getNodeKindColor(kind: string): string {
  switch (kind) {
    case 'task':
      return 'text-blue-400';
    case 'foreach':
      return 'text-orange-400';
    case 'transformation':
      return 'text-green-400';
    default:
      return 'text-gray-400';
  }
}

/**
 * Workflow Settings Panel - shown when nothing is selected
 */
const WorkflowSettingsPanel: React.FC<{ className?: string }> = ({ className = '' }) => {
  const store = useWorkflowBuilderStore();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loadingAlerts, setLoadingAlerts] = useState(false);
  const [showAlertPicker, setShowAlertPicker] = useState(false);
  const [showJsonInput, setShowJsonInput] = useState(false);
  const [jsonInput, setJsonInput] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [expandedSamples, setExpandedSamples] = useState<Set<number>>(new Set());
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [editValue, setEditValue] = useState('');
  const [editError, setEditError] = useState<string | null>(null);

  // Fetch alerts when picker is opened
  useEffect(() => {
    if (showAlertPicker && alerts.length === 0) {
      const fetchAlerts = async () => {
        setLoadingAlerts(true);
        try {
          const response = await backendApi.getAlerts({ limit: 50 });
          setAlerts(response.alerts);
        } catch (error) {
          console.error('Failed to fetch alerts:', error);
        } finally {
          setLoadingAlerts(false);
        }
      };
      void fetchAlerts();
    }
  }, [showAlertPicker, alerts.length]);

  // Handle adding an alert as a data sample
  const handleAddAlertSample = (alert: Alert) => {
    store.addDataSample(alert);
    setShowAlertPicker(false);
  };

  // Handle adding JSON manually
  const handleAddJsonSample = () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
      const parsed = JSON.parse(jsonInput);
      store.addDataSample(parsed);
      setJsonInput('');
      setJsonError(null);
      setShowJsonInput(false);
    } catch {
      // JSON parsing failed - show user-friendly error
      setJsonError('Invalid JSON format');
    }
  };

  // Toggle sample expansion
  const toggleSampleExpansion = (index: number) => {
    setExpandedSamples((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  // Start editing a sample
  const startEditing = (index: number) => {
    const sample = store.dataSamples[index];
    setEditingIndex(index);
    setEditValue(JSON.stringify(sample, null, 2));
    setEditError(null);
  };

  // Save edited sample
  const saveEdit = () => {
    if (editingIndex === null) return;
    try {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
      const parsed = JSON.parse(editValue);
      store.updateDataSample(editingIndex, parsed);
      setEditingIndex(null);
      setEditValue('');
      setEditError(null);
    } catch {
      // JSON parsing failed
      setEditError('Invalid JSON format');
    }
  };

  // Cancel editing
  const cancelEdit = () => {
    setEditingIndex(null);
    setEditValue('');
    setEditError(null);
  };

  return (
    <div className={`p-4 space-y-6 ${className}`}>
      {/* Header */}
      <div className="flex items-center space-x-2 text-gray-300">
        <DocumentTextIcon className="h-5 w-5" />
        <span className="text-sm font-medium">Workflow Settings</span>
      </div>

      {/* Workflow Name - Prominent */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">Workflow Name</label>
        <input
          type="text"
          value={store.workflowName}
          onChange={(e) => store.setWorkflowName(e.target.value)}
          placeholder="Enter workflow name..."
          className="w-full px-4 py-3 text-base bg-dark-700 border border-gray-500 rounded-lg text-white placeholder-gray-500 focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-primary"
        />
      </div>

      {/* Workflow Description */}
      <div>
        <label className="block text-xs font-medium text-gray-400 mb-1">Description</label>
        <textarea
          value={store.workflowDescription}
          onChange={(e) => store.setWorkflowDescription(e.target.value)}
          placeholder="Describe what this workflow does..."
          rows={3}
          className="w-full px-3 py-2 text-sm bg-dark-700 border border-gray-600 rounded-sm text-white placeholder-gray-500 focus:outline-hidden focus:ring-1 focus:ring-primary resize-none"
        />
      </div>

      {/* Data Samples Section */}
      <div className="border-t border-gray-700 pt-4">
        <div className="flex items-center justify-between mb-3">
          <label className="block text-xs font-medium text-gray-400">
            Data Samples ({store.dataSamples.length})
          </label>
          <div className="flex space-x-1">
            <button
              onClick={() => setShowAlertPicker(!showAlertPicker)}
              className="p-1.5 text-gray-400 hover:text-primary hover:bg-dark-600 rounded-sm"
              title="Add from existing alerts"
            >
              <PlusIcon className="h-4 w-4" />
            </button>
            <button
              onClick={() => setShowJsonInput(!showJsonInput)}
              className="p-1.5 text-gray-400 hover:text-primary hover:bg-dark-600 rounded-sm"
              title="Add JSON manually"
            >
              <CodeBracketIcon className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Alert Picker */}
        {showAlertPicker && (
          <div className="mb-3 bg-dark-800 border border-gray-600 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-300">Select an Alert</span>
              <button
                onClick={() => setShowAlertPicker(false)}
                className="text-gray-500 hover:text-gray-300"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
            {loadingAlerts ? (
              <div className="text-center py-4">
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-primary mx-auto"></div>
              </div>
            ) : alerts.length === 0 ? (
              <p className="text-xs text-gray-500 py-2">No alerts available</p>
            ) : (
              <div className="max-h-48 overflow-y-auto space-y-1">
                {alerts.map((alert) => (
                  <button
                    key={alert.alert_id}
                    onClick={() => handleAddAlertSample(alert)}
                    className="w-full text-left px-2 py-1.5 text-xs bg-dark-700 hover:bg-dark-600 rounded-sm text-gray-300 truncate"
                  >
                    {alert.title || `Alert ${alert.alert_id.slice(0, 8)}`}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* JSON Input */}
        {showJsonInput && (
          <div className="mb-3 bg-dark-800 border border-gray-600 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-gray-300">Add JSON Sample</span>
              <button
                onClick={() => {
                  setShowJsonInput(false);
                  setJsonError(null);
                }}
                className="text-gray-500 hover:text-gray-300"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
            <textarea
              value={jsonInput}
              onChange={(e) => {
                setJsonInput(e.target.value);
                setJsonError(null);
              }}
              placeholder='{"key": "value"}'
              rows={4}
              className="w-full px-2 py-1.5 text-xs font-mono bg-dark-700 border border-gray-600 rounded-sm text-white placeholder-gray-500 focus:outline-hidden focus:ring-1 focus:ring-primary resize-none"
            />
            {jsonError && <p className="text-xs text-red-400 mt-1">{jsonError}</p>}
            <button
              onClick={handleAddJsonSample}
              disabled={!jsonInput.trim()}
              className="mt-2 w-full px-3 py-1.5 text-xs bg-primary hover:bg-primary-dark text-white rounded-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Add Sample
            </button>
          </div>
        )}

        {/* Current Samples List */}
        {store.dataSamples.length === 0 ? (
          <p className="text-xs text-gray-500 italic">
            No data samples yet. Add alerts or JSON to test the workflow.
          </p>
        ) : (
          <div className="space-y-2">
            {store.dataSamples.map((sample, index) => {
              const isEditing = editingIndex === index;
              const isExpanded = expandedSamples.has(index);
              const sampleStr = JSON.stringify(sample, null, 2);
              const preview = JSON.stringify(sample).slice(0, 50);
              const sampleTitle =
                (sample as { title?: string })?.title ||
                (sample as { name?: string })?.name ||
                `Sample ${index + 1}`;

              return (
                <div
                  key={index}
                  className={`bg-dark-700 border rounded-sm p-2 ${isEditing ? 'border-primary' : 'border-gray-600'}`}
                >
                  {isEditing ? (
                    // Edit mode
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-gray-300">Editing Sample</span>
                        <div className="flex space-x-1">
                          <button
                            onClick={saveEdit}
                            className="p-1 text-green-400 hover:text-green-300 hover:bg-green-900/20 rounded-sm"
                            title="Save changes"
                          >
                            <CheckIcon className="h-3 w-3" />
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="p-1 text-gray-400 hover:text-gray-300 hover:bg-gray-700 rounded-sm"
                            title="Cancel"
                          >
                            <XMarkIcon className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                      <textarea
                        value={editValue}
                        onChange={(e) => {
                          setEditValue(e.target.value);
                          setEditError(null);
                        }}
                        rows={8}
                        className="w-full px-2 py-1.5 text-xs font-mono bg-dark-800 border border-gray-600 rounded-sm text-white placeholder-gray-500 focus:outline-hidden focus:ring-1 focus:ring-primary resize-none"
                      />
                      {editError && <p className="text-xs text-red-400">{editError}</p>}
                    </div>
                  ) : (
                    // View mode
                    <>
                      <div className="flex items-center justify-between">
                        <button
                          onClick={() => toggleSampleExpansion(index)}
                          className="flex items-center space-x-1 text-xs text-gray-300 hover:text-white flex-1 text-left"
                        >
                          {isExpanded ? (
                            <ChevronDownIcon className="h-3 w-3" />
                          ) : (
                            <ChevronRightIcon className="h-3 w-3" />
                          )}
                          <span className="truncate">{sampleTitle}</span>
                        </button>
                        <div className="flex space-x-1">
                          <button
                            onClick={() => startEditing(index)}
                            className="p-1 text-gray-400 hover:text-primary hover:bg-dark-600 rounded-sm"
                            title="Edit sample"
                          >
                            <PencilIcon className="h-3 w-3" />
                          </button>
                          <button
                            onClick={() => store.removeDataSample(index)}
                            className="p-1 text-red-400 hover:text-red-300 hover:bg-red-900/20 rounded-sm"
                            title="Remove sample"
                          >
                            <XMarkIcon className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                      {isExpanded ? (
                        <pre className="mt-2 text-xs text-gray-400 overflow-auto max-h-32 bg-dark-800 rounded-sm p-2">
                          {sampleStr}
                        </pre>
                      ) : (
                        <p className="mt-1 text-xs text-gray-500 truncate font-mono">
                          {preview}...
                        </p>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export const WorkflowBuilderProperties: React.FC<WorkflowBuilderPropertiesProps> = ({
  className = '',
}) => {
  const store = useWorkflowBuilderStore();
  const [tasks, setTasks] = useState<Map<string, Task>>(new Map());
  const [loadingTasks, setLoadingTasks] = useState(false);

  // Get the first selected item
  const selectedId = store.selections[0];

  // Find the selected node or edge
  const selectedNode = selectedId ? store.nodes.find((n) => n.id === selectedId) : undefined;
  const selectedEdge = selectedId ? store.edges.find((e) => e.id === selectedId) : undefined;

  // Fetch task details when a task node is selected
  useEffect(() => {
    const fetchTaskDetails = async () => {
      if (selectedNode?.taskId && !tasks.has(selectedNode.taskId)) {
        setLoadingTasks(true);
        try {
          const task = await backendApi.getTask(selectedNode.taskId);
          setTasks((prev) => new Map(prev).set(selectedNode.taskId!, task));
        } catch (error) {
          console.error('Failed to fetch task:', error);
        } finally {
          setLoadingTasks(false);
        }
      }
    };

    void fetchTaskDetails();
  }, [selectedNode?.taskId, tasks]);

  // Handle node name change
  const handleNameChange = (newName: string) => {
    if (selectedNode) {
      store.updateNode(selectedNode.id, { text: newName });
    }
  };

  // Handle edge label change
  const handleEdgeLabelChange = (newLabel: string) => {
    if (selectedEdge) {
      store.updateEdge(selectedEdge.id, { text: newLabel });
    }
  };

  // Handle delete
  const handleDelete = () => {
    if (selectedNode) {
      store.removeNode(selectedNode.id);
    } else if (selectedEdge) {
      store.removeEdge(selectedEdge.id);
    }
  };

  // Workflow settings when nothing selected
  if (!selectedId) {
    return <WorkflowSettingsPanel className={className} />;
  }

  // Edge properties
  if (selectedEdge) {
    const fromNode = store.nodes.find((n) => n.id === selectedEdge.from);
    const toNode = store.nodes.find((n) => n.id === selectedEdge.to);

    return (
      <div className={`p-4 space-y-4 ${className}`}>
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="text-purple-400">→</span>
            <span className="text-sm font-medium text-white">Edge</span>
          </div>
          <button
            onClick={handleDelete}
            className="p-1.5 text-red-400 hover:text-red-300 hover:bg-red-900/20 rounded-sm"
            title="Delete edge"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>

        {/* Connection */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">Connection</label>
          <div className="text-sm text-gray-300 bg-dark-700 rounded-sm p-2">
            <div className="flex items-center space-x-2">
              <span className="truncate">{fromNode?.text || 'Unknown'}</span>
              <span className="text-purple-400">→</span>
              <span className="truncate">{toNode?.text || 'Unknown'}</span>
            </div>
          </div>
        </div>

        {/* Edge Label */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">Label (optional)</label>
          <input
            type="text"
            value={selectedEdge.text || ''}
            onChange={(e) => handleEdgeLabelChange(e.target.value)}
            placeholder="Edge label..."
            className="w-full px-3 py-2 text-sm bg-dark-700 border border-gray-600 rounded-sm text-white placeholder-gray-500 focus:outline-hidden focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>
    );
  }

  // Node properties
  if (selectedNode) {
    const task = selectedNode.taskId ? tasks.get(selectedNode.taskId) : undefined;

    return (
      <div className={`p-4 space-y-4 ${className}`}>
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className={`flex items-center space-x-2 ${getNodeKindColor(selectedNode.kind)}`}>
            {getNodeKindIcon(selectedNode.kind)}
            <span className="text-sm font-medium">{getNodeKindLabel(selectedNode.kind)}</span>
          </div>
          <button
            onClick={handleDelete}
            className="p-1.5 text-red-400 hover:text-red-300 hover:bg-red-900/20 rounded-sm"
            title="Delete node"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>

        {/* Node Name */}
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1">Name</label>
          <input
            type="text"
            value={selectedNode.text}
            onChange={(e) => handleNameChange(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-dark-700 border border-gray-600 rounded-sm text-white placeholder-gray-500 focus:outline-hidden focus:ring-1 focus:ring-primary"
          />
        </div>

        {/* Task-specific properties */}
        {selectedNode.kind === 'task' && (
          <>
            {loadingTasks ? (
              <div className="text-center py-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary mx-auto"></div>
              </div>
            ) : task ? (
              <>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">Task</label>
                  <div className="text-sm text-gray-300 bg-dark-700 rounded-sm p-2">
                    {task.name}
                  </div>
                </div>
                {task.description && (
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">
                      Description
                    </label>
                    <div className="text-sm text-gray-400 bg-dark-700 rounded-sm p-2">
                      {task.description}
                    </div>
                  </div>
                )}
                {task.function && (
                  <div>
                    <label className="block text-xs font-medium text-gray-400 mb-1">Function</label>
                    <div className="text-xs text-gray-400 bg-dark-700 rounded-sm p-2 font-mono">
                      {task.function}
                    </div>
                  </div>
                )}
              </>
            ) : selectedNode.taskId ? (
              <div className="text-sm text-gray-500">Task not found: {selectedNode.taskId}</div>
            ) : (
              <div className="text-sm text-yellow-500">No task assigned</div>
            )}
          </>
        )}

        {/* Transformation-specific properties */}
        {selectedNode.kind === 'transformation' && (
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Template</label>
            <div className="text-sm text-gray-300 bg-dark-700 rounded-sm p-2 capitalize">
              {selectedNode.nodeTemplateId || 'Custom'}
            </div>
          </div>
        )}

        {/* ForEach-specific properties */}
        {selectedNode.kind === 'foreach' && (
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">
              Loop Configuration
            </label>
            <div className="text-sm text-gray-400 bg-dark-700 rounded-sm p-2">
              {selectedNode.foreachConfig ? (
                <pre className="text-xs overflow-auto">
                  {JSON.stringify(selectedNode.foreachConfig, null, 2)}
                </pre>
              ) : (
                <span className="text-gray-500 italic">No configuration</span>
              )}
            </div>
          </div>
        )}

        {/* Node ID (debug info) */}
        <div className="pt-4 border-t border-gray-700">
          <label className="block text-xs font-medium text-gray-500 mb-1">Node ID</label>
          <div className="text-xs text-gray-600 font-mono truncate" title={selectedNode.id}>
            {selectedNode.id}
          </div>
        </div>
      </div>
    );
  }

  // Fallback - shouldn't reach here
  return (
    <div className={`p-4 ${className}`}>
      <p className="text-sm text-gray-400">Unknown selection type</p>
    </div>
  );
};

export default WorkflowBuilderProperties;
