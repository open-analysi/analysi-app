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

vi.mock('../../utils/logger', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

vi.mock('../../utils/errorHandler', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import * as tasksApi from '../tasksApi';

// Shared constants to avoid lint warnings about repeated strings
const PROBLEM_TYPE = 'about:blank';
const TASK_ID = 'task-123';
const TRID = 'trid-456';
const POLL_URL = '/task-runs/trid-456/status';
const STATUS_RUNNING = 'running';

describe('tasksApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getTasks', () => {
    it('should GET /tasks with query params and return full response data', async () => {
      const params = { limit: 10, offset: 0, sort: 'name', order: 'asc' as const };
      mockGet.mockResolvedValue({
        data: {
          data: [{ id: TASK_ID, name: 'Test Task' }],
          meta: { total: 1 },
        },
      });

      const result = await tasksApi.getTasks(params);

      expect(mockGet).toHaveBeenCalledWith('/tasks', { params });
      expect(result).toEqual({ tasks: [{ id: TASK_ID, name: 'Test Task' }], total: 1 });
    });
  });

  describe('getTaskRuns', () => {
    it('should GET /task-runs with params', async () => {
      const params = { task_id: TASK_ID, limit: 20 };
      mockGet.mockResolvedValue({
        data: {
          data: [{ trid: TRID }],
          meta: { total: 1 },
        },
      });

      const result = await tasksApi.getTaskRuns(params);

      expect(mockGet).toHaveBeenCalledWith('/task-runs', { params });
      expect(result).toEqual({ task_runs: [{ trid: TRID }], total: 1 });
    });
  });

  describe('getTaskRunHistory', () => {
    it('should GET /task-runs with hardcoded params for successful runs', async () => {
      mockGet.mockResolvedValue({
        data: {
          data: [{ trid: TRID }],
          meta: { total: 1 },
        },
      });

      const result = await tasksApi.getTaskRunHistory(TASK_ID, 10);

      expect(mockGet).toHaveBeenCalledWith('/task-runs', {
        params: {
          task_id: TASK_ID,
          limit: 10,
          sort: 'created_at',
          order: 'desc',
          status: 'completed',
        },
      });
      expect(result).toEqual({ task_runs: [{ trid: TRID }], total: 1 });
    });
  });

  describe('getTaskBuildingRuns', () => {
    it('should GET /task-generations-internal with params', async () => {
      const params = { limit: 5 };
      mockGet.mockResolvedValue({
        data: {
          data: [{ id: 'run-1' }],
          meta: { total: 1 },
        },
      });

      const result = await tasksApi.getTaskBuildingRuns(params);

      expect(mockGet).toHaveBeenCalledWith('/task-generations-internal', { params });
      expect(result).toEqual({ task_building_runs: [{ id: 'run-1' }], total: 1 });
    });
  });

  describe('createTaskGeneration', () => {
    it('should POST /task-generations with description and optional alert_id', async () => {
      const request = { description: 'Build a phishing detector', alert_id: 'alert-99' };
      const mockData = {
        id: 'gen-1',
        status: 'pending',
        description: request.description,
        alert_id: request.alert_id,
        created_at: '2025-01-01T00:00:00Z',
      };
      mockPost.mockResolvedValue({
        data: { data: mockData, meta: { request_id: 'test' } },
      });

      const result = await tasksApi.createTaskGeneration(request);

      expect(mockPost).toHaveBeenCalledWith('/task-generations', request);
      expect(result).toEqual(mockData);
    });
  });

  describe('getTask', () => {
    it('should GET /tasks/:id and return response data', async () => {
      mockGet.mockResolvedValue({
        data: {
          data: { id: TASK_ID, name: 'My Task' },
          meta: { request_id: 'test' },
        },
      });

      const result = await tasksApi.getTask(TASK_ID);

      expect(mockGet).toHaveBeenCalledWith(`/tasks/${TASK_ID}`);
      expect(result).toEqual({ id: TASK_ID, name: 'My Task' });
    });
  });

  describe('updateTask', () => {
    it('should PUT /tasks/:id with partial data', async () => {
      const updateData = { name: 'Updated Name', description: 'New desc' };
      const responseData = { id: TASK_ID, ...updateData };
      mockPut.mockResolvedValue({
        data: {
          data: responseData,
          meta: { request_id: 'test' },
        },
      });

      const result = await tasksApi.updateTask(TASK_ID, updateData);

      expect(mockPut).toHaveBeenCalledWith(`/tasks/${TASK_ID}`, updateData);
      expect(result).toEqual(responseData);
    });
  });

  describe('createTask', () => {
    it('should POST /tasks with enriched payload including function, scope, status, visible', async () => {
      const inputData = { name: 'New Task', description: 'A task', script: 'cy.run()' };
      const responseData = { id: 'new-task-1', ...inputData };
      mockPost.mockResolvedValue({
        data: {
          data: responseData,
          meta: { request_id: 'test' },
        },
      });

      const result = await tasksApi.createTask(inputData);

      expect(mockPost).toHaveBeenCalledWith('/tasks', {
        name: 'New Task',
        description: 'A task',
        script: 'cy.run()',
        function: 'extraction',
        scope: 'processing',
        status: 'enabled',
        visible: false,
      });
      expect(result).toEqual(responseData);
    });
  });

  describe('checkTaskDeletable', () => {
    it('should GET /tasks/:id/check-delete', async () => {
      const mockData = { can_delete: true, reason: null, message: null };
      mockGet.mockResolvedValue({
        data: { data: mockData, meta: { request_id: 'test' } },
      });

      const result = await tasksApi.checkTaskDeletable(TASK_ID);

      expect(mockGet).toHaveBeenCalledWith(`/tasks/${TASK_ID}/check-delete`);
      expect(result).toEqual(mockData);
    });
  });

  describe('deleteTask', () => {
    it('should DELETE /tasks/:id', async () => {
      mockDelete.mockResolvedValue({ data: {} });

      await tasksApi.deleteTask(TASK_ID);

      expect(mockDelete).toHaveBeenCalledWith(`/tasks/${TASK_ID}`);
    });
  });

  describe('executeTask', () => {
    it('should POST /tasks/:id/run with executor_config and return trid, status, pollUrl from headers', async () => {
      const input = { alert_id: 'alert-1' };
      const executorConfig = { timeout_seconds: 120 };
      mockPost.mockResolvedValue({
        data: {
          data: { trid: TRID, status: STATUS_RUNNING },
          meta: { request_id: 'test' },
        },
        headers: { location: POLL_URL },
      });

      const result = await tasksApi.executeTask(TASK_ID, input, executorConfig);

      expect(mockPost).toHaveBeenCalledWith(`/tasks/${TASK_ID}/run`, {
        input,
        executor_config: executorConfig,
      });
      expect(result).toEqual({
        trid: TRID,
        status: STATUS_RUNNING,
        pollUrl: POLL_URL,
      });
    });

    it('should use default timeout_seconds when executorConfig is not provided', async () => {
      const input = { alert_id: 'alert-2' };
      mockPost.mockResolvedValue({
        data: {
          data: { trid: TRID, status: STATUS_RUNNING },
          meta: { request_id: 'test' },
        },
        headers: { location: POLL_URL },
      });

      await tasksApi.executeTask(TASK_ID, input);

      expect(mockPost).toHaveBeenCalledWith(`/tasks/${TASK_ID}/run`, {
        input,
        executor_config: { timeout_seconds: 60 },
      });
    });
  });

  // ==================== Error Path Tests ====================

  describe('getTask - error paths', () => {
    it('should propagate 404 when task not found', async () => {
      mockGet.mockRejectedValue({
        response: {
          status: 404,
          data: {
            type: PROBLEM_TYPE,
            title: 'Not Found',
            status: 404,
            detail: 'Task not found',
            request_id: 'r-1',
          },
        },
      });

      await expect(tasksApi.getTask('nonexistent')).rejects.toMatchObject({
        response: { status: 404 },
      });
    });
  });

  describe('createTask - error paths', () => {
    it('should propagate 422 validation error', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 422,
          data: {
            type: PROBLEM_TYPE,
            title: 'Validation Error',
            status: 422,
            detail: 'Request validation failed',
            errors: [{ loc: ['body', 'name'], msg: 'Field required', type: 'missing' }],
            request_id: 'r-2',
          },
        },
      });

      await expect(
        tasksApi.createTask({ name: '', description: '', script: '' })
      ).rejects.toMatchObject({
        response: {
          status: 422,
          data: {
            errors: expect.arrayContaining([expect.objectContaining({ msg: 'Field required' })]),
          },
        },
      });
    });

    it('should propagate 409 duplicate task', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 409,
          data: {
            type: PROBLEM_TYPE,
            title: 'Conflict',
            status: 409,
            detail: 'Task with this name already exists',
            request_id: 'r-3',
          },
        },
      });

      await expect(
        tasksApi.createTask({ name: 'Existing', description: '', script: '' })
      ).rejects.toMatchObject({
        response: { status: 409 },
      });
    });
  });

  describe('executeTask - error paths', () => {
    it('should propagate 404 when task not found', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 404,
          data: {
            type: PROBLEM_TYPE,
            title: 'Not Found',
            status: 404,
            detail: 'Task not found',
            request_id: 'r-4',
          },
        },
      });

      await expect(tasksApi.executeTask('missing', {})).rejects.toMatchObject({
        response: { status: 404 },
      });
    });

    it('should propagate 503 database unavailable', async () => {
      mockPost.mockRejectedValue({
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

      await expect(tasksApi.executeTask(TASK_ID, {})).rejects.toMatchObject({
        response: { status: 503, data: { detail: expect.stringContaining('Database') } },
      });
    });
  });

  describe('deleteTask - error paths', () => {
    it('should propagate 404 when task not found', async () => {
      mockDelete.mockRejectedValue({
        response: {
          status: 404,
          data: {
            type: PROBLEM_TYPE,
            title: 'Not Found',
            status: 404,
            detail: 'Task not found',
            request_id: 'r-6',
          },
        },
      });

      await expect(tasksApi.deleteTask('missing')).rejects.toMatchObject({
        response: { status: 404 },
      });
    });
  });

  describe('executeAdHocScript', () => {
    it('should POST /tasks/run with cy_script, input, and executor_config', async () => {
      const cyScript = 'cy.run("test")';
      const input = { data: 'value' };
      const executorConfig = { timeout_seconds: 45 };
      mockPost.mockResolvedValue({
        data: {
          data: { trid: TRID, status: STATUS_RUNNING },
          meta: { request_id: 'test' },
        },
        headers: { location: POLL_URL },
      });

      const result = await tasksApi.executeAdHocScript(cyScript, input, executorConfig);

      expect(mockPost).toHaveBeenCalledWith('/tasks/run', {
        cy_script: cyScript,
        input,
        executor_config: executorConfig,
      });
      expect(result).toEqual({
        trid: TRID,
        status: STATUS_RUNNING,
        pollUrl: POLL_URL,
      });
    });

    it('should use default timeout_seconds of 30 when executorConfig is omitted', async () => {
      const cyScript = 'cy.run("default")';
      const input = {};
      mockPost.mockResolvedValue({
        data: {
          data: { trid: TRID, status: STATUS_RUNNING },
          meta: { request_id: 'test' },
        },
        headers: {},
      });

      const result = await tasksApi.executeAdHocScript(cyScript, input);

      expect(mockPost).toHaveBeenCalledWith('/tasks/run', {
        cy_script: cyScript,
        input,
        executor_config: { timeout_seconds: 30 },
      });
      expect(result.pollUrl).toBeUndefined();
    });
  });
});
