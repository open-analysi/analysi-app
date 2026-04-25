import {
  AuditActionType,
  AuditLog,
  AuditLogCreate,
  AuditLogResponse,
  AuditLogQueryParams,
} from '../types/audit';
import {
  AnalysisGroup,
  AnalysisGroupCreate,
  AnalysisGroupListResponse,
  AlertRoutingRule,
  AlertRoutingRuleCreate,
  AlertRoutingRuleListResponse,
} from '../types/settings';

import {
  withApi,
  fetchOne,
  fetchList,
  mutateOne,
  apiDelete,
  backendApiClient,
  type SifnosEnvelope,
} from './apiClient';

// ==================== Analysis Groups ====================

export const getAnalysisGroups = async (): Promise<AnalysisGroupListResponse> =>
  withApi('getAnalysisGroups', 'fetching analysis groups', () =>
    fetchList<'analysis_groups', AnalysisGroup>('/analysis-groups', 'analysis_groups')
  );

export const getAnalysisGroup = async (id: string): Promise<AnalysisGroup> =>
  withApi(
    'getAnalysisGroup',
    'fetching analysis group',
    () => fetchOne<AnalysisGroup>(`/analysis-groups/${id}`),
    { entityId: id }
  );

export const createAnalysisGroup = async (data: AnalysisGroupCreate): Promise<AnalysisGroup> =>
  withApi(
    'createAnalysisGroup',
    'creating analysis group',
    () => mutateOne<AnalysisGroup>('post', '/analysis-groups', data),
    { params: { title: data.title } }
  );

export const deleteAnalysisGroup = async (id: string): Promise<void> =>
  withApi(
    'deleteAnalysisGroup',
    'deleting analysis group',
    () => apiDelete(`/analysis-groups/${id}`),
    { entityId: id }
  );

// ==================== Alert Routing Rules ====================

export const getAlertRoutingRules = async (): Promise<AlertRoutingRuleListResponse> =>
  withApi('getAlertRoutingRules', 'fetching alert routing rules', () =>
    fetchList<'rules', AlertRoutingRule>('/alert-routing-rules', 'rules')
  );

export const getAlertRoutingRule = async (id: string): Promise<AlertRoutingRule> =>
  withApi(
    'getAlertRoutingRule',
    'fetching alert routing rule',
    () => fetchOne<AlertRoutingRule>(`/alert-routing-rules/${id}`),
    { entityId: id }
  );

export const createAlertRoutingRule = async (
  data: AlertRoutingRuleCreate
): Promise<AlertRoutingRule> =>
  withApi(
    'createAlertRoutingRule',
    'creating alert routing rule',
    () => mutateOne<AlertRoutingRule>('post', '/alert-routing-rules', data),
    { params: { analysis_group_id: data.analysis_group_id, workflow_id: data.workflow_id } }
  );

export const deleteAlertRoutingRule = async (id: string): Promise<void> =>
  withApi(
    'deleteAlertRoutingRule',
    'deleting alert routing rule',
    () => apiDelete(`/alert-routing-rules/${id}`),
    { entityId: id }
  );

// ==================== Audit Trail ====================

