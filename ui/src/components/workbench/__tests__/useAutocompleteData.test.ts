import { renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock dependencies before imports
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getIntegrations: vi.fn(),
    getIntegrationTypes: vi.fn(),
    getIntegrationType: vi.fn(),
    getAllTools: vi.fn(),
  },
}));

vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: null,
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: vi.fn(async (promise: Promise<unknown>) => {
      try {
        const result = await promise;
        return [result, undefined];
      } catch (err) {
        return [undefined, err];
      }
    }),
  }),
}));

vi.mock('../cyCompleter', () => ({
  setCyIntegrationsCache: vi.fn(),
  setCyToolsCache: vi.fn(),
}));

import { backendApi } from '../../../services/backendApi';
import { setCyIntegrationsCache, setCyToolsCache } from '../cyCompleter';
import { useAutocompleteData } from '../useAutocompleteData';

const mockGetIntegrations = vi.mocked(backendApi.getIntegrations);
const mockGetIntegrationTypes = vi.mocked(backendApi.getIntegrationTypes);
const mockGetIntegrationType = vi.mocked(backendApi.getIntegrationType);
const mockGetAllTools = vi.mocked(backendApi.getAllTools);

describe('useAutocompleteData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches integrations and tools on mount and populates caches', async () => {
    mockGetIntegrations.mockResolvedValue([
      {
        integration_type: 'virustotal',
        integration_id: 'vt-main',
        tenant_id: 'tenant-1',
        name: 'VT Main',
        description: null,
        enabled: true,
        settings: {},
        created_at: '2025-01-01T00:00:00Z',
        updated_at: '2025-01-01T00:00:00Z',
      },
    ]);
    mockGetIntegrationTypes.mockResolvedValue([
      {
        integration_type: 'virustotal',
        display_name: 'VirusTotal',
        description: 'VT',
        tools: [],
        connectors: [],
        settings_schema: {},
      },
      {
        integration_type: 'splunk',
        display_name: 'Splunk',
        description: 'Search',
        tools: [],
        connectors: [],
        settings_schema: {},
      },
    ]);
    mockGetIntegrationType.mockResolvedValue({
      integration_type: 'virustotal',
      actions: [
        {
          action_id: 'ip_reputation',
          name: 'IP Reputation',
          description: 'Check IP',
          categories: ['enrichment'],
          cy_name: 'ip_reputation',
          enabled: true,
        },
      ],
      settings_schema: {},
      display_name: 'VirusTotal',
    });
    mockGetAllTools.mockResolvedValue({
      tools: [{ fqn: 'native::core::llm_run', name: 'llm_run', description: 'Run LLM' }],
      total: 1,
    });

    renderHook(() => useAutocompleteData());

    await waitFor(() => {
      expect(setCyIntegrationsCache).toHaveBeenCalled();
      expect(setCyToolsCache).toHaveBeenCalled();
    });

    // Verify integrations cache was set with only active types (virustotal, not splunk)
    const integrationsCacheCall = vi.mocked(setCyIntegrationsCache).mock.calls[0][0];
    expect(integrationsCacheCall).toHaveLength(1);
    expect(integrationsCacheCall[0]).toMatchObject({ id: 'virustotal' });

    // Verify tools cache includes both app:: and native:: tools
    const toolsCacheCall = vi.mocked(setCyToolsCache).mock.calls[0][0];
    expect(toolsCacheCall).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ fqn: 'app::virustotal::ip_reputation' }),
        expect.objectContaining({ fqn: 'native::core::llm_run' }),
      ])
    );
  });

  it('sets empty caches when getIntegrations fails', async () => {
    mockGetIntegrations.mockRejectedValue(new Error('Network error'));

    renderHook(() => useAutocompleteData());

    await waitFor(() => {
      expect(setCyIntegrationsCache).toHaveBeenCalledWith([]);
      expect(setCyToolsCache).toHaveBeenCalledWith([]);
    });
  });

  it('sets empty caches when getIntegrations returns null', async () => {
    mockGetIntegrations.mockResolvedValue(null as unknown as never);

    renderHook(() => useAutocompleteData());

    await waitFor(() => {
      expect(setCyIntegrationsCache).toHaveBeenCalledWith([]);
      expect(setCyToolsCache).toHaveBeenCalledWith([]);
    });
  });
});
