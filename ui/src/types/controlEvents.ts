// Control Event Channel
export interface ControlEventChannel {
  channel: string;
  type: 'system' | 'configured';
  description: string | null;
  payload_fields: string[];
}

export interface ControlEventChannelListResponse {
  channels: ControlEventChannel[];
  total: number;
}

// Control Event Rule — re-exported from generated types
export type { ControlEventRule, ControlEventRuleCreate } from './api';

export interface ControlEventRulePatch {
  name?: string;
  channel?: string;
  target_type?: string;
  target_id?: string;
  enabled?: boolean;
  config?: Record<string, unknown>;
}

export interface ControlEventRuleListResponse {
  rules: import('./api').ControlEventRule[];
  total: number;
}

// Control Event (history)
export type ControlEventStatus = 'pending' | 'claimed' | 'completed' | 'failed';

// ControlEvent & ControlEventCreate — re-exported from generated types
export type { ControlEvent, ControlEventCreate } from './api';

export interface ControlEventListResponse {
  events: import('./api').ControlEvent[];
  total: number;
}

export interface ControlEventListParams {
  channel?: string;
  status?: ControlEventStatus;
  limit?: number;
  since_days?: number;
}
