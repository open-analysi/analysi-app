import { create } from 'zustand';

import { backendApi } from '../services/backendApi';
import type {
  Alert,
  AlertsQueryParams,
  Disposition,
  AnalysisProgress,
  AlertAnalysis,
} from '../types/alert';
import { logger } from '../utils/errorHandler';

type AlertFilters = Omit<AlertsQueryParams, 'offset' | 'limit' | 'sort' | 'order'>;

interface AlertStore {
  // State
  alerts: Alert[];
  selectedAlert: Alert | undefined;
  dispositions: Disposition[];
  analysisProgress: AnalysisProgress | undefined;
  alertAnalyses: AlertAnalysis[];
  pollingTimeout: ReturnType<typeof setTimeout> | null;

  // In-flight request tracking for deduplication
  pendingAlertsRequest: Promise<void> | null;
  pendingDispositionsRequest: Promise<void> | null;

  // Pagination
  total: number;
  limit: number;
  offset: number;

  // Sorting
  sortBy: 'severity' | 'created_at' | 'confidence' | 'analyzed_at';
  sortOrder: 'asc' | 'desc';

  // Filters
  filters: AlertFilters;

  // Loading states
  isLoadingAlerts: boolean;
  isLoadingAlert: boolean;
  isLoadingDispositions: boolean;
  isAnalyzing: boolean;

  // Errors
  error: string | undefined;

  // Actions
  fetchAlerts: (params?: AlertsQueryParams) => Promise<void>;
  fetchAlertsSilent: (params?: AlertsQueryParams) => Promise<void>;
  fetchAlert: (alertId: string) => Promise<void>;
  fetchDispositions: () => Promise<void>;
  startAnalysis: (alertId: string) => Promise<void>;
  fetchAnalysisProgress: (alertId: string) => Promise<void>;
  fetchAlertAnalyses: (alertId: string) => Promise<void>;

  // UI Actions
  setSelectedAlert: (alert: Alert | undefined) => void;
  setFilters: (filters: AlertFilters) => void;
  setSorting: (sortBy: AlertStore['sortBy'], sortOrder: AlertStore['sortOrder']) => void;
  setPagination: (offset: number, limit: number) => void;
  clearError: () => void;
  clearAnalysisProgress: () => void;
  reset: () => void;
}

const initialState = {
  alerts: [],
  selectedAlert: undefined,
  dispositions: [],
  analysisProgress: undefined,
  alertAnalyses: [],
  pollingTimeout: null,
  pendingAlertsRequest: null,
  pendingDispositionsRequest: null,
  total: 0,
  limit: 20,
  offset: 0,
  sortBy: 'created_at' as const,
  sortOrder: 'desc' as const,
  filters: {},
  isLoadingAlerts: false,
  isLoadingAlert: false,
  isLoadingDispositions: false,
  isAnalyzing: false,
  error: undefined,
};

