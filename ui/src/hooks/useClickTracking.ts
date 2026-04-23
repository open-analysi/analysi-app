/**
 * Click Tracking Hook
 *
 * Provides helpers for tracking critical button clicks and user actions.
 * Use this hook to get tracking functions for specific components.
 *
 * Example usage:
 *   const { trackExport, trackExecute, trackDelete } = useClickTracking('Alert Details');
 *
 *   <button onClick={() => {
 *     trackExport('alerts', { entityId: alertId, format: 'json' });
 *     handleExport();
 *   }}>
 *     Export
 *   </button>
 */

import { useCallback } from 'react';

import { trackClick } from '../utils/analyticsLogger';

export interface ClickTrackingDetails {
  entityType?: string;
  entityId?: string;
  entityName?: string;
  params?: Record<string, unknown>;
}

export function useClickTracking(component: string) {
  /**
   * Track an export action
   */
  const trackExport = useCallback(
    (entityType: string, details?: Omit<ClickTrackingDetails, 'entityType'>) => {
      trackClick(`export ${entityType}`, component, {
        entityType,
        ...details,
      });
    },
    [component]
  );

  /**
   * Track an execute/run action
   */
  const trackExecute = useCallback(
    (entityType: string, details?: Omit<ClickTrackingDetails, 'entityType'>) => {
      trackClick(`execute ${entityType}`, component, {
        entityType,
        ...details,
      });
    },
    [component]
  );

  /**
   * Track a delete action
   */
  const trackDelete = useCallback(
    (entityType: string, details?: Omit<ClickTrackingDetails, 'entityType'>) => {
      trackClick(`delete ${entityType}`, component, {
        entityType,
        ...details,
      });
    },
    [component]
  );

  /**
   * Track a save/update action
   */
  const trackSave = useCallback(
    (entityType: string, details?: Omit<ClickTrackingDetails, 'entityType'>) => {
      trackClick(`save ${entityType}`, component, {
        entityType,
        ...details,
      });
    },
    [component]
  );

  /**
   * Track a create action
   */
  const trackCreate = useCallback(
    (entityType: string, details?: Omit<ClickTrackingDetails, 'entityType'>) => {
      trackClick(`create ${entityType}`, component, {
        entityType,
        ...details,
      });
    },
    [component]
  );

  /**
   * Track a custom action
   */
  const trackAction = useCallback(
    (action: string, details?: ClickTrackingDetails) => {
      trackClick(action, component, details);
    },
    [component]
  );

  return {
    trackExport,
    trackExecute,
    trackDelete,
    trackSave,
    trackCreate,
    trackAction,
  };
}
