import type { ReactElement } from 'react';

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { backendApi } from '../../services/backendApi';
import { IntegrationsPage } from '../Integrations';

const SPLUNK_PRODUCTION = 'Splunk Production';
const TEST_TIMESTAMP = '2025-01-01T00:00:00Z';
const PROVISION_FREE_TITLE = "Add all free integrations that don't require API keys";

// Helper to render with router context
const renderWithRouter = (ui: ReactElement) => {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
};

// Mock the backend API
vi.mock('../../services/backendApi', () => ({
  backendApi: {
    getIntegrationTypes: vi.fn(),
    getIntegrations: vi.fn(),
    getIntegrationHealth: vi.fn(),
    getManagedRuns: vi.fn(),
    getManagedResources: vi.fn(),
    getManagedSchedule: vi.fn(),
    updateManagedSchedule: vi.fn(),
    triggerManagedRun: vi.fn(),
    getIntegrationType: vi.fn(),
    createIntegration: vi.fn(),
    deleteIntegration: vi.fn(),
    enableIntegration: vi.fn(),
    disableIntegration: vi.fn(),
    getAllTools: vi.fn(),
    updateIntegration: vi.fn(),
    provisionFreeIntegrations: vi.fn(),
  },
}));

// Mock the error handler hook
vi.mock('../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: { hasError: false, message: '' },
    clearError: vi.fn(),
    runSafe: vi.fn(async (promise) => {
      try {
        const result = await promise;
        return [result, undefined];
      } catch (error) {
        return [undefined, error];
      }
    }),
  }),
}));

// Mock IntegrationSetupWizard component
vi.mock('../../components/integrations/IntegrationSetupWizard', () => ({
  IntegrationSetupWizard: ({
    integrationType,
    onClose,
  }: {
    integrationType: { display_name: string; integration_type: string };
    onClose: () => void;
  }) => (
    <div data-testid="integration-setup-wizard">
      <h2>Setup {integrationType.display_name}</h2>
      <span data-testid="wizard-type">{integrationType.integration_type}</span>
      <button onClick={onClose}>Close Wizard</button>
    </div>
  ),
}));

