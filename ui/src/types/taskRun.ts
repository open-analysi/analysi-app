export type { LLMUsage, TaskBuildingRun, TaskBuildingRunStatus } from './api';

import type {
  TaskRun as GeneratedTaskRun,
  LLMUsage,
  TaskBuildingRun,
  TaskBuildingRunStatus,
} from './api';

/**
 * TaskRun extends the generated type with legacy fields that the API may still
 * return and that the UI accesses (input, output, error). These fields are not
 * part of the OpenAPI spec but appear in older API responses.
 */
export type TaskRun = GeneratedTaskRun & {
  input?: string;
  output?: string;
  error?: string;
};

export interface TaskRunsResponse {
  execution_time: number;
  task_runs: TaskRun[];
}

export interface TaskRunsUIResponse {
  items: TaskRun[];
  total: number;
  skip: number;
  limit: number;
}

export interface TaskRunFilters {
  search?: string;
  status?: string;
  sort?: string;
  order?: 'asc' | 'desc';
  skip?: number;
  limit?: number;
  workflow_run_id?: string;
  alert_id?: string;
}

export interface WorkflowRun {
  id: string;
  tenant_id: string;
  workflow_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'paused';
  created_at: string;
  started_at?: string;
  completed_at?: string;
  input_data?: unknown; // Direct input data object
  output_data?: unknown; // Direct output data object
  error_message?: string;
  updated_at?: string;
  workflow_name?: string; // From joined workflow data
  duration?: number | string;
  progress?: number;
  execution_context?: Record<string, any>;
  llm_usage?: LLMUsage | null;
}

export interface WorkflowRunsResponse {
  execution_time: number;
  workflow_runs: WorkflowRun[];
}

export interface WorkflowRunsUIResponse {
  items: WorkflowRun[];
  total: number;
  skip: number;
  limit: number;
}

export interface WorkflowRunFilters {
  search?: string;
  status?: string;
  workflow_id?: string;
  sort?: string;
  order?: 'asc' | 'desc';
  skip?: number;
  limit?: number;
}

export type ExecutionType = 'tasks' | 'workflows' | 'task-building';

export interface TaskBuildingRunsResponse {
  execution_time: number;
  task_building_runs: TaskBuildingRun[];
  total: number;
}

export interface TaskBuildingRunFilters {
  workflow_generation_id?: string;
  status?: string;
  sort?: string;
  order?: 'asc' | 'desc';
  offset?: number;
  limit?: number;
}

// Task Generation API (standalone task building via AI)
export interface TaskGenerationRequest {
  description: string;
  alert_id?: string;
}

export interface TaskGenerationResponse {
  id: string;
  status: TaskBuildingRunStatus;
  description: string;
  alert_id?: string | null;
  created_at: string;
}

export interface TaskGenerationProgressMessage {
  timestamp: string;
  message: string;
  level: 'info' | 'warning' | 'error';
  details?: Record<string, unknown>;
}
