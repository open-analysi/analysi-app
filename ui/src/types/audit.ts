// Audit Trail Types

// Backend source values (lowercase with underscores) - used for displaying audit logs
export type AuditSource = 'ui' | 'rest_api' | 'mcp';
// Frontend source values (for creating audit logs from UI)
export type AuditSourceFrontend = 'UI' | 'API';

export type AuditActionType =
  | 'create'
  | 'read'
  | 'update'
  | 'delete'
  | 'execute'
  | 'navigate'
  | 'page_view'
  | 'page_exit'
  | 'button_click';

export interface AuditLog {
  id: string;
  timestamp: string;
  user_id: string;
  user_name: string;
  session_id?: string;

  // Source of audit log
  source?: AuditSource;

  // Action classification
  action_type: AuditActionType;
  action: string; // Specific action (e.g., "enable_integration", "analyze_alert")

  // Context
  component: string;
  method?: string;
  route?: string;

  // Entity information
  entity_type?: string; // 'integration', 'alert', 'workflow', 'task', etc.
  entity_id?: string;
  entity_name?: string;

  // Request details
  params?: Record<string, unknown>;
  result?: 'success' | 'error';
  error_message?: string;

  // UX analytics fields (for page_view, page_exit, button_click)
  page_title?: string;
  duration_ms?: number; // For page_exit events

  // Metadata
  ip_address?: string;
  user_agent?: string;
  metadata?: Record<string, unknown>;
}

export interface AuditLogCreate {
  actor_id: string;
  user_name: string;
  session_id?: string;
  source?: AuditSourceFrontend;
  action_type: AuditActionType;
  action: string;
  component: string;
  method?: string;
  route?: string;
  entity_type?: string;
  entity_id?: string;
  entity_name?: string;
  params?: Record<string, unknown>;
  result?: 'success' | 'error';
  error_message?: string;
  page_title?: string;
  duration_ms?: number;
  metadata?: Record<string, unknown>;
}

export interface AuditLogResponse {
  activities: AuditLog[];
  total: number;
  page?: number;
  page_size?: number;
  total_pages?: number;
}

export interface AuditLogQueryParams {
  page?: number;
  page_size?: number;
  user_id?: string;
  action_type?: AuditActionType;
  entity_type?: string;
  entity_id?: string;
  start_date?: string;
  end_date?: string;
  search?: string;
}
