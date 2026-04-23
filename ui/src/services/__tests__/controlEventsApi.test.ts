import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { mockGet, mockPost, mockPatch, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: mockGet,
      post: mockPost,
      put: vi.fn(),
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

import * as controlEventsApi from '../controlEventsApi';

const RULE_ID = 'rule-abc-123';
const EVENT_ID = 'evt-xyz-456';
const CHANNEL_NAME = 'alert.created';
const CREATED_AT = '2025-01-01T00:00:00Z';

describe('controlEventsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getControlEventChannels', () => {
    it('should fetch channels via GET /control-event-channels', async () => {
      const channelObj = {
        channel: CHANNEL_NAME,
        type: 'system',
        description: 'Fired when an alert is created',
        payload_fields: ['alert_id', 'severity'],
      };
      // Sifnos envelope: { data: [...], meta: { total, ... } }
      mockGet.mockResolvedValue({
        data: {
          data: [channelObj],
          meta: { total: 1 },
        },
      });

      const result = await controlEventsApi.getControlEventChannels();

      expect(mockGet).toHaveBeenCalledWith('/control-event-channels');
      expect(result).toEqual({ channels: [channelObj], total: 1 });
    });
  });

  describe('getControlEventRules', () => {
    it('should fetch rules with optional filter params', async () => {
      const ruleObj = {
        id: RULE_ID,
        tenant_id: 't-1',
        name: 'My Rule',
        channel: CHANNEL_NAME,
        target_type: 'task',
        target_id: 'task-1',
        enabled: true,
        config: {},
        created_at: CREATED_AT,
      };
      const params = { channel: CHANNEL_NAME, enabled_only: true };
      // Sifnos envelope: { data: [...], meta: { total, ... } }
      mockGet.mockResolvedValue({
        data: {
          data: [ruleObj],
          meta: { total: 1 },
        },
      });

      const result = await controlEventsApi.getControlEventRules(params);

      expect(mockGet).toHaveBeenCalledWith('/control-event-rules', { params });
      expect(result).toEqual({ rules: [ruleObj], total: 1 });
    });

    it('should fetch rules without params', async () => {
      // Sifnos envelope: { data: [...], meta: { total, ... } }
      mockGet.mockResolvedValue({
        data: {
          data: [],
          meta: { total: 0 },
        },
      });

      const result = await controlEventsApi.getControlEventRules();

      expect(mockGet).toHaveBeenCalledWith('/control-event-rules', { params: undefined });
      expect(result).toEqual({ rules: [], total: 0 });
    });
  });

  describe('createControlEventRule', () => {
    it('should create a rule via POST /control-event-rules', async () => {
      const createData = {
        name: 'New Rule',
        channel: CHANNEL_NAME,
        target_type: 'workflow' as const,
        target_id: 'wf-42',
        enabled: true,
        config: { threshold: 5 },
      };
      const createdObj = {
        id: RULE_ID,
        tenant_id: 't-1',
        ...createData,
        created_at: CREATED_AT,
      };
      // Sifnos envelope: { data: itemObject, meta: { request_id, ... } }
      mockPost.mockResolvedValue({
        data: {
          data: createdObj,
          meta: { request_id: 'test' },
        },
      });

      const result = await controlEventsApi.createControlEventRule(createData);

      expect(mockPost).toHaveBeenCalledWith('/control-event-rules', createData);
      expect(result).toEqual(createdObj);
    });
  });

  describe('updateControlEventRule', () => {
    it('should patch a rule via PATCH /control-event-rules/:id', async () => {
      const patchData = { enabled: false, name: 'Renamed Rule' };
      const updatedObj = {
        id: RULE_ID,
        tenant_id: 't-1',
        name: 'Renamed Rule',
        channel: CHANNEL_NAME,
        target_type: 'task',
        target_id: 'task-1',
        enabled: false,
        config: {},
        created_at: CREATED_AT,
        updated_at: '2025-02-01T00:00:00Z',
      };
      // Sifnos envelope: { data: itemObject, meta: { request_id, ... } }
      mockPatch.mockResolvedValue({
        data: {
          data: updatedObj,
          meta: { request_id: 'test' },
        },
      });

      const result = await controlEventsApi.updateControlEventRule(RULE_ID, patchData);

      expect(mockPatch).toHaveBeenCalledWith(`/control-event-rules/${RULE_ID}`, patchData);
      expect(result).toEqual(updatedObj);
    });
  });

  describe('deleteControlEventRule', () => {
    it('should delete a rule via DELETE /control-event-rules/:id', async () => {
      mockDelete.mockResolvedValue({ data: null });

      await controlEventsApi.deleteControlEventRule(RULE_ID);

      expect(mockDelete).toHaveBeenCalledWith(`/control-event-rules/${RULE_ID}`);
    });
  });

  describe('getControlEvents', () => {
    it('should fetch events with optional filter params', async () => {
      const eventObj = {
        id: EVENT_ID,
        tenant_id: 't-1',
        channel: CHANNEL_NAME,
        payload: { alert_id: 'a-1' },
        status: 'completed',
        retry_count: 0,
        created_at: CREATED_AT,
      };
      const params = { channel: CHANNEL_NAME, status: 'completed' as const, limit: 50 };
      // Sifnos envelope: { data: [...], meta: { total, ... } }
      mockGet.mockResolvedValue({
        data: {
          data: [eventObj],
          meta: { total: 1 },
        },
      });

      const result = await controlEventsApi.getControlEvents(params);

      expect(mockGet).toHaveBeenCalledWith('/control-events', { params });
      expect(result).toEqual({ events: [eventObj], total: 1 });
    });
  });

  // ==================== Error Path Tests ====================

  describe('error paths', () => {
    it('createControlEventRule should propagate 422 validation error', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 422,
          data: {
            type: 'about:blank',
            title: 'Validation Error',
            status: 422,
            detail: 'Request validation failed',
            errors: [{ loc: ['body', 'channel'], msg: 'Field required', type: 'missing' }],
            request_id: 'r-1',
          },
        },
      });

      await expect(controlEventsApi.createControlEventRule({} as never)).rejects.toMatchObject({
        response: {
          status: 422,
          data: {
            errors: expect.arrayContaining([expect.objectContaining({ msg: 'Field required' })]),
          },
        },
      });
    });

    it('deleteControlEventRule should propagate 404', async () => {
      mockDelete.mockRejectedValue({
        response: {
          status: 404,
          data: {
            type: 'about:blank',
            title: 'Not Found',
            status: 404,
            detail: 'Rule not found',
            request_id: 'r-2',
          },
        },
      });

      await expect(controlEventsApi.deleteControlEventRule('missing')).rejects.toMatchObject({
        response: { status: 404 },
      });
    });

    it('getControlEventRules should propagate 503', async () => {
      mockGet.mockRejectedValue({
        response: {
          status: 503,
          data: {
            type: 'about:blank',
            title: 'Service Unavailable',
            status: 503,
            detail: 'Database temporarily unavailable. Please retry.',
            request_id: 'r-3',
          },
        },
      });

      await expect(controlEventsApi.getControlEventRules()).rejects.toMatchObject({
        response: { status: 503 },
      });
    });
  });

  describe('createControlEvent', () => {
    it('should fire an event via POST /control-events', async () => {
      const createData = {
        channel: CHANNEL_NAME,
        payload: { alert_id: 'a-99', severity: 'high' },
      };
      const createdObj = {
        id: EVENT_ID,
        tenant_id: 't-1',
        channel: CHANNEL_NAME,
        payload: createData.payload,
        status: 'pending',
        retry_count: 0,
        created_at: CREATED_AT,
      };
      // Sifnos envelope: { data: itemObject, meta: { request_id, ... } }
      mockPost.mockResolvedValue({
        data: {
          data: createdObj,
          meta: { request_id: 'test' },
        },
      });

      const result = await controlEventsApi.createControlEvent(createData);

      expect(mockPost).toHaveBeenCalledWith('/control-events', createData);
      expect(result).toEqual(createdObj);
    });
  });
});