export const useAlertStore = create<AlertStore>((set, get) => ({
  ...initialState,

  fetchAlerts: async (params?: AlertsQueryParams) => {
    // Return existing request if one is already in-flight
    const existingRequest = get().pendingAlertsRequest;
    if (existingRequest) {
      logger.info(
        'Deduplicating alerts request - returning existing promise',
        {},
        { component: 'AlertStore', method: 'fetchAlerts' }
      );
      return existingRequest;
    }

    const { filters, sortBy, sortOrder, limit, offset } = get();

    set({ isLoadingAlerts: true, error: undefined });

    const requestPromise = (async () => {
      try {
        const queryParams: AlertsQueryParams = {
          ...filters,
          ...params,
          limit: params?.limit ?? limit,
          offset: params?.offset ?? offset,
          sort: params?.sort ?? sortBy,
          order: params?.order ?? sortOrder,
        };

        const response = await backendApi.getAlerts(queryParams);

        // Ensure alerts is always an array
        const alerts = Array.isArray(response.alerts) ? response.alerts : [];

        set({
          alerts: alerts,
          total: response.total ?? 0,
          limit: response.limit ?? queryParams.limit ?? 20,
          offset: response.offset ?? queryParams.offset ?? 0,
          isLoadingAlerts: false,
          pendingAlertsRequest: null,
        });

        logger.info(
          'Alerts fetched successfully',
          { count: alerts.length },
          { component: 'AlertStore', method: 'fetchAlerts' }
        );
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Failed to fetch alerts';
        set({ error: errorMessage, isLoadingAlerts: false, pendingAlertsRequest: null });
        logger.error('Failed to fetch alerts', error, {
          component: 'AlertStore',
          method: 'fetchAlerts',
        });
      }
    })();

    set({ pendingAlertsRequest: requestPromise });
    return requestPromise;
  },

  fetchAlertsSilent: async (params?: AlertsQueryParams) => {
    const { filters, sortBy, sortOrder, limit, offset, alerts: currentAlerts } = get();

    // Don't set loading state for silent refresh
    try {
      const queryParams: AlertsQueryParams = {
        ...filters,
        ...params,
        limit: params?.limit ?? limit,
        offset: params?.offset ?? offset,
        sort: params?.sort ?? sortBy,
        order: params?.order ?? sortOrder,
      };

      const response = await backendApi.getAlerts(queryParams);

      // Ensure alerts is always an array
      const alerts = Array.isArray(response.alerts) ? response.alerts : [];

      // Only update if data has actually changed
      const hasChanges =
        (response.total ?? 0) !== get().total ||
        alerts.length !== currentAlerts.length ||
        JSON.stringify(alerts) !== JSON.stringify(currentAlerts);

      if (hasChanges) {
        set({
          alerts: alerts,
          total: response.total ?? 0,
          limit: response.limit ?? limit,
          offset: response.offset ?? offset,
        });
        logger.info(
          'Alerts updated (silent refresh)',
          { count: alerts.length },
          { component: 'AlertStore', method: 'fetchAlertsSilent' }
        );
      }
    } catch (error) {
      // Silent refresh shouldn't show errors to user
      logger.error('Silent refresh failed', error, {
        component: 'AlertStore',
        method: 'fetchAlertsSilent',
      });
    }
  },

  fetchAlert: async (alertId: string) => {
    // Clear any existing polling timeout when switching alerts
    const existingTimeout = get().pollingTimeout;
    if (existingTimeout) {
      clearTimeout(existingTimeout);
    }

    const currentAlertId = get().selectedAlert?.alert_id;
    const isSwitchingAlerts = currentAlertId && currentAlertId !== alertId;

    set({
      isLoadingAlert: true,
      error: undefined,
      // Only clear progress when switching to a different alert, not when refreshing same alert
      analysisProgress: isSwitchingAlerts ? undefined : get().analysisProgress,
      pollingTimeout: isSwitchingAlerts ? undefined : get().pollingTimeout,
      alertAnalyses: isSwitchingAlerts ? [] : get().alertAnalyses,
    });

    try {
      const alert = await backendApi.getAlert(alertId);
      set({ selectedAlert: alert, isLoadingAlert: false });
      logger.info(
        'Alert fetched successfully',
        { alertId },
        { component: 'AlertStore', method: 'fetchAlert' }
      );
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to fetch alert';
      set({ error: errorMessage, isLoadingAlert: false });
      logger.error('Failed to fetch alert', error, {
        component: 'AlertStore',
        method: 'fetchAlert',
        entityId: alertId,
        entityType: 'alert',
      });
    }
  },

  fetchDispositions: async () => {
    const { dispositions, pendingDispositionsRequest } = get();

    // Cache dispositions if already loaded
    if (dispositions.length > 0) {
      return;
    }

    // Return existing request if one is already in-flight
    if (pendingDispositionsRequest) {
      logger.info(
        'Deduplicating dispositions request - returning existing promise',
        {},
        { component: 'AlertStore', method: 'fetchDispositions' }
      );
      return pendingDispositionsRequest;
    }

    set({ isLoadingDispositions: true, error: undefined });

    const requestPromise = (async () => {
      try {
        const data = await backendApi.getDispositions();
        set({ dispositions: data, isLoadingDispositions: false, pendingDispositionsRequest: null });
        logger.info(
          'Dispositions fetched successfully',
          { count: data.length },
          { component: 'AlertStore', method: 'fetchDispositions' }
        );
      } catch (error) {
        const errorMessage =
          error instanceof Error ? error.message : 'Failed to fetch dispositions';
        set({
          error: errorMessage,
          isLoadingDispositions: false,
          pendingDispositionsRequest: null,
        });
        logger.error('Failed to fetch dispositions', error, {
          component: 'AlertStore',
          method: 'fetchDispositions',
        });
      }
    })();

    set({ pendingDispositionsRequest: requestPromise });
    return requestPromise;
  },

  startAnalysis: async (alertId: string) => {
    set({ isAnalyzing: true, error: undefined });

    try {
      const response = await backendApi.analyzeAlert(alertId);

      // Update the alert in the list if it exists
      const { alerts } = get();
      const updatedAlerts = alerts.map((alert) =>
        alert.alert_id === alertId ? { ...alert, analysis_status: 'in_progress' as const } : alert
      );

      set({ alerts: updatedAlerts, isAnalyzing: false });

      // If this is the selected alert, update it too
      const { selectedAlert } = get();
      if (selectedAlert?.alert_id === alertId) {
        set({ selectedAlert: { ...selectedAlert, analysis_status: 'in_progress' as const } });
      }

      logger.info(
        'Analysis started successfully',
        { alertId, analysisId: response.analysis_id },
        { component: 'AlertStore', method: 'startAnalysis' }
      );

      // Start polling for progress
      void get().fetchAnalysisProgress(alertId);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to start analysis';
      set({ error: errorMessage, isAnalyzing: false });
      logger.error('Failed to start analysis', error, {
        component: 'AlertStore',
        method: 'startAnalysis',
        entityId: alertId,
        entityType: 'alert',
      });
    }
  },

  fetchAnalysisProgress: async (alertId: string) => {
    // Clear any existing polling timeout
    const existingTimeout = get().pollingTimeout;
    if (existingTimeout) {
      clearTimeout(existingTimeout);
      set({ pollingTimeout: null });
    }

    try {
      const progress = await backendApi.getAnalysisProgress(alertId);
      const currentProgress = get().analysisProgress;

      // Only update if progress has actually changed to avoid unnecessary re-renders
      if (JSON.stringify(currentProgress) !== JSON.stringify(progress)) {
        set({ analysisProgress: progress });
      }

      // Continue polling if analysis is still running or paused
      if (progress.status === 'running' || progress.status === 'paused') {
        // Adaptive polling: 10 seconds when paused for workflow generation, 2 seconds otherwise
        const pollInterval = progress.status === 'paused' ? 10000 : 2000;
        const timeout = setTimeout(() => {
          void get().fetchAnalysisProgress(alertId);
        }, pollInterval);
        set({ pollingTimeout: timeout });
      } else if (
        (progress.status === 'completed' || progress.status === 'failed') && // Only refresh alert data once when transitioning to completed/failed
        currentProgress?.status !== progress.status
      ) {
        // Only refresh alert data if the alert doesn't already reflect the terminal state.
        // Skips the redundant re-fetch on initial page load when the analysis was already complete.
        const { selectedAlert } = get();
        const isAlreadyTerminal =
          selectedAlert?.analysis_status === 'completed' ||
          selectedAlert?.analysis_status === 'failed';

        if (!isAlreadyTerminal) {
          void get().fetchAlert(alertId);
          void get().fetchAlertAnalyses(alertId);
        }
      }
      // Don't clear analysisProgress here - let the user close it manually
    } catch (error) {
      logger.error('Failed to fetch analysis progress', error, {
        component: 'AlertStore',
        method: 'fetchAnalysisProgress',
        entityId: alertId,
        entityType: 'alert',
      });
      // Don't set error state for polling failures
    }
  },

  fetchAlertAnalyses: async (alertId: string) => {
    try {
      const analyses = await backendApi.getAlertAnalyses(alertId);
      set({ alertAnalyses: analyses });
      logger.info(
        'Alert analyses fetched successfully',
        { alertId, count: analyses.length },
        { component: 'AlertStore', method: 'fetchAlertAnalyses' }
      );
    } catch (error) {
      logger.error('Failed to fetch alert analyses', error, {
        component: 'AlertStore',
        method: 'fetchAlertAnalyses',
        entityId: alertId,
        entityType: 'alert',
      });
    }
  },

  setSelectedAlert: (alert: Alert | undefined) => {
    // Clear alert analyses and analysisProgress when switching alerts
    const currentAlert = get().selectedAlert;
    if (!alert || alert.alert_id !== currentAlert?.alert_id) {
      // Different alert or no alert - clear everything including progress
      set({ selectedAlert: alert, analysisProgress: undefined, alertAnalyses: [] });
    } else {
      // Same alert - just update it, keep progress if it exists
      set({ selectedAlert: alert });
    }
  },

  setFilters: (filters: AlertFilters) => {
    set({ filters, offset: 0 }); // Reset pagination when filters change
    void get().fetchAlerts();
  },

  setSorting: (sortBy: AlertStore['sortBy'], sortOrder: AlertStore['sortOrder']) => {
    set({ sortBy, sortOrder });
    void get().fetchAlerts();
  },

  setPagination: (offset: number, limit: number) => {
    set({ offset, limit });
    void get().fetchAlerts();
  },

  clearError: () => {
    set({ error: undefined });
  },

  clearAnalysisProgress: () => {
    const timeout = get().pollingTimeout;
    if (timeout) {
      clearTimeout(timeout);
    }
    set({ analysisProgress: undefined, pollingTimeout: null });
  },

  reset: () => {
    set(initialState);
  },
}));
