import type {
  ControlEventChannel,
  ControlEventChannelListResponse,
  ControlEventRule,
  ControlEventRuleCreate,
  ControlEventRulePatch,
  ControlEventRuleListResponse,
  ControlEvent,
  ControlEventCreate,
  ControlEventListResponse,
  ControlEventListParams,
} from '../types/controlEvents';

import { withApi, fetchOne, fetchList, mutateOne, apiDelete } from './apiClient';

// ==================== Channels ====================

export const getControlEventChannels = async (): Promise<ControlEventChannelListResponse> =>
  withApi('getControlEventChannels', 'fetching control event channels', () =>
    fetchList<'channels', ControlEventChannel>('/control-event-channels', 'channels')
  );

// ==================== Rules ====================

export const getControlEventRules = async (params?: {
  channel?: string;
  enabled_only?: boolean;
}): Promise<ControlEventRuleListResponse> =>
  withApi('getControlEventRules', 'fetching control event rules', () =>
    fetchList<'rules', ControlEventRule>('/control-event-rules', 'rules', { params })
  );

export const createControlEventRule = async (
  data: ControlEventRuleCreate
): Promise<ControlEventRule> =>
  withApi('createControlEventRule', 'creating control event rule', () =>
    mutateOne<ControlEventRule>('post', '/control-event-rules', data)
  );

export const updateControlEventRule = async (
  id: string,
  data: ControlEventRulePatch
): Promise<ControlEventRule> =>
  withApi('updateControlEventRule', 'updating control event rule', () =>
    mutateOne<ControlEventRule>('patch', `/control-event-rules/${id}`, data)
  );

export const deleteControlEventRule = async (id: string): Promise<void> =>
  withApi('deleteControlEventRule', 'deleting control event rule', () =>
    apiDelete(`/control-event-rules/${id}`)
  );

// ==================== Events ====================

export const getControlEvents = async (
  params?: ControlEventListParams
): Promise<ControlEventListResponse> =>
  withApi('getControlEvents', 'fetching control events', () =>
    fetchList<'events', ControlEvent>('/control-events', 'events', { params })
  );

export const getControlEvent = async (eventId: string): Promise<ControlEvent> =>
  withApi('getControlEvent', 'fetching control event', () =>
    fetchOne<ControlEvent>(`/control-events/${eventId}`)
  );

export const createControlEvent = async (data: ControlEventCreate): Promise<ControlEvent> =>
  withApi('createControlEvent', 'triggering control event', () =>
    mutateOne<ControlEvent>('post', '/control-events', data)
  );

// Re-export types for convenience
export type { ControlEventChannel };
