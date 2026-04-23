import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Use vi.hoisted to ensure mocks are available before vi.mock runs
const { mockGet, mockPost, mockPut, mockPatch, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPut: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: mockGet,
      post: mockPost,
      put: mockPut,
      patch: mockPatch,
      delete: mockDelete,
      interceptors: {
        request: { use: vi.fn(), eject: vi.fn() },
        response: { use: vi.fn(), eject: vi.fn() },
      },
    })),
  },
}));

vi.mock('../../utils/errorHandler', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('../../store/authStore', () => ({
  useAuthStore: {
    getState: vi.fn(() => ({ email: 'test@example.com' })),
  },
}));

import { WorkflowRunRequest } from '../../types/workflow';
import * as workflowsApi from '../workflowsApi';

// Constants for repeated test values
const PROBLEM_TYPE = 'about:blank';
const WORKFLOW_ID = 'wf-abc-123';
const WORKFLOW_RUN_ID = 'run-xyz-789';
const NETWORK_ERROR_MSG = 'Network error';
const VALID_UUID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
const SHOULD_THROW_ON_ERROR = 'should throw on error';

describe('workflowsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getWorkflowRuns', () => {
    it('should call GET /workflow-runs with params and return data', async () => {
      const params = { workflow_id: WORKFLOW_ID, status: 'completed' };
      mockGet.mockResolvedValue({
        data: {
          data: [{ id: WORKFLOW_RUN_ID }],
          meta: { total: 1 },
        },
      });

      const result = await workflowsApi.getWorkflowRuns(params);

      expect(mockGet).toHaveBeenCalledWith('/workflow-runs', { params });
      expect(result).toEqual({ runs: [{ id: WORKFLOW_RUN_ID }], total: 1 });
    });

    it(SHOULD_THROW_ON_ERROR, async () => {
      mockGet.mockRejectedValue(new Error(NETWORK_ERROR_MSG));

      await expect(workflowsApi.getWorkflowRuns()).rejects.toThrow(NETWORK_ERROR_MSG);
    });
  });

  describe('getWorkflows', () => {
    it('should call GET /workflows with params and return data', async () => {
      const params = { page: 1, page_size: 10 };
      mockGet.mockResolvedValue({
        data: {
          data: [{ id: WORKFLOW_ID, name: 'Test WF' }],
          meta: { total: 1 },
        },
      });

      const result = await workflowsApi.getWorkflows(params);

      expect(mockGet).toHaveBeenCalledWith('/workflows', { params });
      expect(result).toEqual({ workflows: [{ id: WORKFLOW_ID, name: 'Test WF' }], total: 1 });
    });

    it('should default to empty params', async () => {
      mockGet.mockResolvedValue({
        data: {
          data: [],
          meta: { total: 0 },
        },
      });

      await workflowsApi.getWorkflows();

      expect(mockGet).toHaveBeenCalledWith('/workflows', { params: {} });
    });
  });

  describe('getWorkflow', () => {
    it('should call GET /workflows/:id and return data', async () => {
      const mockWorkflow = { id: WORKFLOW_ID, name: 'My Workflow' };
      mockGet.mockResolvedValue({
        data: {
          data: mockWorkflow,
          meta: { request_id: 'test' },
        },
      });

      const result = await workflowsApi.getWorkflow(WORKFLOW_ID);

      expect(mockGet).toHaveBeenCalledWith(`/workflows/${WORKFLOW_ID}`);
      expect(result).toEqual(mockWorkflow);
    });

    it(SHOULD_THROW_ON_ERROR, async () => {
      mockGet.mockRejectedValue(new Error(NETWORK_ERROR_MSG));

      await expect(workflowsApi.getWorkflow(WORKFLOW_ID)).rejects.toThrow(NETWORK_ERROR_MSG);
    });
  });

  describe('executeWorkflow', () => {
    it('should call POST /workflows/:id/run with request data', async () => {
      const requestData: WorkflowRunRequest = {
        input_data: { alert_id: 'alert-1' },
      };
      const mockResponse = { workflow_run_id: WORKFLOW_RUN_ID };
      mockPost.mockResolvedValue({
        data: {
          data: mockResponse,
          meta: { request_id: 'test' },
        },
      });

      const result = await workflowsApi.executeWorkflow(WORKFLOW_ID, requestData);

      expect(mockPost).toHaveBeenCalledWith(`/workflows/${WORKFLOW_ID}/run`, requestData);
      expect(result).toEqual(mockResponse);
    });

    it(SHOULD_THROW_ON_ERROR, async () => {
      mockPost.mockRejectedValue(new Error(NETWORK_ERROR_MSG));

      await expect(workflowsApi.executeWorkflow(WORKFLOW_ID, {} as never)).rejects.toThrow(
        NETWORK_ERROR_MSG
      );
    });
  });

  describe('createWorkflow', () => {
    const basePayload = {
      name: 'New Workflow',
      description: 'A test workflow',
      is_dynamic: false,
      io_schema: { input: {}, output: {} },
      nodes: [
        {
          node_id: 'node-1',
          kind: 'task',
          name: 'Task Node',
          task_id: 'task-abc',
          node_template_id: VALID_UUID,
        },
        {
          node_id: 'node-2',
          kind: 'transform',
          name: 'Identity Node',
          node_template_id: 'identity',
        },
      ],
      edges: [{ edge_id: 'edge-1', from_node_id: 'node-1', to_node_id: 'node-2' }],
    };

    it('should call POST /workflows and strip created_by from payload', async () => {
      const payloadWithCreatedBy = { ...basePayload, created_by: 'should-be-removed@test.com' };
      const mockWorkflow = { id: WORKFLOW_ID, name: 'New Workflow' };
      mockPost.mockResolvedValue({
        data: {
          data: mockWorkflow,
          meta: { request_id: 'test' },
        },
      });

      const result = await workflowsApi.createWorkflow(payloadWithCreatedBy);

      expect(result).toEqual(mockWorkflow);

      // Verify created_by is NOT in the payload sent to the API
      const sentPayload = mockPost.mock.calls[0][1] as Record<string, unknown>;
      expect(sentPayload).not.toHaveProperty('created_by');
    });

    it('should default node schemas to {} and resolve node_template_id', async () => {
      const noSchemaPayload = {
        ...basePayload,
        nodes: [
          { node_id: 'node-1', kind: 'task', name: 'No Schema Node' },
          {
            node_id: 'node-2',
            kind: 'transform',
            name: 'Identity',
            node_template_id: 'identity',
          },
        ],
      };
      mockPost.mockResolvedValue({
        data: {
          data: { id: WORKFLOW_ID },
          meta: { request_id: 'test' },
        },
      });

      await workflowsApi.createWorkflow(noSchemaPayload);

      const sentPayload = mockPost.mock.calls[0][1] as {
        nodes: Array<{ schemas: Record<string, unknown>; node_template_id?: string }>;
      };

      // Nodes without schemas should get {}
      expect(sentPayload.nodes[0].schemas).toEqual({});
      // Built-in 'identity' should resolve to system UUID
      expect(sentPayload.nodes[1].node_template_id).toBe('00000000-0000-0000-0000-000000000001');
    });

    it('should preserve existing schemas on nodes', async () => {
      const customSchemas = { input: { type: 'object' } };
      const payload = {
        ...basePayload,
        nodes: [
          {
            node_id: 'node-1',
            kind: 'task',
            name: 'With Schema',
            schemas: customSchemas,
          },
        ],
      };
      mockPost.mockResolvedValue({
        data: {
          data: { id: WORKFLOW_ID },
          meta: { request_id: 'test' },
        },
      });

      await workflowsApi.createWorkflow(payload);

      const sentPayload = mockPost.mock.calls[0][1] as {
        nodes: Array<{ schemas: Record<string, unknown> }>;
      };
      expect(sentPayload.nodes[0].schemas).toEqual(customSchemas);
    });
  });

  describe('updateWorkflow', () => {
    const baseUpdateData = {
      name: 'Updated Workflow',
      description: 'Updated description',
      is_dynamic: true,
      nodes: [
        {
          node_id: 'node-1',
          kind: 'task',
          name: 'Updated Node',
          node_template_id: 'merge',
        },
      ],
      edges: [],
    };

    it('should call PUT /workflows/:id and add created_by from authStore', async () => {
      const mockWorkflow = { id: WORKFLOW_ID, name: 'Updated Workflow' };
      mockPut.mockResolvedValue({
        data: {
          data: mockWorkflow,
          meta: { request_id: 'test' },
        },
      });

      const result = await workflowsApi.updateWorkflow(WORKFLOW_ID, baseUpdateData);

      expect(result).toEqual(mockWorkflow);
      expect(mockPut).toHaveBeenCalledWith(
        `/workflows/${WORKFLOW_ID}`,
        expect.objectContaining({ created_by: 'test@example.com' })
      );
    });

    it('should resolve built-in node_template_id names to UUIDs', async () => {
      mockPut.mockResolvedValue({
        data: {
          data: { id: WORKFLOW_ID },
          meta: { request_id: 'test' },
        },
      });

      await workflowsApi.updateWorkflow(WORKFLOW_ID, baseUpdateData);

      const sentPayload = mockPut.mock.calls[0][1] as {
        nodes: Array<{ node_template_id?: string }>;
      };
      // 'merge' should resolve to system UUID
      expect(sentPayload.nodes[0].node_template_id).toBe('00000000-0000-0000-0000-000000000002');
    });

    it('should default node schemas to {} when missing', async () => {
      mockPut.mockResolvedValue({
        data: {
          data: { id: WORKFLOW_ID },
          meta: { request_id: 'test' },
        },
      });

      await workflowsApi.updateWorkflow(WORKFLOW_ID, baseUpdateData);

      const sentPayload = mockPut.mock.calls[0][1] as {
        nodes: Array<{ schemas: Record<string, unknown> }>;
      };
      expect(sentPayload.nodes[0].schemas).toEqual({});
    });

    it('should use provided created_by if present', async () => {
      const dataWithCreatedBy = { ...baseUpdateData, created_by: 'custom@example.com' };
      mockPut.mockResolvedValue({
        data: {
          data: { id: WORKFLOW_ID },
          meta: { request_id: 'test' },
        },
      });

      await workflowsApi.updateWorkflow(WORKFLOW_ID, dataWithCreatedBy);

      const sentPayload = mockPut.mock.calls[0][1] as { created_by: string };
      expect(sentPayload.created_by).toBe('custom@example.com');
    });
  });

  describe('deleteWorkflow', () => {
    it('should call DELETE /workflows/:id', async () => {
      mockDelete.mockResolvedValue({ data: {} });

      await workflowsApi.deleteWorkflow(WORKFLOW_ID);

      expect(mockDelete).toHaveBeenCalledWith(`/workflows/${WORKFLOW_ID}`);
    });

    it(SHOULD_THROW_ON_ERROR, async () => {
      mockDelete.mockRejectedValue(new Error(NETWORK_ERROR_MSG));

      await expect(workflowsApi.deleteWorkflow(WORKFLOW_ID)).rejects.toThrow(NETWORK_ERROR_MSG);
    });
  });

  describe('getWorkflowExecutionGraph', () => {
    it('should call GET /workflow-runs/:id/graph and return data', async () => {
      const mockGraph = { nodes: [{ id: 'n1' }], edges: [], is_complete: true };
      mockGet.mockResolvedValue({
        data: {
          data: mockGraph,
          meta: { request_id: 'test' },
        },
      });

      const result = await workflowsApi.getWorkflowExecutionGraph(WORKFLOW_RUN_ID);

      expect(mockGet).toHaveBeenCalledWith(`/workflow-runs/${WORKFLOW_RUN_ID}/graph`);
      expect(result).toEqual(mockGraph);
    });

    it(SHOULD_THROW_ON_ERROR, async () => {
      mockGet.mockRejectedValue(new Error(NETWORK_ERROR_MSG));

      await expect(workflowsApi.getWorkflowExecutionGraph(WORKFLOW_RUN_ID)).rejects.toThrow(
        NETWORK_ERROR_MSG
      );
    });
  });

  describe('getWorkflowRunStatus', () => {
    it('should call GET /workflow-runs/:id/status and return data', async () => {
      const mockStatus = { status: 'completed', workflow_run_id: WORKFLOW_RUN_ID };
      mockGet.mockResolvedValue({
        data: {
          data: mockStatus,
          meta: { request_id: 'test' },
        },
      });

      const result = await workflowsApi.getWorkflowRunStatus(WORKFLOW_RUN_ID);

      expect(mockGet).toHaveBeenCalledWith(`/workflow-runs/${WORKFLOW_RUN_ID}/status`);
      expect(result).toEqual(mockStatus);
    });
  });

  describe('getWorkflowRun', () => {
    it('should call GET /workflow-runs/:id and return data', async () => {
      const mockRun = { id: WORKFLOW_RUN_ID, status: 'running' };
      mockGet.mockResolvedValue({
        data: {
          data: mockRun,
          meta: { request_id: 'test' },
        },
      });

      const result = await workflowsApi.getWorkflowRun(WORKFLOW_RUN_ID);

      expect(mockGet).toHaveBeenCalledWith(`/workflow-runs/${WORKFLOW_RUN_ID}`);
      expect(result).toEqual(mockRun);
    });

    it(SHOULD_THROW_ON_ERROR, async () => {
      mockGet.mockRejectedValue(new Error(NETWORK_ERROR_MSG));

      await expect(workflowsApi.getWorkflowRun(WORKFLOW_RUN_ID)).rejects.toThrow(NETWORK_ERROR_MSG);
    });
  });

  describe('getWorkflowArtifacts', () => {
    it('should call GET /workflow-runs/:id/artifacts and return data', async () => {
      const mockArtifacts = [
        { id: 'art-1', name: 'Report', type: 'markdown' },
        { id: 'art-2', name: 'Data', type: 'json' },
      ];
      mockGet.mockResolvedValue({
        data: {
          data: mockArtifacts,
          meta: { request_id: 'test' },
        },
      });

      const result = await workflowsApi.getWorkflowArtifacts(WORKFLOW_RUN_ID);

      expect(mockGet).toHaveBeenCalledWith(`/workflow-runs/${WORKFLOW_RUN_ID}/artifacts`);
      expect(result).toEqual(mockArtifacts);
      expect(result).toHaveLength(2);
    });

    it(SHOULD_THROW_ON_ERROR, async () => {
      mockGet.mockRejectedValue(new Error(NETWORK_ERROR_MSG));

      await expect(workflowsApi.getWorkflowArtifacts(WORKFLOW_RUN_ID)).rejects.toThrow(
        NETWORK_ERROR_MSG
      );
    });
  });

  // ==================== Error Path Tests (RFC 9457) ====================

  describe('error paths', () => {
    it('createWorkflow should propagate 422 validation error', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 422,
          data: {
            type: PROBLEM_TYPE,
            title: 'Validation Error',
            status: 422,
            detail: 'Request validation failed',
            errors: [{ loc: ['body', 'name'], msg: 'Field required', type: 'missing' }],
            request_id: 'r-1',
          },
        },
      });

      const minimalInput = {
        name: '',
        description: '',
        is_dynamic: false,
        io_schema: { input: {}, output: {} },
        nodes: [],
        edges: [],
      };
      await expect(workflowsApi.createWorkflow(minimalInput)).rejects.toMatchObject({
        response: { status: 422, data: { errors: expect.any(Array) } },
      });
    });

    it('executeWorkflow should propagate 404 when workflow not found', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 404,
          data: {
            type: PROBLEM_TYPE,
            title: 'Not Found',
            status: 404,
            detail: 'Workflow not found',
            request_id: 'r-2',
          },
        },
      });

      await expect(workflowsApi.executeWorkflow('missing', {} as never)).rejects.toMatchObject({
        response: { status: 404, data: { detail: 'Workflow not found' } },
      });
    });

    it('updateWorkflow should propagate 409 conflict', async () => {
      mockPut.mockRejectedValue({
        response: {
          status: 409,
          data: {
            type: PROBLEM_TYPE,
            title: 'Conflict',
            status: 409,
            detail: 'Workflow name already exists',
            request_id: 'r-3',
          },
        },
      });

      await expect(
        workflowsApi.updateWorkflow(WORKFLOW_ID, { name: 'Existing' } as never)
      ).rejects.toMatchObject({
        response: { status: 409 },
      });
    });

    it('getWorkflowRunStatus should propagate 404', async () => {
      mockGet.mockRejectedValue({
        response: {
          status: 404,
          data: {
            type: PROBLEM_TYPE,
            title: 'Not Found',
            status: 404,
            detail: 'Workflow run not found',
            request_id: 'r-4',
          },
        },
      });

      await expect(workflowsApi.getWorkflowRunStatus('missing')).rejects.toMatchObject({
        response: { status: 404 },
      });
    });

    it('getWorkflows should propagate 503 database error', async () => {
      mockGet.mockRejectedValue({
        response: {
          status: 503,
          data: {
            type: PROBLEM_TYPE,
            title: 'Service Unavailable',
            status: 503,
            detail: 'Database temporarily unavailable. Please retry.',
            request_id: 'r-5',
          },
        },
      });

      await expect(workflowsApi.getWorkflows()).rejects.toMatchObject({
        response: { status: 503, data: { detail: expect.stringContaining('Database') } },
      });
    });
  });

  describe('getActiveWorkflowByTitle', () => {
    it('should call GET /analysis-groups/active-workflow with title param', async () => {
      const title = 'Phishing Analysis';
      const mockResponse = { workflow_id: WORKFLOW_ID, title };
      mockGet.mockResolvedValue({
        data: {
          data: mockResponse,
          meta: { request_id: 'test' },
        },
      });

      const result = await workflowsApi.getActiveWorkflowByTitle(title);

      expect(mockGet).toHaveBeenCalledWith('/analysis-groups/active-workflow', {
        params: { title },
      });
      expect(result).toEqual(mockResponse);
    });

    it(SHOULD_THROW_ON_ERROR, async () => {
      mockGet.mockRejectedValue(new Error(NETWORK_ERROR_MSG));

      await expect(workflowsApi.getActiveWorkflowByTitle('missing')).rejects.toThrow(
        NETWORK_ERROR_MSG
      );
    });
  });
});
