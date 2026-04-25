// Workflow types — re-exports from generated types + UI-only types

// Re-export API types from generated types (single source of truth)
export type {
  WorkflowNode,
  WorkflowEdge,
  Workflow,
  WorkflowNodeInstance,
  WorkflowEdgeInstance,
  WorkflowRunStatus,
} from './api';

export type { LLMUsage as WorkflowLLMUsage } from './api';

// ---- UI-only types below (no generated counterpart) ----

import type {
  WorkflowNode,
  WorkflowEdge,
  WorkflowNodeInstance,
  WorkflowEdgeInstance,
  Workflow,
} from './api';

export interface WorkflowsResponse {
  workflows: Workflow[];
  total: number;
}

export interface WorkflowQueryParams {
  search?: string;
  created_by?: string;
  is_dynamic?: boolean;
  page?: number;
  page_size?: number;
  sort?: string;
  order?: 'asc' | 'desc';
}

export type WorkflowNodeStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'paused';

export interface WorkflowRunRequest {
  input_data: Record<string, any>;
}

// Service-layer response for initiating a workflow run (not the full run details)
export interface WorkflowRunInitiatedResponse {
  workflow_run_id: string;
  status: string;
  message: string;
}

export interface WorkflowExecutionSummary {
  pending: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface WorkflowExecutionGraph {
  workflow_run_id: string;
  is_complete: boolean; // True when execution finished
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'paused'; // Overall workflow run status
  snapshot_at: string; // Timestamp for incremental updates
  summary: WorkflowExecutionSummary;
  nodes: WorkflowNodeInstance[];
  edges: WorkflowEdgeInstance[];
}

export interface WorkflowRun {
  id?: string; // Alias for workflow_run_id (for backward compatibility)
  workflow_run_id: string;
  workflow_id: string;
  workflow_name?: string;
  status: WorkflowNodeStatus;
  input_data: Record<string, any>;
  output_data?: Record<string, any>;
  error_message?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
  duration?: number;
  progress?: number;
  execution_context?: Record<string, any>;
  llm_usage?: import('./api').LLMUsage | null;
}

export interface WorkflowRunsResponse {
  workflow_runs: WorkflowRun[];
  total: number;
}

// Local kind type for UI usage (generated WorkflowNode has `kind: string`)
export type WorkflowNodeKind = 'task' | 'transformation' | 'foreach';

// UI-specific types for visualization

export interface CytoscapeNode {
  data: {
    id: string;
    label: string;
    kind: WorkflowNodeKind;
    status?: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'paused';
    nodeData: WorkflowNode | WorkflowNodeInstance;
  };
  position?: { x: number; y: number };
}

export interface CytoscapeEdge {
  data: {
    id: string;
    source: string;
    target: string;
    label?: string;
    edgeData: WorkflowEdge | WorkflowEdgeInstance;
  };
}

export interface CytoscapeElements {
  nodes: CytoscapeNode[];
  edges: CytoscapeEdge[];
}

// Status color scheme constants
export const STATUS_COLORS = {
  pending: '#6B7280', // Gray
  running: '#3B82F6', // Blue
  completed: '#10B981', // Green
  failed: '#EF4444', // Red
  cancelled: '#F59E0B', // Amber
} as const;

export const NODE_KIND_COLORS = {
  task: '#1E40AF', // Dark blue
  transformation: '#059669', // Dark green
  foreach: '#D97706', // Dark orange
} as const;
