import { KnowledgeUnit, Task, TaskQueryParams } from '../types/knowledge';
import { TaskRun, TaskBuildingRun } from '../types/taskRun';

import {
  withApi,
  fetchOne,
  fetchList,
  mutateOne,
  apiDelete,
  backendApiClient,
  type SifnosEnvelope,
} from './apiClient';

// Tasks
export const getTasks = (params: TaskQueryParams = {}): Promise<{ tasks: Task[]; total: number }> =>
  fetchList<'tasks', Task>('/tasks', 'tasks', { params });

export const getTaskRuns = (
  params: Record<string, unknown> = {}
): Promise<{ task_runs: TaskRun[]; total: number }> =>
  fetchList<'task_runs', TaskRun>('/task-runs', 'task_runs', { params });

export const getTaskRunHistory = (
  taskId: string,
  limit: number = 5
): Promise<{ task_runs: TaskRun[]; total: number }> =>
  fetchList<'task_runs', TaskRun>('/task-runs', 'task_runs', {
    params: {
      task_id: taskId,
      limit,
      sort: 'created_at',
      order: 'desc',
      status: 'completed',
    },
  });

export const getTaskBuildingRuns = (
  params: Record<string, unknown> = {}
): Promise<{ task_building_runs: TaskBuildingRun[]; total: number }> =>
  fetchList<'task_building_runs', TaskBuildingRun>(
    '/task-generations-internal',
    'task_building_runs',
    { params }
  );

export const getTaskBuildingRun = (runId: string): Promise<TaskBuildingRun> =>
  fetchOne<TaskBuildingRun>(`/task-generations-internal/${runId}`);

// Task Generation API (standalone AI-powered task building)
export const createTaskGeneration = (request: {
  description: string;
  alert_id?: string;
}): Promise<{
  id: string;
  status: string;
  description: string;
  alert_id?: string;
  created_at: string;
}> =>
  mutateOne<{
    id: string;
    status: string;
    description: string;
    alert_id?: string;
    created_at: string;
  }>('post', '/task-generations', request);

export const getTaskGeneration = (generationId: string): Promise<TaskBuildingRun> =>
  fetchOne<TaskBuildingRun>(`/task-generations/${generationId}`);

export const listTaskGenerations = (
  params: { limit?: number; offset?: number } = {}
): Promise<{ task_building_runs: TaskBuildingRun[]; total: number }> =>
  fetchList<'task_building_runs', TaskBuildingRun>('/task-generations', 'task_building_runs', {
    params,
  });

export const getTask = (id: string): Promise<Task> => fetchOne<Task>(`/tasks/${id}`);

export interface TaskSchedule {
  id: string;
  tenant_id: string;
  target_type: string;
  target_id: string;
  schedule_type: string;
  schedule_value: string;
  timezone: string;
  enabled: boolean;
  params: Record<string, unknown> | null;
  origin_type: string;
  integration_id: string | null;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
}

export const getTaskSchedule = (taskId: string): Promise<TaskSchedule> =>
  fetchOne<TaskSchedule>(`/tasks/${taskId}/schedule`);

export const updateTask = (id: string, data: Partial<Task>): Promise<Task> =>
  mutateOne<Task>('put', `/tasks/${id}`, data);

export const createTask = (data: {
  name: string;
  description: string;
  script: string;
}): Promise<Task> =>
  withApi('createTask', 'creating task', async () => {
    const payload = {
      name: data.name,
      description: data.description,
      script: data.script,
      function: 'extraction',
      scope: 'processing',
      status: 'enabled',
      visible: false,
    };
    return mutateOne<Task>('post', '/tasks', payload);
  });

export const checkTaskDeletable = (
  id: string
): Promise<{
  can_delete: boolean;
  reason: string | null;
  message: string | null;
  workflows?: Array<{ id: string; name: string }>;
}> =>
  fetchOne<{
    can_delete: boolean;
    reason: string | null;
    message: string | null;
    workflows?: Array<{ id: string; name: string }>;
  }>(`/tasks/${id}/check-delete`);

export const deleteTask = (id: string): Promise<void> => apiDelete(`/tasks/${id}`);

// Task Script Analysis
export const analyzeScript = (
  script: string
): Promise<{
  task_id: string | null;
  cy_name: string | null;
  tools_used: string[] | null;
  external_variables: string[] | null;
  errors: string[] | null;
}> =>
  mutateOne<{
    task_id: string | null;
    cy_name: string | null;
    tools_used: string[] | null;
    external_variables: string[] | null;
    errors: string[] | null;
  }>('post', '/tasks/analyze', { script });

export const analyzeTask = (
  taskId: string
): Promise<{
  task_id: string | null;
  cy_name: string | null;
  tools_used: string[] | null;
  external_variables: string[] | null;
  errors: string[] | null;
}> =>
  fetchOne<{
    task_id: string | null;
    cy_name: string | null;
    tools_used: string[] | null;
    external_variables: string[] | null;
    errors: string[] | null;
  }>(`/tasks/${taskId}/analyze`);

// Task Knowledge Units
export const getTaskKnowledgeUnits = (id: string): Promise<KnowledgeUnit[]> =>
  fetchOne<KnowledgeUnit[]>(`/tasks/${id}/knowledge-units`);

// Task Execution
export const executeTask = (
  taskId: string,
  input: Record<string, unknown>,
  executorConfig?: Record<string, unknown>
): Promise<{ trid: string; status: string; pollUrl?: string }> =>
  withApi('executeTask', 'executing task', async () => {
    const requestBody = {
      input,
      executor_config: executorConfig || { timeout_seconds: 60 },
    };
    const response = await backendApiClient.post<SifnosEnvelope<{ trid: string; status: string }>>(
      `/tasks/${taskId}/run`,
      requestBody
    );
    const pollUrl = response.headers.location as string | undefined;
    const result = response.data.data;
    return {
      trid: result.trid,
      status: result.status,
      pollUrl,
    };
  });

export const executeAdHocScript = (
  cyScript: string,
  input: Record<string, unknown>,
  executorConfig?: Record<string, unknown>
): Promise<{ trid: string; status: string; pollUrl?: string }> =>
  withApi('executeAdHocScript', 'executing ad-hoc script', async () => {
    const response = await backendApiClient.post<SifnosEnvelope<{ trid: string; status: string }>>(
      '/tasks/run',
      {
        cy_script: cyScript,
        input,
        executor_config: executorConfig || { timeout_seconds: 30 },
      }
    );
    const pollUrl = response.headers.location as string | undefined;
    const result = response.data.data;
    return {
      trid: result.trid,
      status: result.status,
      pollUrl,
    };
  });

export const getTaskRunStatus = (trid: string): Promise<{ status: string; updated_at: string }> =>
  fetchOne<{ status: string; updated_at: string }>(`/task-runs/${trid}/status`);

export const getTaskRunDetails = (trid: string): Promise<TaskRun> =>
  fetchOne<TaskRun>(`/task-runs/${trid}`);

export interface LogEntry {
  ts: number;
  message: string;
}

export interface TaskRunLogsResponse {
  trid: string;
  status: string;
  entries: (LogEntry | string)[];
  has_logs: boolean;
}

export const getTaskRunLogs = (trid: string): Promise<TaskRunLogsResponse> =>
  fetchOne<TaskRunLogsResponse>(`/task-runs/${trid}/logs`);
