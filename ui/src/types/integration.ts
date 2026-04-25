export type {
  Credential,
  ManagedResourceBlock,
  ManagedRun,
  ManagedSchedule,
  ProvisionFreeIntegrationResult,
  ProvisionFreeResponse,
  Schedule,
} from './api';

import type { IntegrationInstance as GeneratedIntegrationInstance } from './api';

/**
 * IntegrationInstance extends the generated type with UI-computed fields
 * that the Integrations page derives from the health endpoint and recent runs.
 */
export type IntegrationInstance = GeneratedIntegrationInstance & {
  health_status?: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  last_run_at?: string;
  last_run_status?: 'completed' | 'failed' | 'running';
};

export interface IntegrationTool {
  tool_id?: string;
  fqn: string;
  name: string;
  description?: string;
  enabled?: boolean;
  categories?: string[];
  integration_id?: string;
}

export interface IntegrationAction {
  action_id: string;
  name: string;
  description: string;
  categories: string[];
  cy_name: string;
  enabled: boolean;
  params_schema?: Record<string, unknown>;
  result_schema?: Record<string, unknown>;
}

export interface IntegrationTypeInfo {
  integration_type: string;
  display_name: string;
  actions?: IntegrationAction[];
  /** @deprecated Use `actions` instead — backend no longer returns this field */
  connectors?: Array<
    string | { connector_type?: string; display_name?: string; description?: string }
  >;
  settings_schema: Record<string, unknown>;
  description?: string;
  archetypes?: string[];
  priority?: number;
  /** @deprecated Use `actions` instead */
  tools?: IntegrationTool[];
  /** Action count returned by the registry list endpoint (when `actions` array is not included) */
  action_count?: number;
  /** @deprecated Use `actions?.length` instead */
  tool_count?: number;
  integration_id_config?: Record<string, unknown>;
  credential_schema?: Record<string, unknown>;
}

// Legacy types — used by IntegrationCard, IntegrationGroup, and mock data
export enum IntegrationStatus {
  Connected = 'connected',
  NotConnected = 'not_connected',
  Error = 'error',
}

export interface Integration {
  id: string;
  name: string;
  type: string;
  status: IntegrationStatus;
  description?: string;
  icon?: string;
  isConfigured?: boolean;
}

export interface IntegrationGroup {
  type: string;
  description: string;
  integrations: Integration[];
}
