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

import * as settingsApi from '../settingsApi';

const GROUP_ID = 'ag-123';
const RULE_ID = 'rule-456';
const WORKFLOW_ID = 'wf-789';
const TENANT_ID = 't-1';
const AUDIT_ENDPOINT = '/audit-trail';
const TIMESTAMP = '2025-01-15T10:30:00Z';
// eslint-disable-next-line sonarjs/no-hardcoded-ip -- test-only fixture
const TEST_IP = '10.0.0.1';

describe('settingsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ==================== Analysis Groups ====================

  describe('getAnalysisGroups', () => {
    it('should fetch all analysis groups via GET /analysis-groups', async () => {
      const groupObj = {
        id: GROUP_ID,
        tenant_id: TENANT_ID,
        title: 'Malware',
        created_at: TIMESTAMP,
      };
      mockGet.mockResolvedValue({
        data: {
          data: [groupObj],
          meta: { total: 1 },
        },
      });

      const result = await settingsApi.getAnalysisGroups();

      expect(mockGet).toHaveBeenCalledWith('/analysis-groups');
      expect(result).toEqual({ analysis_groups: [groupObj], total: 1 });
    });
  });

  describe('getAnalysisGroup', () => {
    it('should fetch a single analysis group via GET /analysis-groups/:id', async () => {
      const groupObj = {
        id: GROUP_ID,
        tenant_id: TENANT_ID,
        title: 'Malware',
        created_at: TIMESTAMP,
      };
      mockGet.mockResolvedValue({
        data: {
          data: groupObj,
          meta: { request_id: 'test' },
        },
      });

      const result = await settingsApi.getAnalysisGroup(GROUP_ID);

      expect(mockGet).toHaveBeenCalledWith(`/analysis-groups/${GROUP_ID}`);
      expect(result).toEqual(groupObj);
    });
  });

  describe('createAnalysisGroup', () => {
    it('should create an analysis group via POST /analysis-groups', async () => {
      const createData = { title: 'Phishing' };
      const responseObj = {
        id: 'ag-new',
        tenant_id: TENANT_ID,
        title: 'Phishing',
        created_at: TIMESTAMP,
      };
      mockPost.mockResolvedValue({
        data: {
          data: responseObj,
          meta: { request_id: 'test' },
        },
      });

      const result = await settingsApi.createAnalysisGroup(createData);

      expect(mockPost).toHaveBeenCalledWith('/analysis-groups', createData);
      expect(result).toEqual(responseObj);
    });
  });

  describe('deleteAnalysisGroup', () => {
    it('should delete an analysis group via DELETE /analysis-groups/:id', async () => {
      mockDelete.mockResolvedValue({ data: null });

      await settingsApi.deleteAnalysisGroup(GROUP_ID);

      expect(mockDelete).toHaveBeenCalledWith(`/analysis-groups/${GROUP_ID}`);
    });
  });

  // ==================== Alert Routing Rules ====================

  describe('getAlertRoutingRules', () => {
    it('should fetch all routing rules via GET /alert-routing-rules', async () => {
      const ruleObj = {
        id: RULE_ID,
        tenant_id: TENANT_ID,
        analysis_group_id: GROUP_ID,
        workflow_id: WORKFLOW_ID,
        created_at: TIMESTAMP,
      };
      mockGet.mockResolvedValue({
        data: {
          data: [ruleObj],
          meta: { total: 1 },
        },
      });

      const result = await settingsApi.getAlertRoutingRules();

      expect(mockGet).toHaveBeenCalledWith('/alert-routing-rules');
      expect(result).toEqual({ rules: [ruleObj], total: 1 });
    });
  });

  describe('createAlertRoutingRule', () => {
    it('should create a routing rule via POST /alert-routing-rules', async () => {
      const createData = { analysis_group_id: GROUP_ID, workflow_id: WORKFLOW_ID };
      const responseObj = {
        id: RULE_ID,
        tenant_id: TENANT_ID,
        ...createData,
        created_at: TIMESTAMP,
      };
      mockPost.mockResolvedValue({
        data: {
          data: responseObj,
          meta: { request_id: 'test' },
        },
      });

      const result = await settingsApi.createAlertRoutingRule(createData);

      expect(mockPost).toHaveBeenCalledWith('/alert-routing-rules', createData);
      expect(result).toEqual(responseObj);
    });
  });

  describe('deleteAlertRoutingRule', () => {
    it('should delete a routing rule via DELETE /alert-routing-rules/:id', async () => {
      mockDelete.mockResolvedValue({ data: null });

      await settingsApi.deleteAlertRoutingRule(RULE_ID);

      expect(mockDelete).toHaveBeenCalledWith(`/alert-routing-rules/${RULE_ID}`);
    });
  });

  // ==================== Error Path Tests ====================

  describe('error paths', () => {
    it('getAnalysisGroup should propagate 404', async () => {
      mockGet.mockRejectedValue({
        response: {
          status: 404,
          data: {
            type: 'about:blank',
            title: 'Not Found',
            status: 404,
            detail: 'Analysis group not found',
            request_id: 'r-1',
          },
        },
      });

      await expect(settingsApi.getAnalysisGroup('missing')).rejects.toMatchObject({
        response: { status: 404 },
      });
    });

    it('createAnalysisGroup should propagate 422 validation error', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 422,
          data: {
            type: 'about:blank',
            title: 'Validation Error',
            status: 422,
            detail: 'Request validation failed',
            errors: [{ loc: ['body', 'title'], msg: 'Field required', type: 'missing' }],
            request_id: 'r-2',
          },
        },
      });

      await expect(settingsApi.createAnalysisGroup({ title: '' } as any)).rejects.toMatchObject({
        response: {
          status: 422,
          data: {
            errors: expect.arrayContaining([expect.objectContaining({ msg: 'Field required' })]),
          },
        },
      });
    });

    it('createAlertRoutingRule should propagate 409 duplicate', async () => {
      mockPost.mockRejectedValue({
        response: {
          status: 409,
          data: {
            type: 'about:blank',
            title: 'Conflict',
            status: 409,
            detail: 'Routing rule already exists for this group',
            request_id: 'r-3',
          },
        },
      });

      await expect(
        settingsApi.createAlertRoutingRule({
          analysis_group_id: GROUP_ID,
          workflow_id: WORKFLOW_ID,
        })
      ).rejects.toMatchObject({
        response: { status: 409 },
      });
    });

    it('deleteAnalysisGroup should propagate 404', async () => {
      mockDelete.mockRejectedValue({
        response: {
          status: 404,
          data: {
            type: 'about:blank',
            title: 'Not Found',
            status: 404,
            detail: 'Analysis group not found',
            request_id: 'r-4',
          },
        },
      });

      await expect(settingsApi.deleteAnalysisGroup('missing')).rejects.toMatchObject({
        response: { status: 404 },
      });
    });
  });

  // ==================== Audit Trail ====================

  describe('getAuditLogs', () => {
    const backendItem = {
      id: 'audit-001',
      actor_id: 'user-1',
      actor_type: 'user',
      source: 'ui',
      action: 'create_integration',
      resource_type: 'integration',
      resource_id: 'int-5',
      details: {
        user_name: 'John Doe',
        component: 'IntegrationSettings',
        entity_name: 'Splunk Prod',
        result: 'success',
      },
      ip_address: TEST_IP,
      user_agent: 'Mozilla/5.0',
      request_id: 'req-abc',
      tenant_id: TENANT_ID,
      created_at: TIMESTAMP,
    };

    it('should convert page/page_size to offset/limit and transform the response', async () => {
      mockGet.mockResolvedValue({
        data: {
          data: [backendItem],
          meta: {
            total: 25,
            limit: 10,
            offset: 0,
          },
        },
      });

      const result = await settingsApi.getAuditLogs({ page: 1, page_size: 10 });

      // Verify pagination conversion: page=1, page_size=10 -> offset=0, limit=10
      expect(mockGet).toHaveBeenCalledWith(AUDIT_ENDPOINT, {
        params: { offset: 0, limit: 10 },
      });

      // Verify response transformation
      expect(result.activities).toHaveLength(1);
      const activity = result.activities[0];
      expect(activity.id).toBe('audit-001');
      expect(activity.timestamp).toBe(TIMESTAMP);
      expect(activity.user_id).toBe('user-1');
      expect(activity.user_name).toBe('John Doe');
      expect(activity.source).toBe('ui');
      expect(activity.action_type).toBe('create'); // inferred from "create_integration"
      expect(activity.action).toBe('create_integration');
      expect(activity.component).toBe('IntegrationSettings');
      expect(activity.entity_type).toBe('integration');
      expect(activity.entity_id).toBe('int-5');
      expect(activity.entity_name).toBe('Splunk Prod');
      expect(activity.result).toBe('success');
      expect(activity.ip_address).toBe(TEST_IP);
      expect(activity.user_agent).toBe('Mozilla/5.0');

      // Verify pagination metadata
      expect(result.total).toBe(25);
      expect(result.page).toBe(1);
      expect(result.page_size).toBe(10);
      expect(result.total_pages).toBe(3); // ceil(25/10)
    });

    it('should compute offset correctly for page 2', async () => {
      mockGet.mockResolvedValue({
        data: {
          data: [],
          meta: {
            total: 25,
            limit: 10,
            offset: 10,
          },
        },
      });

      const result = await settingsApi.getAuditLogs({ page: 2, page_size: 10 });

      // page=2, page_size=10 -> offset = (2-1)*10 = 10, limit=10
      expect(mockGet).toHaveBeenCalledWith(AUDIT_ENDPOINT, {
        params: { offset: 10, limit: 10 },
      });

      // Verify reverse pagination: offset=10, limit=10 -> page=2
      expect(result.page).toBe(2);
      expect(result.page_size).toBe(10);
      expect(result.total_pages).toBe(3);
    });

    it('should infer action_type from action string patterns', async () => {
      const makeItem = (action: string) => ({
        ...backendItem,
        action,
        details: null,
      });

      mockGet.mockResolvedValue({
        data: {
          data: [
            makeItem('update_settings'),
            makeItem('delete_workflow'),
            makeItem('execute_task'),
            makeItem('login_sso'),
            makeItem('view_dashboard'),
          ],
          meta: {
            total: 5,
            limit: 50,
            offset: 0,
          },
        },
      });

      const result = await settingsApi.getAuditLogs();
      const types = result.activities.map((a) => a.action_type);

      expect(types).toEqual(['update', 'delete', 'execute', 'navigate', 'read']);
    });

    it('should prefer action_type from details over inference', async () => {
      const itemWithExplicitType = {
        ...backendItem,
        action: 'some_custom_action',
        details: { action_type: 'execute' },
      };
      mockGet.mockResolvedValue({
        data: {
          data: [itemWithExplicitType],
          meta: {
            total: 1,
            limit: 10,
            offset: 0,
          },
        },
      });

      const result = await settingsApi.getAuditLogs();

      expect(result.activities[0].action_type).toBe('execute');
    });

    it('should pass through non-pagination params and strip page/page_size', async () => {
      mockGet.mockResolvedValue({
        data: {
          data: [],
          meta: { total: 0, limit: 20, offset: 0 },
        },
      });

      await settingsApi.getAuditLogs({
        page: 1,
        page_size: 20,
        user_id: 'user-1',
        action_type: 'create',
        entity_type: 'workflow',
      });

      expect(mockGet).toHaveBeenCalledWith(AUDIT_ENDPOINT, {
        params: {
          offset: 0,
          limit: 20,
          user_id: 'user-1',
          action_type: 'create',
          entity_type: 'workflow',
        },
      });
    });
  });

  describe('createAuditLog', () => {
    it('should transform frontend payload to backend format with source mapping', async () => {
      const frontendData = {
        actor_id: 'user-1',
        user_name: 'Jane Smith',
        session_id: 'sess-abc',
        source: 'UI' as const,
        action_type: 'create' as const,
        action: 'create_workflow',
        component: 'WorkflowBuilder',
        method: 'handleSave',
        route: '/workflows/new',
        entity_type: 'workflow',
        entity_id: 'wf-new',
        entity_name: 'My Workflow',
        result: 'success' as const,
        page_title: 'Workflow Builder',
        duration_ms: 1500,
        metadata: { extra_field: 'value' },
      };

      const responseObj = {
        id: 'audit-new',
        timestamp: TIMESTAMP,
        user_id: 'user-1',
        user_name: 'Jane Smith',
        action_type: 'create',
        action: 'create_workflow',
        component: 'WorkflowBuilder',
      };
      mockPost.mockResolvedValue({
        data: {
          data: responseObj,
          meta: { request_id: 'test' },
        },
      });

      const result = await settingsApi.createAuditLog(frontendData);

      expect(mockPost).toHaveBeenCalledWith(
        AUDIT_ENDPOINT,
        expect.objectContaining({
          actor_type: 'user',
          source: 'ui', // 'UI' -> 'ui'
          action: 'create_workflow',
          resource_type: 'workflow',
          resource_id: 'wf-new',
          details: expect.objectContaining({
            action_type: 'create',
            user_name: 'Jane Smith',
            session_id: 'sess-abc',
            component: 'WorkflowBuilder',
            method: 'handleSave',
            route: '/workflows/new',
            entity_name: 'My Workflow',
            result: 'success',
            page_title: 'Workflow Builder',
            duration_ms: 1500,
            extra_field: 'value', // from metadata spread
          }),
        })
      );
      expect(result).toEqual(responseObj);
    });

    it('should map API source to rest_api', async () => {
      const frontendData = {
        actor_id: 'user-1',
        user_name: 'Bot',
        source: 'API' as const,
        action_type: 'execute' as const,
        action: 'run_script',
        component: 'ScriptRunner',
      };
      mockPost.mockResolvedValue({
        data: {
          data: { id: 'audit-api' },
          meta: { request_id: 'test' },
        },
      });

      await settingsApi.createAuditLog(frontendData);

      const postedPayload = mockPost.mock.calls[0][1];
      expect(postedPayload.source).toBe('rest_api'); // 'API' -> 'rest_api'
    });

    it('should set source to undefined when not provided', async () => {
      const frontendData = {
        actor_id: 'user-1',
        user_name: 'System',
        action_type: 'read' as const,
        action: 'view_dashboard',
        component: 'Dashboard',
      };
      mockPost.mockResolvedValue({
        data: {
          data: { id: 'audit-none' },
          meta: { request_id: 'test' },
        },
      });

      await settingsApi.createAuditLog(frontendData);

      const postedPayload = mockPost.mock.calls[0][1];
      expect(postedPayload.source).toBeUndefined();
    });
  });
});
