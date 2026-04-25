import type {
  IntegrationTypeInfo,
  IntegrationInstance,
  IntegrationTool,
  IntegrationAction,
  ManagedRun,
  ManagedSchedule,
  ManagedResourceBlock,
  ProvisionFreeResponse,
  Schedule,
  Credential,
} from '../types/integration';

import { withApi, fetchOne, mutateOne, apiDelete } from './apiClient';

// Re-export types for consumers
export type {
  IntegrationTypeInfo,
  IntegrationInstance,
  IntegrationTool,
  IntegrationAction,
  ManagedRun,
  ManagedSchedule,
  ManagedResourceBlock,
  ProvisionFreeResponse,
  Schedule,
  Credential,
};

// Named types for inline return shapes
export type IntegrationHealth = {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  last_success_at?: string;
  success_rate_24h?: number;
  recent_failures?: number;
  message?: string;
};

export type IntegrationCredentialResult = {
  credential_id: string;
  tenant_id: string;
  provider: string;
  account: string;
  is_primary: boolean;
  purpose?: string;
  key_version: number;
  created_at: string;
};

export type ManagedRunResult = {
  task_run_id: string;
  status: string;
  task_id: string;
  resource_key: string;
};

// Integrations API
// Get all available tools (native + integration) with parameter schemas
export const getAllTools = async (): Promise<{ tools: IntegrationTool[]; total: number }> =>
  withApi('getAllTools', 'fetching all tools for autocomplete', () =>
    fetchOne<{ tools: IntegrationTool[]; total: number }>('/integrations/tools/all')
  );

// Get available integration types from registry
export const getIntegrationTypes = async (): Promise<IntegrationTypeInfo[]> =>
  withApi('getIntegrationTypes', 'fetching integration types from registry', () =>
    fetchOne<IntegrationTypeInfo[]>('/integrations/registry')
  );

// Get detailed information for a specific integration type
export const getIntegrationType = async (integrationType: string): Promise<IntegrationTypeInfo> =>
  withApi('getIntegrationType', 'fetching integration type details', () =>
    fetchOne<IntegrationTypeInfo>(`/integrations/registry/${integrationType}`)
  );

// Get actions for a specific integration type
export const getIntegrationActions = async (
  integrationType: string
): Promise<IntegrationAction[]> =>
  withApi('getIntegrationActions', 'fetching integration actions', () =>
    fetchOne<IntegrationAction[]>(`/integrations/registry/${integrationType}/actions`)
  );

export const getIntegrations = async (
  params: {
    integration_type?: string;
    enabled?: boolean;
    limit?: number;
    skip?: number;
  } = {}
): Promise<IntegrationInstance[]> =>
  withApi('getIntegrations', 'fetching integrations', () =>
    fetchOne<IntegrationInstance[]>('/integrations', { params })
  );

export const createIntegration = async (data: {
  integration_id: string;
  integration_type: string;
  name: string;
  description?: string;
  enabled?: boolean;
  settings: Record<string, unknown>;
  credential_id?: string;
}): Promise<IntegrationInstance> =>
  withApi('createIntegration', 'creating integration', () =>
    mutateOne<IntegrationInstance>('post', '/integrations', data)
  );

export const getIntegration = async (integrationId: string): Promise<IntegrationInstance> =>
  withApi('getIntegration', 'fetching integration', () =>
    fetchOne<IntegrationInstance>(`/integrations/${integrationId}`)
  );

export const updateIntegration = async (
  integrationId: string,
  data: Partial<{
    name: string;
    description?: string;
    enabled?: boolean;
    settings: Record<string, unknown>;
    credential_id?: string;
  }>
): Promise<IntegrationInstance> =>
  withApi('updateIntegration', 'updating integration', () =>
    mutateOne<IntegrationInstance>('patch', `/integrations/${integrationId}`, data)
  );

export const deleteIntegration = async (integrationId: string): Promise<void> =>
  withApi('deleteIntegration', 'deleting integration', () =>
    apiDelete(`/integrations/${integrationId}`)
  );

export const enableIntegration = async (integrationId: string): Promise<IntegrationInstance> =>
  withApi('enableIntegration', 'enabling integration', () =>
    mutateOne<IntegrationInstance>('post', `/integrations/${integrationId}/enable`)
  );

export const disableIntegration = async (integrationId: string): Promise<IntegrationInstance> =>
  withApi('disableIntegration', 'disabling integration', () =>
    mutateOne<IntegrationInstance>('post', `/integrations/${integrationId}/disable`)
  );

export const getIntegrationHealth = async (integrationId: string): Promise<IntegrationHealth> =>
  withApi('getIntegrationHealth', 'fetching integration health', () =>
    fetchOne<IntegrationHealth>(`/integrations/${integrationId}/health`)
  );

// Provision all free integrations (no API key required) for this tenant.
// Idempotent: skips integrations that already exist.
export const provisionFreeIntegrations = async (): Promise<ProvisionFreeResponse> =>
  withApi('provisionFreeIntegrations', 'provisioning free integrations', () =>
    mutateOne<ProvisionFreeResponse>('post', '/integrations/provision-free')
  );