export const getAuditLogs = async (params?: AuditLogQueryParams): Promise<AuditLogResponse> =>
  withApi(
    'getAuditLogs',
    'fetching audit logs',
    async () => {
      interface BackendAuditLog {
        id: string;
        actor_id: string;
        actor_type: string;
        source?: string | null;
        action: string;
        resource_type?: string | null;
        resource_id?: string | null;
        details?: Record<string, unknown> | null;
        ip_address?: string | null;
        user_agent?: string | null;
        request_id?: string | null;
        tenant_id: string;
        created_at: string;
      }

      // Convert frontend pagination params (page, page_size) to backend params (offset, limit)
      const backendParams: Record<string, unknown> = {};

      if (params) {
        Object.keys(params).forEach((key) => {
          if (key !== 'page' && key !== 'page_size') {
            backendParams[key] = params[key as keyof AuditLogQueryParams];
          }
        });

        if (params.page !== undefined && params.page_size !== undefined) {
          backendParams.offset = (params.page - 1) * params.page_size;
          backendParams.limit = params.page_size;
        } else if (params.page_size !== undefined) {
          backendParams.limit = params.page_size;
          backendParams.offset = 0;
        }
      }

      const response = await backendApiClient.get<SifnosEnvelope<BackendAuditLog[]>>(
        '/audit-trail',
        { params: backendParams }
      );
      const { data: items, meta } = response.data;

      // Transform backend response to match frontend expectations
      const activities: AuditLog[] = items.map((item) => {
        const details = item.details;

        let actionType: AuditActionType = 'read';
        if (details?.action_type && typeof details.action_type === 'string') {
          actionType = details.action_type as AuditActionType;
        } else if (item.action.includes('create')) {
          actionType = 'create';
        } else if (
          item.action.includes('update') ||
          item.action.includes('enable') ||
          item.action.includes('disable')
        ) {
          actionType = 'update';
        } else if (item.action.includes('delete')) {
          actionType = 'delete';
        } else if (item.action.includes('execute')) {
          actionType = 'execute';
        } else if (item.action.includes('login') || item.action.includes('logout')) {
          actionType = 'navigate';
        }

        return {
          id: item.id,
          timestamp: item.created_at,
          user_id: item.actor_id,
          user_name: (details?.user_name as string) || item.actor_id,
          session_id: details?.session_id as string | undefined,
          source: (item.source as 'ui' | 'rest_api' | 'mcp') || undefined,
          action_type: actionType,
          action: item.action,
          component: (details?.component as string) || 'System',
          method: details?.method as string | undefined,
          route: details?.route as string | undefined,
          entity_type: item.resource_type || undefined,
          entity_id: item.resource_id || undefined,
          entity_name: details?.entity_name as string | undefined,
          params: details?.params as Record<string, unknown> | undefined,
          result: (details?.result as 'success' | 'error') || 'success',
          error_message: details?.error_message as string | undefined,
          page_title: details?.page_title as string | undefined,
          duration_ms: details?.duration_ms as number | undefined,
          ip_address: item.ip_address || undefined,
          user_agent: item.user_agent || undefined,
          metadata: item.details || undefined,
        };
      });

      const limit = meta.limit ?? 20;
      const offset = meta.offset ?? 0;
      const total = meta.total ?? items.length;
      return {
        activities,
        total,
        page: Math.floor(offset / limit) + 1,
        page_size: limit,
        total_pages: Math.ceil(total / limit),
      };
    },
    { params: params as unknown as Record<string, unknown> }
  );

export const getAuditLog = async (eventId: string): Promise<AuditLog> =>
  withApi(
    'getAuditLog',
    'fetching audit log',
    () => fetchOne<AuditLog>(`/audit-trail/${eventId}`),
    { entityId: eventId, entityType: 'audit-log' }
  );

export const createAuditLog = async (data: AuditLogCreate): Promise<AuditLog> =>
  withApi(
    'createAuditLog',
    'creating audit log',
    async () => {
      // Map frontend source to backend enum
      const mapSourceToBackend = (source?: string): string | undefined => {
        if (source === 'UI') return 'ui';
        if (source === 'API') return 'rest_api';
        return undefined;
      };

      // Transform frontend format to backend format
      // Note: actor_id is NOT sent -- the backend always overrides it
      // with the authenticated user's UUID from the auth token.
      const backendPayload = {
        actor_type: 'user',
        source: mapSourceToBackend(data.source),
        action: data.action,
        resource_type: data.entity_type || null,
        resource_id: data.entity_id || null,
        user_agent: navigator.userAgent,
        details: {
          action_type: data.action_type,
          user_name: data.user_name,
          session_id: data.session_id,
          component: data.component,
          method: data.method,
          route: data.route,
          entity_name: data.entity_name,
          params: data.params,
          result: data.result,
          error_message: data.error_message,
          page_title: data.page_title,
          duration_ms: data.duration_ms,
          ...data.metadata,
        },
      };

      return mutateOne<AuditLog>('post', '/audit-trail', backendPayload);
    },
    {
      params: {
        action: data.action,
        action_type: data.action_type,
        component: data.component,
      },
    }
  );
