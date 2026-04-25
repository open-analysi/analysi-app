import { useAuthStore } from '../store/authStore';
import {
  WorkflowGeneration,
  WorkflowGenerationListResponse,
  ActiveWorkflowResponse,
  AnalysisArtifact,
} from '../types/alert';
import {
  Workflow,
  WorkflowsResponse,
  WorkflowQueryParams,
  WorkflowRunRequest,
  WorkflowRunInitiatedResponse,
  WorkflowExecutionGraph,
  WorkflowRunStatus,
  WorkflowRun,
  WorkflowRunsResponse,
} from '../types/workflow';

import {
  withApi,
  fetchOne,
  fetchList,
  mutateOne,
  apiDelete,
  backendApiClient,
  resolveNodeTemplateId,
  type SifnosEnvelope,
} from './apiClient';

// ---------------------------------------------------------------------------
// List / Query
// ---------------------------------------------------------------------------

export const getWorkflowRuns = (
  params: Record<string, unknown> = {}
): Promise<{ runs: WorkflowRun[]; total: number }> =>
  withApi('getWorkflowRuns', 'fetching workflow runs', () =>
    fetchList<'runs', WorkflowRun>('/workflow-runs', 'runs', { params })
  );

export const getWorkflows = (params: WorkflowQueryParams = {}): Promise<WorkflowsResponse> =>
  withApi('getWorkflows', 'fetching workflows', () =>
    fetchList<'workflows', Workflow>('/workflows', 'workflows', { params })
  );

export const getWorkflowRunsList = (
  params: {
    workflow_id?: string;
    status?: string;
    page?: number;
    page_size?: number;
    sort?: string;
    order?: 'asc' | 'desc';
  } = {}
): Promise<WorkflowRunsResponse> =>
  withApi('getWorkflowRunsList', 'fetching workflow runs list', () =>
    fetchList<'workflow_runs', WorkflowRun>('/workflow-runs', 'workflow_runs', { params })
  );

export const listWorkflowGenerations = (params?: {
  triggering_alert_analysis_id?: string;
}): Promise<WorkflowGenerationListResponse> =>
  withApi('listWorkflowGenerations', 'listing workflow generations', () =>
    fetchList<'workflow_generations', WorkflowGeneration>(
      '/workflow-generations',
      'workflow_generations',
      { params }
    )
  );

// ---------------------------------------------------------------------------
// Single-item GET
// ---------------------------------------------------------------------------

export const getWorkflow = (workflowId: string): Promise<Workflow> =>
  withApi(
    'getWorkflow',
    'fetching workflow',
    () => fetchOne<Workflow>(`/workflows/${workflowId}`),
    { entityId: workflowId, entityType: 'workflow' }
  );

export const getWorkflowExecutionGraph = (workflowRunId: string): Promise<WorkflowExecutionGraph> =>
  withApi(
    'getWorkflowExecutionGraph',
    'fetching workflow execution graph',
    () => fetchOne<WorkflowExecutionGraph>(`/workflow-runs/${workflowRunId}/graph`),
    { entityId: workflowRunId, entityType: 'workflow-run' }
  );

export const getWorkflowRunStatus = (workflowRunId: string): Promise<WorkflowRunStatus> =>
  withApi(
    'getWorkflowRunStatus',
    'fetching workflow run status',
    () => fetchOne<WorkflowRunStatus>(`/workflow-runs/${workflowRunId}/status`),
    { entityId: workflowRunId, entityType: 'workflow-run' }
  );

export const getWorkflowRun = (workflowRunId: string): Promise<WorkflowRun> =>
  withApi(
    'getWorkflowRun',
    'fetching workflow run details',
    () => fetchOne<WorkflowRun>(`/workflow-runs/${workflowRunId}`),
    { entityId: workflowRunId, entityType: 'workflow-run' }
  );

export const getWorkflowArtifacts = (workflowRunId: string): Promise<AnalysisArtifact[]> =>
  withApi(
    'getWorkflowArtifacts',
    'fetching workflow artifacts',
    () => fetchOne<AnalysisArtifact[]>(`/workflow-runs/${workflowRunId}/artifacts`),
    { entityId: workflowRunId, entityType: 'workflow-run' }
  );

