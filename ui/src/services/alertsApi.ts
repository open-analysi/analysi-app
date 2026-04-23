import {
  Alert,
  AlertAnalysis,
  AlertsListResponse,
  AlertsQueryParams,
  AnalysisStartResponse,
  AnalysisProgress,
  Disposition,
} from '../types/alert';

import { withApi, fetchOne, mutateOne, backendApiClient, type SifnosEnvelope } from './apiClient';

export const getAlerts = (params: AlertsQueryParams = {}): Promise<AlertsListResponse> =>
  withApi('getAlerts', 'fetching alerts', async () => {
    // Map our field names to backend field names
    const { sort, order, ...restParams } = params;
    const enhancedParams = {
      ...restParams,
      include_short_summary: true,
      ...(sort && { sort_by: sort }),
      ...(order && { sort_order: order }),
    };

    const response = await backendApiClient.get<SifnosEnvelope<Alert[]>>('/alerts', {
      params: enhancedParams,
      paramsSerializer: {
        indexes: null, // This makes arrays serialize as key=val1&key=val2 instead of key[0]=val1
      },
    });
    const { data, meta } = response.data;
    return {
      alerts: data,
      total: meta.total ?? 0,
      limit: meta.limit ?? 20,
      offset: meta.offset ?? 0,
      has_next: (meta.has_next as boolean | undefined) ?? false,
    };
  });

export const getAlert = (alertId: string): Promise<Alert> =>
  withApi('getAlert', 'fetching alert details', () =>
    fetchOne<Alert>(`/alerts/${alertId}`, { params: { include_short_summary: true } })
  );

export const createAlert = (alert: Partial<Alert>): Promise<Alert> =>
  withApi('createAlert', 'creating alert', () => mutateOne<Alert>('post', '/alerts', alert));

export const analyzeAlert = (alertId: string): Promise<AnalysisStartResponse> =>
  withApi('analyzeAlert', 'starting alert analysis', () =>
    mutateOne<AnalysisStartResponse>('post', `/alerts/${alertId}/analyze`)
  );

export const getAnalysisProgress = (alertId: string): Promise<AnalysisProgress> =>
  withApi('getAnalysisProgress', 'fetching analysis progress', () =>
    fetchOne<AnalysisProgress>(`/alerts/${alertId}/analysis/progress`)
  );

export const getAlertAnalyses = (alertId: string): Promise<AlertAnalysis[]> =>
  withApi('getAlertAnalyses', 'fetching alert analysis history', () =>
    fetchOne<AlertAnalysis[]>(`/alerts/${alertId}/analyses`)
  );

export const getAlertsByIoc = (
  iocValue: string,
  params: { ioc_type?: string; limit?: number } = {}
): Promise<Alert[]> =>
  withApi('getAlertsByIoc', 'fetching alerts by IOC', async () => {
    const response = await backendApiClient.get<SifnosEnvelope<Alert[]>>(
      `/alerts/by-ioc/${encodeURIComponent(iocValue)}`,
      { params }
    );
    return response.data.data;
  });

export const getDispositions = (): Promise<Disposition[]> =>
  withApi('getDispositions', 'fetching dispositions', () =>
    fetchOne<Disposition[]>('/dispositions')
  );