describe('IntegrationsPage', () => {
  const mockIntegrationTypes = [
    {
      integration_type: 'splunk',
      display_name: 'Splunk',
      actions: [
        {
          action_id: 'pull_alerts',
          name: 'Pull Alerts',
          description: 'Pull security alerts',
          categories: ['alert_ingestion'],
          cy_name: 'pull_alerts',
          enabled: true,
        },
        {
          action_id: 'health_check',
          name: 'Health Check',
          description: 'Check integration health',
          categories: ['health_monitoring'],
          cy_name: 'health_check',
          enabled: true,
        },
      ],
      settings_schema: {},
      description: 'SIEM integration',
      archetypes: ['SIEM'],
      priority: 90,
    },
    {
      integration_type: 'crowdstrike',
      display_name: 'CrowdStrike',
      actions: [
        {
          action_id: 'pull_alerts',
          name: 'Pull Alerts',
          description: 'Pull security alerts',
          categories: ['alert_ingestion'],
          cy_name: 'pull_alerts',
          enabled: true,
        },
      ],
      settings_schema: {},
      description: 'EDR integration',
      archetypes: ['EDR'],
      priority: 85,
    },
    {
      integration_type: 'slack',
      display_name: 'Slack',
      actions: [
        {
          action_id: 'send_notification',
          name: 'Send Notification',
          description: 'Send alerts to channels',
          categories: ['notification'],
          cy_name: 'send_notification',
          enabled: true,
        },
      ],
      settings_schema: {},
      description: 'Notification service',
      archetypes: ['Notification'],
      priority: 60,
    },
  ];

  const mockUserIntegrations = [
    {
      integration_id: 'int-1',
      integration_type: 'splunk',
      tenant_id: 'tenant-1',
      name: SPLUNK_PRODUCTION,
      description: 'Production SIEM',
      enabled: true,
      settings: {},
      created_at: TEST_TIMESTAMP,
      updated_at: TEST_TIMESTAMP,
      health_status: 'healthy' as const,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();

    // Setup default API mocks
    vi.mocked(backendApi.getIntegrationTypes).mockResolvedValue(mockIntegrationTypes);
    vi.mocked(backendApi.getIntegrations).mockResolvedValue(mockUserIntegrations);
    vi.mocked(backendApi.getIntegrationHealth).mockImplementation(() =>
      Promise.resolve({
        status: 'healthy',
        last_check_at: new Date().toISOString(),
      })
    );
    vi.mocked(backendApi.getManagedRuns).mockImplementation(() => Promise.resolve([]));
    vi.mocked(backendApi.getAllTools).mockResolvedValue({ tools: [], total: 0 });
    vi.mocked(backendApi.getIntegrationType).mockResolvedValue(mockIntegrationTypes[0]);
    vi.mocked(backendApi.getManagedResources).mockResolvedValue({});
  });

  describe('Basic Rendering', () => {
    it('renders the page with main sections', () => {
      renderWithRouter(<IntegrationsPage />);

      expect(screen.getByText('Available Integrations')).toBeInTheDocument();
      expect(screen.getByText('Your Integrations')).toBeInTheDocument();
      // Subtitle shows integration and action counts
      expect(screen.getByText(/integrations? · \d+ actions? enabled/)).toBeInTheDocument();
    });

    it('shows skeleton loader initially', () => {
      renderWithRouter(<IntegrationsPage />);

      // Skeleton loader renders animated pulse placeholders instead of plain text
      const skeletons = document.querySelectorAll('.animate-pulse');
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it('renders without crashing when API returns empty data', () => {
      vi.mocked(backendApi.getIntegrationTypes).mockResolvedValue([]);
      vi.mocked(backendApi.getIntegrations).mockResolvedValue([]);

      const { container } = renderWithRouter(<IntegrationsPage />);

      expect(container.firstChild).toBeInTheDocument();
    });
  });

  describe('Integration Display', () => {
    it('displays user integrations', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });
    });

    it('shows action_count in sidebar when actions array is not provided', async () => {
      // Registry list endpoint returns action_count but not actions array
      vi.mocked(backendApi.getIntegrationTypes).mockResolvedValue([
        {
          integration_type: 'whois_rdap',
          display_name: 'WHOIS RDAP',
          action_count: 3,
          settings_schema: {},
          description: 'WHOIS lookups via RDAP',
        },
      ]);

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText('WHOIS RDAP')).toBeInTheDocument();
      });

      // Should show "3 actions" from action_count, not "0 actions"
      expect(screen.getByText('3 actions')).toBeInTheDocument();
    });
  });

  describe('Empty States', () => {
    it('shows message when no user integrations exist', async () => {
      vi.mocked(backendApi.getIntegrations).mockResolvedValue([]);

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText('No integrations yet')).toBeInTheDocument();
        expect(
          screen.getByText('Click on an available integration to get started')
        ).toBeInTheDocument();
      });
    });
  });

  describe('UI Elements', () => {
    it('displays refresh button', () => {
      renderWithRouter(<IntegrationsPage />);

      const refreshButton = screen.getByTitle('Refresh integrations');
      expect(refreshButton).toBeInTheDocument();
      expect(refreshButton).toHaveTextContent('Refresh');
    });
  });

  describe('Search', () => {
    it('filters sidebar by display name', async () => {
      renderWithRouter(<IntegrationsPage />);

      // Wait for available integrations to load
      await waitFor(() => {
        expect(screen.getByText('Splunk')).toBeInTheDocument();
      });

      // Type in the search input
      const searchInput = screen.getByPlaceholderText('Search integrations...');
      fireEvent.change(searchInput, { target: { value: 'splunk' } });

      // Splunk should still be visible, CrowdStrike and Slack should be hidden
      expect(screen.getByText('Splunk')).toBeInTheDocument();
      expect(screen.queryByText('CrowdStrike')).not.toBeInTheDocument();
      expect(screen.queryByText('Slack')).not.toBeInTheDocument();
    });

    it('filters sidebar by archetype', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText('Splunk')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText('Search integrations...');
      fireEvent.change(searchInput, { target: { value: 'EDR' } });

      // Only CrowdStrike has EDR archetype
      expect(screen.getByText('CrowdStrike')).toBeInTheDocument();
      expect(screen.queryByText('Splunk')).not.toBeInTheDocument();
      expect(screen.queryByText('Slack')).not.toBeInTheDocument();
    });

    it('shows "no results" for unmatched search', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText('Splunk')).toBeInTheDocument();
      });

      const searchInput = screen.getByPlaceholderText('Search integrations...');
      fireEvent.change(searchInput, { target: { value: 'nonexistent-integration' } });

      expect(
        screen.getByText('No integrations match your search. Try a different term.')
      ).toBeInTheDocument();
    });
  });

  describe('Sorting', () => {
    it('displays configured integrations before unconfigured ones', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText('Splunk')).toBeInTheDocument();
        expect(screen.getByText('CrowdStrike')).toBeInTheDocument();
      });

      // Get all sidebar buttons (integration type items)
      const buttons = screen
        .getAllByRole('button')
        .filter(
          (btn) =>
            btn.textContent?.includes('Splunk') ||
            btn.textContent?.includes('CrowdStrike') ||
            btn.textContent?.includes('Slack')
        );

      // Splunk (configured) should appear before CrowdStrike and Slack (unconfigured)
      const splunkIndex = buttons.findIndex((btn) => btn.textContent?.includes('Splunk'));
      const crowdstrikeIndex = buttons.findIndex((btn) => btn.textContent?.includes('CrowdStrike'));
      const slackIndex = buttons.findIndex((btn) => btn.textContent?.includes('Slack'));

      expect(splunkIndex).toBeLessThan(crowdstrikeIndex);
      expect(splunkIndex).toBeLessThan(slackIndex);
    });

    it('shows "Available to Configure" separator between configured and unconfigured', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText('Splunk')).toBeInTheDocument();
      });

      expect(screen.getByText('Available to Configure')).toBeInTheDocument();
    });
  });

  describe('Create Integration', () => {
    it('clicking available integration opens preview then wizard', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText('CrowdStrike')).toBeInTheDocument();
      });

      // Click a sidebar integration to open preview
      const crowdstrikeButton = screen
        .getAllByRole('button')
        .find((btn) => btn.textContent?.includes('CrowdStrike'));
      fireEvent.click(crowdstrikeButton!);

      // Wait for preview panel with "Configure Integration" button
      await waitFor(() => {
        expect(screen.getByText('Configure Integration')).toBeInTheDocument();
      });

      // Click the Configure Integration button
      fireEvent.click(screen.getByText('Configure Integration'));

      // Wizard should appear
      await waitFor(() => {
        expect(screen.getByTestId('integration-setup-wizard')).toBeInTheDocument();
      });
    });

    it('wizard receives correct integration type details', async () => {
      // Mock getIntegrationType to return CrowdStrike details
      vi.mocked(backendApi.getIntegrationType).mockResolvedValue({
        ...mockIntegrationTypes[1],
        tools: [
          {
            fqn: 'app::crowdstrike::detect',
            name: 'Detect',
            description: 'Detect threats',
          },
        ],
      });

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText('CrowdStrike')).toBeInTheDocument();
      });

      // Click CrowdStrike in sidebar
      const csButton = screen
        .getAllByRole('button')
        .find((btn) => btn.textContent?.includes('CrowdStrike'));
      fireEvent.click(csButton!);

      // Wait for preview and click Configure Integration
      await waitFor(() => {
        expect(screen.getByText('Configure Integration')).toBeInTheDocument();
      });
      fireEvent.click(screen.getByText('Configure Integration'));

      // Verify the wizard received the correct type
      await waitFor(() => {
        expect(screen.getByTestId('wizard-type')).toHaveTextContent('crowdstrike');
      });
    });
  });

  describe('Delete Integration', () => {
    it('delete button on card shows confirmation dialog', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      // Find and click the delete button (trash icon) on the card
      const deleteButton = screen.getByTitle('Delete integration');
      fireEvent.click(deleteButton);

      // Confirmation dialog should appear with destructive action details
      await waitFor(() => {
        expect(
          screen.getByText('Permanently delete this integration configuration')
        ).toBeInTheDocument();
        expect(screen.getByText('Cancel')).toBeInTheDocument();
      });
    });

    it('confirming delete calls API', async () => {
      vi.mocked(backendApi.deleteIntegration).mockResolvedValue(undefined as never);

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      // Click delete button on card
      fireEvent.click(screen.getByTitle('Delete integration'));

      // Wait for confirmation dialog
      await waitFor(() => {
        expect(
          screen.getByText('Permanently delete this integration configuration')
        ).toBeInTheDocument();
      });

      // Click the "Delete Integration" confirm button (not the heading)
      const confirmButtons = screen.getAllByRole('button');
      const deleteConfirmBtn = confirmButtons.find(
        (btn) => btn.textContent === 'Delete Integration'
      );
      fireEvent.click(deleteConfirmBtn!);

      // API should be called
      await waitFor(() => {
        expect(backendApi.deleteIntegration).toHaveBeenCalledWith('int-1');
      });
    });
  });

  describe('Toggle Integration', () => {
    it('disabling an enabled integration calls disableIntegration API', async () => {
      vi.mocked(backendApi.disableIntegration).mockResolvedValue(undefined as never);

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      // Find the toggle switch via its aria role
      const toggleSwitch = screen.getByRole('switch');
      expect(toggleSwitch).toHaveAttribute('aria-checked', 'true');

      fireEvent.click(toggleSwitch);

      await waitFor(() => {
        expect(backendApi.disableIntegration).toHaveBeenCalledWith('int-1');
      });
    });

    it('enabling a disabled integration calls enableIntegration API', async () => {
      const disabledIntegration = {
        ...mockUserIntegrations[0],
        enabled: false,
      };
      vi.mocked(backendApi.getIntegrations).mockResolvedValue([disabledIntegration]);
      vi.mocked(backendApi.enableIntegration).mockResolvedValue(undefined as never);

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      const toggleSwitch = screen.getByRole('switch');
      expect(toggleSwitch).toHaveAttribute('aria-checked', 'false');

      fireEvent.click(toggleSwitch);

      await waitFor(() => {
        expect(backendApi.enableIntegration).toHaveBeenCalledWith('int-1');
      });
    });
  });

  describe('Details Panel', () => {
    it('clicking integration card opens details panel', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      // Click the card
      const card = screen.getByText(SPLUNK_PRODUCTION).closest('div[class*="cursor-pointer"]');
      fireEvent.click(card!);

      // Verify detail panel appears with tabs
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Overview' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Configuration' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Runs' })).toBeInTheDocument();
      });
    });

    it('tab navigation switches between overview, configuration, and runs', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      // Open details
      const card = screen.getByText(SPLUNK_PRODUCTION).closest('div[class*="cursor-pointer"]');
      fireEvent.click(card!);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Overview' })).toBeInTheDocument();
      });

      // Switch to Configuration tab
      fireEvent.click(screen.getByRole('button', { name: 'Configuration' }));
      await waitFor(() => {
        expect(screen.getByText('Settings')).toBeInTheDocument();
      });

      // Switch to Runs tab
      fireEvent.click(screen.getByRole('button', { name: 'Runs' }));
      await waitFor(() => {
        expect(screen.getByText('Recent Runs')).toBeInTheDocument();
      });
    });

    it('details panel calls API for runs and type details', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      const card = screen.getByText(SPLUNK_PRODUCTION).closest('div[class*="cursor-pointer"]');
      fireEvent.click(card!);

      await waitFor(() => {
        expect(backendApi.getManagedRuns).toHaveBeenCalledWith('int-1', 'health_check', {
          limit: 10,
        });
        expect(backendApi.getIntegrationType).toHaveBeenCalledWith('splunk');
      });
    });
  });

  describe('Error Handling', () => {
    it('shows empty state when getIntegrations fails', async () => {
      vi.mocked(backendApi.getIntegrations).mockRejectedValue(new Error('Network error'));

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText('No integrations yet')).toBeInTheDocument();
      });
    });

    it('shows sidebar message when getIntegrationTypes returns empty', async () => {
      vi.mocked(backendApi.getIntegrationTypes).mockResolvedValue([]);

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(
          screen.getByText('No integration types available. Please check backend configuration.')
        ).toBeInTheDocument();
      });
    });
  });

  describe('Refresh', () => {
    it('refresh button triggers data reload', async () => {
      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      // Clear mock call counts after initial load
      vi.mocked(backendApi.getIntegrations).mockClear();

      // Click refresh
      const refreshButton = screen.getByTitle('Refresh integrations');
      fireEvent.click(refreshButton);

      await waitFor(() => {
        expect(backendApi.getIntegrations).toHaveBeenCalled();
      });
    });
  });

  describe('Action Dropdown Menu', () => {
    it('clicking an action from the dropdown menu does NOT open the details panel', async () => {
      vi.mocked(backendApi.triggerManagedRun).mockResolvedValue({
        task_run_id: 'run-123',
        status: 'running',
        task_id: 'task-1',
        resource_key: 'health_check',
      });

      // Mock polling response so the post-trigger poll doesn't crash
      vi.mocked(backendApi.getManagedRuns).mockResolvedValue([
        {
          task_run_id: 'run-123',
          status: 'completed',
          created_at: TEST_TIMESTAMP,
          started_at: '2025-01-01T00:00:01Z',
          completed_at: '2025-01-01T00:00:02Z',
        },
      ]);

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      // Click the Run button on the Splunk card to open the action dropdown
      // (Splunk has 2 actions so it shows a dropdown instead of running directly)
      const runButton = screen.getByTitle('Run action now');
      fireEvent.click(runButton);

      // The dropdown should appear with action options
      await waitFor(() => {
        expect(screen.getByText('Pull Alerts')).toBeInTheDocument();
        expect(screen.getByText('Health Check')).toBeInTheDocument();
      });

      // Click "Pull Alerts" from the dropdown
      fireEvent.click(screen.getByText('Pull Alerts'));

      // The action run should be triggered
      await waitFor(() => {
        expect(backendApi.triggerManagedRun).toHaveBeenCalled();
      });

      // The details panel should NOT have opened (no Overview/Actions/Runs tabs visible)
      expect(screen.queryByRole('button', { name: 'Overview' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Actions' })).not.toBeInTheDocument();
    });
  });

  describe('Provision Free Integrations', () => {
    it('renders the "Add Free Integrations" button', () => {
      renderWithRouter(<IntegrationsPage />);

      const button = screen.getByTitle(PROVISION_FREE_TITLE);
      expect(button).toBeInTheDocument();
      expect(button).toHaveTextContent('Add Free Integrations');
    });

    it('calls provisionFreeIntegrations API and shows result banner', async () => {
      vi.mocked(backendApi.provisionFreeIntegrations).mockResolvedValue({
        created: 2,
        already_exists: 1,
        integrations: [
          {
            integration_type: 'whois',
            integration_id: 'whois-1',
            name: 'WHOIS Lookup',
            status: 'created',
          },
          {
            integration_type: 'dns',
            integration_id: 'dns-1',
            name: 'DNS Resolver',
            status: 'created',
          },
          {
            integration_type: 'geoip',
            integration_id: 'geoip-1',
            name: 'GeoIP',
            status: 'already_exists',
          },
        ],
      });

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      // Click the provision button
      const button = screen.getByTitle(PROVISION_FREE_TITLE);
      fireEvent.click(button);

      // API should be called
      await waitFor(() => {
        expect(backendApi.provisionFreeIntegrations).toHaveBeenCalled();
      });

      // Result banner should appear
      await waitFor(() => {
        expect(screen.getByText('Free integrations provisioned')).toBeInTheDocument();
        expect(screen.getByText('2 created, 1 already existed')).toBeInTheDocument();
      });

      // All integrations should be listed as badges (created and already existing)
      expect(screen.getByText('WHOIS Lookup')).toBeInTheDocument();
      expect(screen.getByText('DNS Resolver')).toBeInTheDocument();
      expect(screen.getByText('GeoIP')).toBeInTheDocument();
    });

    it('dismisses the result banner when X is clicked', async () => {
      vi.mocked(backendApi.provisionFreeIntegrations).mockResolvedValue({
        created: 1,
        already_exists: 0,
        integrations: [
          {
            integration_type: 'whois',
            integration_id: 'whois-1',
            name: 'WHOIS Lookup',
            status: 'created',
          },
        ],
      });

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByTitle(PROVISION_FREE_TITLE));

      await waitFor(() => {
        expect(screen.getByText('Free integrations provisioned')).toBeInTheDocument();
      });

      // Click the dismiss X button on the banner
      const bannerContainer = screen.getByText('Free integrations provisioned').closest('.mb-6');
      const closeBtn = bannerContainer!.querySelector('button:last-of-type')!;
      fireEvent.click(closeBtn);

      await waitFor(() => {
        expect(screen.queryByText('Free integrations provisioned')).not.toBeInTheDocument();
      });
    });

    it('refreshes integrations after successful provisioning', async () => {
      vi.mocked(backendApi.provisionFreeIntegrations).mockResolvedValue({
        created: 1,
        already_exists: 0,
        integrations: [
          {
            integration_type: 'whois',
            integration_id: 'whois-1',
            name: 'WHOIS Lookup',
            status: 'created',
          },
        ],
      });

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      // Clear call counts after initial load
      vi.mocked(backendApi.getIntegrations).mockClear();

      fireEvent.click(screen.getByTitle(PROVISION_FREE_TITLE));

      // After provisioning, getIntegrations should be called again to refresh
      await waitFor(() => {
        expect(backendApi.getIntegrations).toHaveBeenCalled();
      });
    });
  });

  describe('Configuration Tab - Settings Edit Mode', () => {
    it('shows current values for both string and numeric settings in edit form', async () => {
      const integrationWithMixedSettings = {
        integration_id: 'int-splunk',
        integration_type: 'splunk',
        tenant_id: 'tenant-1',
        name: SPLUNK_PRODUCTION,
        description: 'Production SIEM',
        enabled: true,
        settings: { host: 'splunk-server', port: 8089 },
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        health_status: 'healthy' as const,
      };

      vi.mocked(backendApi.getIntegrations).mockResolvedValue([integrationWithMixedSettings]);

      renderWithRouter(<IntegrationsPage />);

      await waitFor(() => {
        expect(screen.getByText(SPLUNK_PRODUCTION)).toBeInTheDocument();
      });

      // Click the card to open the detail panel
      const card = screen.getByText(SPLUNK_PRODUCTION).closest('div[class*="cursor-pointer"]');
      fireEvent.click(card!);

      // Wait for the detail panel tabs to appear
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Configuration' })).toBeInTheDocument();
      });

      // Click the Configuration tab
      fireEvent.click(screen.getByRole('button', { name: 'Configuration' }));

      // Wait for settings section
      await waitFor(() => {
        expect(screen.getByText('Settings')).toBeInTheDocument();
      });

      // Click Edit
      fireEvent.click(screen.getByRole('button', { name: 'Edit' }));

      // Both string and numeric setting values must be populated in the edit form
      await waitFor(() => {
        expect(screen.getByDisplayValue('splunk-server')).toBeInTheDocument();
        expect(screen.getByDisplayValue('8089')).toBeInTheDocument();
      });
    });
  });
});