export const getWorkflowGeneration = (generationId: string): Promise<WorkflowGeneration> =>
  withApi(
    'getWorkflowGeneration',
    'fetching workflow generation details',
    () => fetchOne<WorkflowGeneration>(`/workflow-generations/${generationId}`),
    { entityId: generationId, entityType: 'workflow-generation' }
  );

export const getActiveWorkflowByTitle = (title: string): Promise<ActiveWorkflowResponse> =>
  withApi('getActiveWorkflowByTitle', 'fetching active workflow by title', () =>
    fetchOne<ActiveWorkflowResponse>('/analysis-groups/active-workflow', { params: { title } })
  );

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export const executeWorkflow = (
  workflowId: string,
  requestData: WorkflowRunRequest
): Promise<WorkflowRunInitiatedResponse> =>
  withApi(
    'executeWorkflow',
    'executing workflow',
    () =>
      mutateOne<WorkflowRunInitiatedResponse>('post', `/workflows/${workflowId}/run`, requestData),
    { entityId: workflowId, entityType: 'workflow' }
  );

export const createWorkflow = (data: {
  name: string;
  description: string;
  is_dynamic: boolean;
  io_schema: { input: Record<string, unknown>; output: Record<string, unknown> };
  nodes: Array<{
    node_id: string;
    kind: string;
    name: string;
    task_id?: string;
    node_template_id?: string;
    foreach_config?: Record<string, unknown>;
    template_code?: string;
    is_start_node?: boolean;
    schemas?: Record<string, unknown>;
  }>;
  edges: Array<{
    edge_id: string;
    from_node_id: string;
    to_node_id: string;
    alias?: string;
  }>;
  data_samples?: unknown[];
  created_by?: string;
}): Promise<Workflow> =>
  withApi('createWorkflow', 'creating workflow', async () => {
    // created_by is resolved from JWT by the backend -- strip it from the payload.
    // eslint-disable-next-line @typescript-eslint/no-unused-vars, sonarjs/no-unused-vars
    const { created_by: _stripped, ...rest } = data;
    const payload = {
      ...rest,
      nodes: data.nodes.map((node) => ({
        ...node,
        schemas: node.schemas || {},
        node_template_id: resolveNodeTemplateId(node.node_template_id),
      })),
    };
    const response = await backendApiClient.post<SifnosEnvelope<Workflow>>('/workflows', payload);
    return response.data.data;
  });

export const updateWorkflow = (
  workflowId: string,
  data: {
    name?: string;
    description?: string;
    is_dynamic?: boolean;
    io_schema?: { input: Record<string, unknown>; output: Record<string, unknown> };
    nodes?: Array<{
      node_id: string;
      kind: string;
      name: string;
      task_id?: string;
      node_template_id?: string;
      foreach_config?: Record<string, unknown>;
      template_code?: string;
      is_start_node?: boolean;
      schemas?: Record<string, unknown>;
    }>;
    edges?: Array<{
      edge_id: string;
      from_node_id: string;
      to_node_id: string;
      alias?: string;
    }>;
    data_samples?: unknown[];
    created_by?: string;
  }
): Promise<Workflow> =>
  withApi(
    'updateWorkflow',
    'updating workflow',
    async () => {
      const payload = {
        ...data,
        created_by: data.created_by || useAuthStore.getState().email || 'system',
        nodes: data.nodes?.map((node) => ({
          ...node,
          schemas: node.schemas || {},
          node_template_id: resolveNodeTemplateId(node.node_template_id),
        })),
      };
      const response = await backendApiClient.put<SifnosEnvelope<Workflow>>(
        `/workflows/${workflowId}`,
        payload
      );
      return response.data.data;
    },
    { entityId: workflowId }
  );

export const deleteWorkflow = (workflowId: string): Promise<void> =>
  withApi('deleteWorkflow', 'deleting workflow', () => apiDelete(`/workflows/${workflowId}`), {
    entityId: workflowId,
    entityType: 'workflow',
  });