// ---------------------------------------------------------------------------
// Managed Resources (Project Symi)
// ---------------------------------------------------------------------------

export const getManagedResources = async (
  integrationId: string
): Promise<Record<string, ManagedResourceBlock>> =>
  withApi('getManagedResources', 'fetching managed resources', () =>
    fetchOne<Record<string, ManagedResourceBlock>>(`/integrations/${integrationId}/managed`)
  );

export const getManagedSchedule = async (
  integrationId: string,
  resourceKey: string
): Promise<ManagedSchedule> =>
  withApi('getManagedSchedule', 'fetching managed schedule', () =>
    fetchOne<ManagedSchedule>(`/integrations/${integrationId}/managed/${resourceKey}/schedule`)
  );

export const updateManagedSchedule = async (
  integrationId: string,
  resourceKey: string,
  data: { schedule_value?: string; enabled?: boolean }
): Promise<ManagedSchedule> =>
  withApi('updateManagedSchedule', 'updating managed schedule', () =>
    mutateOne<ManagedSchedule>(
      'put',
      `/integrations/${integrationId}/managed/${resourceKey}/schedule`,
      data
    )
  );

export const triggerManagedRun = async (
  integrationId: string,
  resourceKey: string,
  params?: Record<string, unknown>
): Promise<ManagedRunResult> =>
  withApi('triggerManagedRun', 'triggering managed run', () =>
    mutateOne<ManagedRunResult>(
      'post',
      `/integrations/${integrationId}/managed/${resourceKey}/run`,
      params ? { params } : undefined
    )
  );

export const getManagedRuns = async (
  integrationId: string,
  resourceKey: string,
  params: { skip?: number; limit?: number } = {}
): Promise<ManagedRun[]> =>
  withApi('getManagedRuns', 'fetching managed runs', () =>
    fetchOne<ManagedRun[]>(`/integrations/${integrationId}/managed/${resourceKey}/runs`, { params })
  );

// ---------------------------------------------------------------------------
// Generic Schedules API
// ---------------------------------------------------------------------------

export const getSchedules = async (
  params: { target_type?: string; integration_id?: string } = {}
): Promise<Schedule[]> =>
  withApi('getSchedules', 'fetching schedules', () =>
    fetchOne<Schedule[]>('/schedules', { params })
  );

export const deleteSchedule = async (scheduleId: string): Promise<void> =>
  withApi('deleteSchedule', 'deleting schedule', () => apiDelete(`/schedules/${scheduleId}`));

// ---------------------------------------------------------------------------
// Credential Management
// ---------------------------------------------------------------------------

export const createCredential = async (data: {
  provider: string;
  account: string;
  secret: Record<string, unknown>;
  credential_metadata?: Record<string, unknown>;
}): Promise<Credential> =>
  withApi('createCredential', 'creating credential', () =>
    mutateOne<Credential>('post', '/credentials', data)
  );

export const getCredentials = async (): Promise<Credential[]> =>
  withApi('getCredentials', 'fetching credentials', () => fetchOne<Credential[]>('/credentials'));

export const getCredential = async (credentialId: string): Promise<Credential> =>
  withApi('getCredential', 'fetching credential', () =>
    fetchOne<Credential>(`/credentials/${credentialId}`)
  );

export type IntegrationCredentialLink = {
  credential_id: string;
  provider: string;
  account: string;
  is_primary: boolean;
  purpose?: string;
  created_at: string;
};

export const getIntegrationCredentials = async (
  integrationId: string
): Promise<IntegrationCredentialLink[]> =>
  withApi('getIntegrationCredentials', 'fetching integration credentials', () =>
    fetchOne<IntegrationCredentialLink[]>(`/credentials/integrations/${integrationId}`)
  );

export const deleteCredential = async (credentialId: string): Promise<void> =>
  withApi('deleteCredential', 'deleting credential', () =>
    apiDelete(`/credentials/${credentialId}`)
  );

export const associateCredentialWithIntegration = async (
  integrationId: string,
  credentialId: string,
  isPrimary: boolean = true
): Promise<Record<string, unknown>> =>
  withApi('associateCredentialWithIntegration', 'associating credential with integration', () =>
    mutateOne<Record<string, unknown>>(
      'post',
      `/credentials/integrations/${integrationId}/associate`,
      { credential_id: credentialId, is_primary: isPrimary }
    )
  );

// New combined endpoint to create and associate credential in one step
export const createIntegrationCredential = async (
  integrationId: string,
  data: {
    provider: string;
    account: string;
    secret: Record<string, unknown>;
    is_primary?: boolean;
    purpose?: string;
    credential_metadata?: Record<string, unknown>;
  }
): Promise<IntegrationCredentialResult> =>
  withApi('createIntegrationCredential', 'creating and associating credential', () =>
    mutateOne<IntegrationCredentialResult>(
      'post',
      `/integrations/${integrationId}/credentials`,
      data
    )
  );
