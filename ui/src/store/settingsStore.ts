import { create } from 'zustand';

import { backendApi } from '../services/backendApi';
import type { AuditLog, AuditLogQueryParams } from '../types/audit';
import { ConfigurationVersion } from '../types/configuration';

interface SettingsState {
  currentVersion: string;
  versions: ConfigurationVersion[];
  auditLogs: AuditLog[];
  auditLogsTotalCount: number;
  auditLogsCurrentPage: number;
  auditLogsPageSize: number;
  auditLogsTotalPages: number;
  isLoading: boolean;
  error: string | null;

  // Actions
  saveVersion: (changes: ConfigurationVersion['changes'], comment?: string) => void;
  revertToVersion: (versionId: string) => void;
  fetchAuditLogs: (params?: AuditLogQueryParams) => Promise<void>;
  refreshAuditLogs: () => Promise<void>;
  setAuditLogsPage: (page: number) => void;
  setAuditLogsPageSize: (pageSize: number) => void;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  currentVersion: '',
  versions: [],
  auditLogs: [],
  auditLogsTotalCount: 0,
  auditLogsCurrentPage: 1,
  auditLogsPageSize: 25,
  auditLogsTotalPages: 0,
  isLoading: false,
  error: null,

  saveVersion: (changes, comment) =>
    set((state) => ({
      versions: [
        {
          id: crypto.randomUUID(),
          timestamp: new Date(),
          author: 'Current User',
          changes,
          comment,
        },
        ...state.versions,
      ],
    })),

  revertToVersion: (versionId) =>
    set((state) => {
      const version = state.versions.find((v) => v.id === versionId);
      if (!version) return state;

      return {
        currentVersion: versionId,
        // ... apply changes
      };
    }),

  fetchAuditLogs: async (params?: AuditLogQueryParams) => {
    set({ isLoading: true, error: null });

    try {
      const state = get();

      // Merge provided params with current pagination state
      const queryParams: AuditLogQueryParams = {
        page: params?.page !== undefined ? params.page : state.auditLogsCurrentPage,
        page_size: params?.page_size !== undefined ? params.page_size : state.auditLogsPageSize,
        ...params,
      };

      const response = await backendApi.getAuditLogs(queryParams);

      // Convert ISO timestamp strings to Date objects
      const parsedLogs = response.activities.map((log) => ({
        ...log,
        timestamp: log.timestamp, // Keep as string - component will handle formatting
      }));

      set({
        auditLogs: parsedLogs,
        auditLogsTotalCount: response.total,
        auditLogsCurrentPage: response.page || 1,
        auditLogsPageSize: response.page_size || 25,
        auditLogsTotalPages: response.total_pages || 0,
        isLoading: false,
      });
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch audit logs',
        isLoading: false,
      });
    }
  },

  refreshAuditLogs: async () => {
    const { fetchAuditLogs, auditLogsCurrentPage, auditLogsPageSize } = get();
    await fetchAuditLogs({ page: auditLogsCurrentPage, page_size: auditLogsPageSize });
  },

  setAuditLogsPage: (page: number) => {
    const { fetchAuditLogs, auditLogsPageSize } = get();
    void fetchAuditLogs({ page, page_size: auditLogsPageSize });
  },

  setAuditLogsPageSize: (pageSize: number) => {
    const { fetchAuditLogs } = get();
    // Reset to page 1 when changing page size
    void fetchAuditLogs({ page: 1, page_size: pageSize });
  },
}));
