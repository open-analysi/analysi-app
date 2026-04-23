import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Use vi.hoisted to ensure mocks are available before vi.mock runs
const { mockGet, mockPost, mockPut, mockPatch, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPut: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock('axios', () => {
  return {
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
  };
});

vi.mock('../../utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
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

import * as integrationsApi from '../integrationsApi';

// Shared constants to avoid string duplication
const PROBLEM_TYPE = 'about:blank';
const INT_ID = 'int-123';

const SCHEDULE_ID = 'sched-456';
const CRED_ID = 'cred-789';

describe('integrationsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getAllTools', () => {
    it('should fetch all tools successfully', async () => {
      const mockData = { tools: [{ name: 'tool1' }], total: 1 };
      mockGet.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.getAllTools();

      expect(mockGet).toHaveBeenCalledWith('/integrations/tools/all');
      expect(result).toEqual(mockData);
    });

    it('should throw on network error', async () => {
      mockGet.mockRejectedValue(new Error('Network error'));

      await expect(integrationsApi.getAllTools()).rejects.toThrow('Network error');
      expect(mockGet).toHaveBeenCalledWith('/integrations/tools/all');
    });
  });

  describe('getIntegrationTypes', () => {
    it('should fetch integration types from registry', async () => {
      const mockData = [{ integration_type: 'splunk', name: 'Splunk' }];
      mockGet.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.getIntegrationTypes();

      expect(mockGet).toHaveBeenCalledWith('/integrations/registry');
      expect(result).toEqual(mockData);
    });
  });

  describe('getIntegrations', () => {
    it('should fetch integrations with query params', async () => {
      const mockData = [{ integration_id: INT_ID, name: 'My Integration' }];
      const params = { integration_type: 'splunk', enabled: true, limit: 10, skip: 0 };
      mockGet.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.getIntegrations(params);

      expect(mockGet).toHaveBeenCalledWith('/integrations', { params });
      expect(result).toEqual(mockData);
    });

    it('should fetch integrations with no params', async () => {
      const mockData: unknown[] = [];
      mockGet.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.getIntegrations();

      expect(mockGet).toHaveBeenCalledWith('/integrations', { params: {} });
      expect(result).toEqual(mockData);
    });
  });

  describe('createIntegration', () => {
    it('should create an integration with body data', async () => {
      const body = {
        integration_id: INT_ID,
        integration_type: 'splunk',
        name: 'My Splunk',
        settings: { host: 'localhost' },
      };
      const mockData = { ...body, enabled: false };
      mockPost.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.createIntegration(body);

      expect(mockPost).toHaveBeenCalledWith('/integrations', body);
      expect(result).toEqual(mockData);
    });
  });

  describe('getIntegration', () => {
    it('should fetch a single integration by id', async () => {
      const mockData = { integration_id: INT_ID, name: 'My Integration' };
      mockGet.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.getIntegration(INT_ID);

      expect(mockGet).toHaveBeenCalledWith(`/integrations/${INT_ID}`);
      expect(result).toEqual(mockData);
    });
  });

  describe('updateIntegration', () => {
    it('should patch an integration with partial data', async () => {
      const updateData = { name: 'Renamed Integration' };
      const mockData = { integration_id: INT_ID, ...updateData };
      mockPatch.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.updateIntegration(INT_ID, updateData);

      expect(mockPatch).toHaveBeenCalledWith(`/integrations/${INT_ID}`, updateData);
      expect(result).toEqual(mockData);
    });
  });

  describe('deleteIntegration', () => {
    it('should delete an integration by id', async () => {
      mockDelete.mockResolvedValue({ data: null });

      await integrationsApi.deleteIntegration(INT_ID);

      expect(mockDelete).toHaveBeenCalledWith(`/integrations/${INT_ID}`);
    });
  });

  describe('enableIntegration', () => {
    it('should post to enable an integration', async () => {
      const mockData = { integration_id: INT_ID, enabled: true };
      mockPost.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.enableIntegration(INT_ID);

      expect(mockPost).toHaveBeenCalledWith(`/integrations/${INT_ID}/enable`);
      expect(result).toEqual(mockData);
    });
  });

  describe('getIntegrationHealth', () => {
    it('should fetch health status for an integration', async () => {
      const mockData = { status: 'healthy', success_rate_24h: 99.5 };
      mockGet.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.getIntegrationHealth(INT_ID);

      expect(mockGet).toHaveBeenCalledWith(`/integrations/${INT_ID}/health`);
      expect(result).toEqual(mockData);
    });
  });

  describe('triggerManagedRun', () => {
    it('should post to trigger a managed resource run', async () => {
      const mockData = {
        task_run_id: 'run-001',
        status: 'running',
        task_id: 'task-1',
        resource_key: 'health_check',
      };
      mockPost.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.triggerManagedRun(INT_ID, 'health_check');

      expect(mockPost).toHaveBeenCalledWith(`/integrations/${INT_ID}/managed/health_check/run`);
      expect(result).toEqual(mockData);
    });
  });

  describe('getManagedRuns', () => {
    const mockRuns = [
      { task_run_id: 'run-001', status: 'completed', created_at: '2024-01-01T00:00:00Z' },
    ];

    it('should fetch runs for a managed resource', async () => {
      const params = { limit: 10 };
      mockGet.mockResolvedValue({ data: { data: mockRuns, meta: { request_id: 'test' } } });

      const result = await integrationsApi.getManagedRuns(INT_ID, 'health_check', params);

      expect(mockGet).toHaveBeenCalledWith(`/integrations/${INT_ID}/managed/health_check/runs`, {
        params,
      });
      expect(result).toEqual(mockRuns);
    });
  });

  describe('updateManagedSchedule', () => {
    it('should update a managed resource schedule', async () => {
      const body = { schedule_value: '5m', enabled: true };
      const mockData = {
        schedule_id: SCHEDULE_ID,
        schedule_type: 'every',
        ...body,
        timezone: 'UTC',
      };
      mockPut.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.updateManagedSchedule(INT_ID, 'health_check', body);

      expect(mockPut).toHaveBeenCalledWith(
        `/integrations/${INT_ID}/managed/health_check/schedule`,
        body
      );
      expect(result).toEqual(mockData);
    });
  });

  describe('deleteSchedule', () => {
    it('should delete a schedule by ID', async () => {
      mockDelete.mockResolvedValue({ data: null });

      await integrationsApi.deleteSchedule(SCHEDULE_ID);

      expect(mockDelete).toHaveBeenCalledWith(`/schedules/${SCHEDULE_ID}`);
    });
  });

  describe('createCredential', () => {
    it('should create a credential', async () => {
      const body = {
        provider: 'splunk',
        account: 'admin',
        secret: { api_key: 'abc123' },
      };
      const mockData = { credential_id: CRED_ID, ...body };
      mockPost.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.createCredential(body);

      expect(mockPost).toHaveBeenCalledWith('/credentials', body);
      expect(result).toEqual(mockData);
    });
  });

  // ==================== Error Path Tests ====================

  describe('error paths', () => {
    it('createIntegration should propagate 409 duplicate', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 409,
          data: {
            type: PROBLEM_TYPE,
            title: 'Conflict',
            status: 409,
            detail: 'Integration ID already exists',
            request_id: 'r-1',
          },
        },
      });

      await expect(
        integrationsApi.createIntegration({
          integration_id: INT_ID,
          integration_type: 'splunk',
          name: 'Dup',
          settings: {},
        })
      ).rejects.toMatchObject({
        response: { status: 409, data: { detail: 'Integration ID already exists' } },
      });
    });

    it('createIntegration should propagate 422 validation error', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 422,
          data: {
            type: PROBLEM_TYPE,
            title: 'Validation Error',
            status: 422,
            detail: 'Request validation failed',
            errors: [
              { loc: ['body', 'integration_type'], msg: 'Field required', type: 'missing' },
              {
                loc: ['body', 'name'],
                msg: 'String should have at least 1 character',
                type: 'string_too_short',
              },
            ],
            request_id: 'r-2',
          },
        },
      });

      await expect(integrationsApi.createIntegration({} as never)).rejects.toMatchObject({
        response: { status: 422, data: { errors: expect.any(Array) } },
      });
    });

    it('getIntegration should propagate 404', async () => {
      mockGet.mockRejectedValue({
        response: {
          status: 404,
          data: {
            type: PROBLEM_TYPE,
            title: 'Not Found',
            status: 404,
            detail: 'Integration not found',
            request_id: 'r-3',
          },
        },
      });

      await expect(integrationsApi.getIntegration('missing')).rejects.toMatchObject({
        response: { status: 404 },
      });
    });

    it('deleteIntegration should propagate 404', async () => {
      mockDelete.mockRejectedValue({
        response: {
          status: 404,
          data: {
            type: PROBLEM_TYPE,
            title: 'Not Found',
            status: 404,
            detail: 'Integration not found',
            request_id: 'r-4',
          },
        },
      });

      await expect(integrationsApi.deleteIntegration('missing')).rejects.toMatchObject({
        response: { status: 404 },
      });
    });

    it('createCredential should propagate 422 validation error', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 422,
          data: {
            type: PROBLEM_TYPE,
            title: 'Validation Error',
            status: 422,
            detail: 'Request validation failed',
            errors: [{ loc: ['body', 'provider'], msg: 'Field required', type: 'missing' }],
            request_id: 'r-5',
          },
        },
      });

      await expect(integrationsApi.createCredential({} as never)).rejects.toMatchObject({
        response: { status: 422 },
      });
    });

    it('triggerManagedRun should propagate 500', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 500,
          data: {
            type: PROBLEM_TYPE,
            title: 'Internal Server Error',
            status: 500,
            detail: 'Internal server error',
            request_id: 'r-6',
          },
        },
      });

      await expect(integrationsApi.triggerManagedRun(INT_ID, 'health_check')).rejects.toMatchObject(
        {
          response: { status: 500 },
        }
      );
    });
  });

  describe('getCredentials', () => {
    it('should fetch all credentials', async () => {
      const mockData = [{ credential_id: CRED_ID, provider: 'splunk' }];
      mockGet.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await integrationsApi.getCredentials();

      expect(mockGet).toHaveBeenCalledWith('/credentials');
      expect(result).toEqual(mockData);
    });
  });
});
