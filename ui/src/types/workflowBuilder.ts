/**
 * Workflow Builder Types
 *
 * Types specific to the workflow builder UI, including canvas nodes/edges
 * that extend the base workflow types with UI-specific properties.
 */

import type { WorkflowNode, WorkflowEdge, Workflow } from './workflow';

/**
 * Canvas node data for Reaflow
 * Structure-first approach: ELK handles all positioning automatically
 */
export interface CanvasNodeData {
  id: string;
  text: string;
  kind: WorkflowNode['kind'];
  taskId?: string;
  nodeTemplateId?: string;
  foreachConfig?: Record<string, unknown>;
  // Description for hover tooltip
  description?: string;
  // Original workflow node reference (for edit mode)
  workflowNode?: WorkflowNode;
}

/**
 * Canvas edge data for Reaflow
 */
export interface CanvasEdgeData {
  id: string;
  from: string;
  to: string;
  text?: string;
  // Original workflow edge reference (for edit mode)
  workflowEdge?: WorkflowEdge;
}

/**
 * Node template for palette items
 */
export interface NodeTemplate {
  id: string;
  name: string;
  kind: WorkflowNode['kind'];
  description?: string;
  icon?: string;
  // For task nodes
  taskId?: string;
  taskName?: string;
  // For transformation nodes
  templateId?: string;
  templateCode?: string;
}

/**
 * Transformation template types
 */
export type TransformationType = 'identity' | 'merge' | 'collect' | 'custom';

/**
 * Predefined transformation templates
 */
export const TRANSFORMATION_TEMPLATES: NodeTemplate[] = [
  {
    id: 'transform-identity',
    name: 'Identity',
    kind: 'transformation',
    description: 'Pass data through unchanged',
    templateId: 'identity',
    icon: 'arrow-right',
  },
  {
    id: 'transform-merge',
    name: 'Merge',
    kind: 'transformation',
    description: 'Combine multiple inputs into one',
    templateId: 'merge',
    icon: 'arrows-pointing-in',
  },
  {
    id: 'transform-collect',
    name: 'Collect',
    kind: 'transformation',
    description: 'Aggregate results from parallel branches',
    templateId: 'collect',
    icon: 'rectangle-stack',
  },
];

/**
 * ForEach node template
 */
export const FOREACH_TEMPLATE: NodeTemplate = {
  id: 'foreach',
  name: 'ForEach',
  kind: 'foreach',
  description: 'Iterate over a collection',
  icon: 'arrow-path',
};

/**
 * History entry for undo/redo
 */
export interface HistoryEntry {
  nodes: CanvasNodeData[];
  edges: CanvasEdgeData[];
  timestamp: number;
}

/**
 * Workflow builder store state
 */
export interface WorkflowBuilderState {
  // Workflow metadata
  workflowId: string | null;
  workflowName: string;
  workflowDescription: string;
  isDynamic: boolean;
  dataSamples: unknown[];

  // Canvas state
  nodes: CanvasNodeData[];
  edges: CanvasEdgeData[];
  selections: string[];

  // UI state
  isDirty: boolean;
  draftTimestamp: number | null; // When the draft was last modified
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;

  // History for undo/redo
  history: HistoryEntry[];
  historyIndex: number;
}

/**
 * Workflow builder store actions
 */
export interface WorkflowBuilderActions {
  // Node operations
  addNode: (node: CanvasNodeData, autoConnect?: boolean) => void;
  removeNode: (nodeId: string) => void;
  updateNode: (nodeId: string, updates: Partial<CanvasNodeData>) => void;

  // Edge operations
  addEdge: (fromId: string, toId: string, label?: string) => void;
  removeEdge: (edgeId: string) => void;
  updateEdge: (edgeId: string, updates: Partial<CanvasEdgeData>) => void;

  // Selection
  setSelections: (ids: string[]) => void;
  clearSelections: () => void;

  // Workflow metadata
  setWorkflowName: (name: string) => void;
  setWorkflowDescription: (description: string) => void;

  // Data samples
  addDataSample: (sample: unknown) => void;
  removeDataSample: (index: number) => void;
  updateDataSample: (index: number, sample: unknown) => void;
  setDataSamples: (samples: unknown[]) => void;

  // Persistence
  newWorkflow: () => void;
  loadWorkflow: (workflow: Workflow) => void;
  saveWorkflow: () => Promise<Workflow | null>;

  // History
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
  pushHistory: () => void;

  // Reset
  reset: () => void;
}

/**
 * Full workflow builder store type
 */
export type WorkflowBuilderStore = WorkflowBuilderState & WorkflowBuilderActions;

/**
 * Convert canvas data to workflow format for saving
 */
export interface WorkflowSaveData {
  name: string;
  description: string;
  is_dynamic: boolean;
  io_schema: {
    input: Record<string, unknown>;
    output: Record<string, unknown>;
  };
  nodes: Array<{
    node_id: string;
    kind: WorkflowNode['kind'];
    name: string;
    task_id?: string;
    node_template_id?: string;
    foreach_config?: Record<string, unknown>;
    template_code?: string;
  }>;
  edges: Array<{
    edge_id: string;
    from_node_id: string;
    to_node_id: string;
    alias?: string;
  }>;
}
