import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';

import {
  ServerIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  ClockIcon,
  ArrowPathIcon,
  PowerIcon,
  TrashIcon,
  ExclamationTriangleIcon,
  EyeIcon,
  EyeSlashIcon,
  CloudIcon,
  CircleStackIcon,
  MagnifyingGlassIcon,
  CubeIcon,
  BoltIcon,
} from '@heroicons/react/24/outline';
import { XCircleIcon } from '@heroicons/react/24/solid';

import ErrorBoundary from '../components/common/ErrorBoundary';
import { IntegrationSetupWizard } from '../components/integrations/IntegrationSetupWizard';
import useErrorHandler from '../hooks/useErrorHandler';
import { usePageTracking } from '../hooks/usePageTracking';
import { extractApiErrorMessage } from '../services/apiClient';
import { backendApi } from '../services/backendApi';
import type {
  IntegrationTypeInfo,
  IntegrationInstance,
  ManagedRun,
  ManagedSchedule,
  ProvisionFreeResponse,
} from '../types/integration';
import { logger } from '../utils/errorHandler';
import { startPolling, type PollingController } from '../utils/polling';

// Local type aliases for brevity within this component
type IntegrationType = IntegrationTypeInfo;
type Integration = IntegrationInstance;

type CredentialDetail = {
  id: string;
  provider: string;
  account: string;
  secret: Record<string, string>;
  credential_metadata: Record<string, unknown> | null;
  key_version: number;
  is_primary?: boolean;
  purpose?: string;
  created_at?: string;
};

// eslint-disable-next-line sonarjs/cognitive-complexity -- large page component, splitting deferred
export const IntegrationsPage: React.FC = () => {
  // Logger context for this component
  const logCtx = (method: string) => ({ component: 'IntegrationsPage', method });

  // Track page views
  usePageTracking('Integrations', 'IntegrationsPage');

  const [availableIntegrations, setAvailableIntegrations] = useState<IntegrationType[]>([]);
  const [userIntegrations, setUserIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIntegrationType, setSelectedIntegrationType] = useState<IntegrationType | null>(
    null
  );
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedIntegration, setSelectedIntegration] = useState<Integration | null>(null);
  const [showDetails, setShowDetails] = useState(false);
  const [detailsTab, setDetailsTab] = useState<'overview' | 'actions' | 'runs' | 'configuration'>(
    'overview'
  );
  const [integrationRuns, setIntegrationRuns] = useState<ManagedRun[]>([]);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [runningActions, setRunningActions] = useState<Map<string, string>>(new Map()); // Map of integrationId+actionId -> runId
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [runningIntegrationId, setRunningIntegrationId] = useState<string | null>(null);
  const [showActionMenu, setShowActionMenu] = useState<string | null>(null); // integrationId when showing action menu
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState<{
    show: boolean;
    integration: Integration | null;
  }>({ show: false, integration: null });
  const [showCloseConfirmation, setShowCloseConfirmation] = useState(false);
  const [formHasChanges, setFormHasChanges] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [visiblePasswords, setVisiblePasswords] = useState<Set<string>>(new Set());
  const [useWizard] = useState(true); // Toggle between wizard and old form
  const [editedSettings, setEditedSettings] = useState<Record<string, unknown>>({});
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [settingsEditMode, setSettingsEditMode] = useState(false);
  const [managedSchedules, setManagedSchedules] = useState<Record<string, ManagedSchedule>>({});
  const [managedResourceKeys, setManagedResourceKeys] = useState<string[]>([]);
  const [integrationCredentials, setIntegrationCredentials] = useState<CredentialDetail[]>([]);
  const [loadingCredentials, setLoadingCredentials] = useState(false);
  const [loadingSchedules, setLoadingSchedules] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<{
    actionId: string;
    schedule: {
      schedule_id?: string;
      schedule_type: string;
      schedule_value: string;
      enabled: boolean;
    } | null;
  } | null>(null);
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [lastRefreshTime, setLastRefreshTime] = useState<Date>(new Date());
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [integrationSearchTerm, setIntegrationSearchTerm] = useState('');
  const [previewIntegrationType, setPreviewIntegrationType] = useState<IntegrationType | null>(
    null
  );
  const [isProvisioning, setIsProvisioning] = useState(false);
  const [provisionResult, setProvisionResult] = useState<ProvisionFreeResponse | null>(null);

  // Use refs to store polling controllers - use Map to track multiple
  const modalPollingControllers = useRef<Map<string, PollingController>>(new Map());
  const cardPollingControllers = useRef<Map<string, PollingController>>(new Map());
  const hasLoadedData = useRef(false); // Prevent double-loading in React Strict Mode

  const { runSafe } = useErrorHandler('Integrations');

  // Helper function to count active integrations by type
  const getActiveIntegrationCount = useCallback(
    (integrationType: string) => {
      return userIntegrations.filter(
        (integration) => integration.integration_type === integrationType && integration.enabled
      ).length;
    },
    [userIntegrations]
  );

  // Count configured integration types
  const configuredCount = useMemo(() => {
    return availableIntegrations.filter(
      (integrationType) => getActiveIntegrationCount(integrationType.integration_type) > 0
    ).length;
  }, [availableIntegrations, getActiveIntegrationCount]);

  // Total actions enabled across all active integrations
  const totalEnabledActions = useMemo(() => {
    return userIntegrations
      .filter((i) => i.enabled)
      .reduce((sum, i) => {
        const typeInfo = availableIntegrations.find(
          (t) => t.integration_type === i.integration_type
        );
        return sum + (typeInfo?.actions?.length ?? typeInfo?.action_count ?? 0);
      }, 0);
  }, [userIntegrations, availableIntegrations]);

  // Sort integrations: configured first, then by archetype, then by priority
  const sortedAvailableIntegrations = useMemo(() => {
    // Define archetype priority order (lower numbers = higher priority)
    // Based on actual archetypes from backend
    const archetypePriority: Record<string, number> = {
      // Security & Monitoring (highest priority)
      SIEM: 1,
      EDR: 2,
      ThreatIntel: 3,
      VulnerabilityManagement: 4,
      NetworkSecurity: 5,
      Sandbox: 6,
      EmailSecurity: 7,

      // Identity & Access
      IdentityProvider: 8,

      // Data & Infrastructure
      Lakehouse: 9,
      Geolocation: 10,

      // Operations & Collaboration
      TicketingSystem: 11,
      Notification: 12,
      Communication: 13,

      // AI & Analytics
      AI: 14,
    };

    return [...availableIntegrations].sort((a, b) => {
      const aConfigured = getActiveIntegrationCount(a.integration_type) > 0;
      const bConfigured = getActiveIntegrationCount(b.integration_type) > 0;

      // Configured integrations come first
      if (aConfigured !== bConfigured) {
        return aConfigured ? -1 : 1;
      }

      // Within each group, sort by archetype
      const aArchetype = a.archetypes?.[0] || 'ZZZ'; // Use first archetype, or put at end if none
      const bArchetype = b.archetypes?.[0] || 'ZZZ';
      const aArchetypePriority = archetypePriority[aArchetype] || 99;
      const bArchetypePriority = archetypePriority[bArchetype] || 99;

      if (aArchetypePriority !== bArchetypePriority) {
        return aArchetypePriority - bArchetypePriority;
      }

      // Within same archetype, sort by priority (descending)
      const aPriority = a.priority || 0;
      const bPriority = b.priority || 0;
      return bPriority - aPriority;
    });
  }, [availableIntegrations, getActiveIntegrationCount]);

  // Filter integrations based on search term
  const filteredAvailableIntegrations = useMemo(() => {
    if (!integrationSearchTerm.trim()) {
      return sortedAvailableIntegrations;
    }

    const searchLower = integrationSearchTerm.toLowerCase();
    return sortedAvailableIntegrations.filter((integrationType) => {
      // Search in display name
      if (integrationType.display_name.toLowerCase().includes(searchLower)) {
        return true;
      }

      // Search in integration type
      if (integrationType.integration_type.toLowerCase().includes(searchLower)) {
        return true;
      }

      // Search in archetypes
      if (
        integrationType.archetypes?.some((archetype) =>
          archetype.toLowerCase().includes(searchLower)
        )
      ) {
        return true;
      }

      // Search in description
      if (integrationType.description?.toLowerCase().includes(searchLower)) {
        return true;
      }

      return false;
    });
  }, [sortedAvailableIntegrations, integrationSearchTerm]);

  // Fetch available integration types from registry
  const fetchAvailableIntegrations = useCallback(async () => {
    try {
      return await backendApi.getIntegrationTypes();
    } catch (error) {
      logger.warn(
        'Failed to fetch integration types from registry',
        error,
        logCtx('fetchAvailableIntegrations')
      );
      // Return empty array on error - no fallback to mock data
      return [];
    }
  }, []);

  // Function to fetch user's integrations
  const fetchUserIntegrations = useCallback(async () => {
    try {
      return await backendApi.getIntegrations();
    } catch (error) {
      logger.warn(
        'Failed to fetch user integrations from backend',
        error,
        logCtx('fetchUserIntegrations')
      );
      return [];
    }
  }, []);

  // Add escape key handler for modals and click outside for dropdowns
  useEffect(() => {
    const handleEscapeKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;

      // Close action menu first
      if (showActionMenu) {
        setShowActionMenu(null);
        return;
      }
      if (deleteConfirmation.show) {
        setDeleteConfirmation({ show: false, integration: null });
        return;
      }
      if (previewIntegrationType) {
        setPreviewIntegrationType(null);
        return;
      }
      if (showCloseConfirmation) return; // Do nothing when confirmation is shown
      if (showCreateForm) {
        if (formHasChanges) {
          setShowCloseConfirmation(true);
        } else {
          setShowCreateForm(false);
          setSelectedIntegrationType(null);
        }
        return;
      }
      if (showDetails) {
        for (const controller of modalPollingControllers.current.values()) controller.stop();
        modalPollingControllers.current.clear();
        setShowDetails(false);
        setSelectedIntegration(null);
        setRunningActions(new Map());
        setCurrentRunId(null);
        setVisiblePasswords(new Set());
      }
    };

    const handleClickOutside = (event: MouseEvent) => {
      // Close action menu when clicking outside
      if (showActionMenu) {
        const target = event.target as HTMLElement;
        if (!target.closest('[data-action-menu]')) {
          setShowActionMenu(null);
        }
      }
    };

    document.addEventListener('keydown', handleEscapeKey);
    document.addEventListener('click', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleEscapeKey);
      document.removeEventListener('click', handleClickOutside);
    };
  }, [
    showCreateForm,
    showDetails,
    deleteConfirmation.show,
    formHasChanges,
    showCloseConfirmation,
    showActionMenu,
    previewIntegrationType,
  ]);

  // Clean up polling on unmount
  useEffect(() => {
    const modalControllers = modalPollingControllers.current;
    const cardControllers = cardPollingControllers.current;
    return () => {
      for (const controller of modalControllers.values()) controller.stop();
      modalControllers.clear();
      for (const controller of cardControllers.values()) controller.stop();
      cardControllers.clear();
    };
  }, []);

  // Fetch health status and last run for integrations
  const fetchIntegrationHealth = useCallback(async (integrations: Integration[]) => {
    return await Promise.all(
      integrations.map(async (integration) => {
        try {
          // Fetch health status
          const health = await backendApi.getIntegrationHealth(integration.integration_id);

          // Fetch last run from health_check managed resource
          let lastRun: ManagedRun | null = null;
          try {
            const runs = await backendApi.getManagedRuns(
              integration.integration_id,
              'health_check',
              { limit: 1 }
            );
            if (runs && runs.length > 0) {
              lastRun = runs[0];
            }
          } catch (error) {
            logger.warn(
              `Failed to fetch runs for ${integration.integration_id}`,
              error,
              logCtx('fetchIntegrationHealth')
            );
          }

          return {
            ...integration,
            health_status: health.status,
            last_run_at: lastRun?.completed_at || lastRun?.started_at || lastRun?.created_at,
            last_run_status: lastRun?.status as Integration['last_run_status'],
          };
        } catch (error) {
          logger.warn(
            `Failed to fetch health for ${integration.integration_id}`,
            error,
            logCtx('fetchIntegrationHealth')
          );
          return {
            ...integration,
            health_status: 'unknown' as const,
          };
        }
      })
    );
  }, []);

  // Refresh function that can be called on demand
  const refreshIntegrations = useCallback(
    async (showLoadingIndicator = false) => {
      if (showLoadingIndicator) {
        setLoading(true);
      } else {
        setIsRefreshing(true);
      }

      try {
        const integrations = await fetchUserIntegrations();
        // Ensure integrations is an array
        const integrationsList = Array.isArray(integrations) ? integrations : [];

        // ✨ Progressive Loading: Show integrations immediately
        setUserIntegrations(integrationsList);
        setLastRefreshTime(new Date());

        // ✅ Stop loading indicator - page is now interactive
        if (showLoadingIndicator) {
          setLoading(false);
        } else {
          setIsRefreshing(false);
        }

        // 🔄 Fetch health status in background, update UI as data arrives
        const integrationsWithHealth = await fetchIntegrationHealth(integrationsList);
        setUserIntegrations(Array.isArray(integrationsWithHealth) ? integrationsWithHealth : []);
        setLastRefreshTime(new Date());
      } catch (error) {
        logger.error('Failed to refresh integrations', error, logCtx('refreshIntegrations'));
        if (showLoadingIndicator) {
          setLoading(false);
        } else {
          setIsRefreshing(false);
        }
      }
    },
    [fetchUserIntegrations, fetchIntegrationHealth]
  );

  // Load data on mount
  useEffect(() => {
    // Prevent double-loading in React Strict Mode (development)
    if (hasLoadedData.current) {
      return;
    }
    hasLoadedData.current = true;

    const loadData = async () => {
      setLoading(true);

      // ✨ Load both available integrations (sidebar) and user integrations (main area) in parallel
      // Fire off refreshIntegrations immediately but DON'T wait for it - it handles its own loading state
      // and will show integration cards immediately, then fetch health checks in background
      void refreshIntegrations(false);

      // Only wait for available integrations (sidebar) to load
      const [availableTypes] = await runSafe(
        fetchAvailableIntegrations(),
        'fetchAvailableIntegrations',
        { action: 'fetching available integration types' }
      );

      if (availableTypes) {
        // Ensure we have an array - handle both direct array and wrapped response
        const integrationsList = Array.isArray(availableTypes) ? availableTypes : [];
        setAvailableIntegrations(integrationsList);
      }

      setLoading(false);
    };

    void loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty deps - only run once on mount

  // Periodic auto-refresh every 30 seconds
  useEffect(() => {
    // Don't refresh if modals are open or forms are being filled
    const shouldRefresh = !showDetails && !showCreateForm && !deleteConfirmation.show;

    if (!shouldRefresh) {
      return;
    }

    const intervalId = setInterval(() => {
      // Silent refresh - no loading indicator
      void refreshIntegrations(false);
      logger.debug('Auto-refreshing integrations...', null, logCtx('autoRefresh'));
    }, 30_000); // 30 seconds

    return () => {
      clearInterval(intervalId);
    };
  }, [refreshIntegrations, showDetails, showCreateForm, deleteConfirmation.show]);

  // Provision all free (no API key) integrations in one click
  const handleProvisionFree = async () => {
    setIsProvisioning(true);
    setProvisionResult(null);
    const [result, error] = await runSafe(
      backendApi.provisionFreeIntegrations(),
      'handleProvisionFree',
      { action: 'provisioning free integrations' }
    );
    setIsProvisioning(false);
    if (error || !result) return;
    setProvisionResult(result);
    // Refresh integration lists to show newly created ones
    void refreshIntegrations(false);
  };

  // Handle creating new integration
  const handleCreateIntegration = async (type: IntegrationType) => {
    try {
      // Fetch full integration type details including credential_schema
      const fullDetails = await backendApi.getIntegrationType(type.integration_type);
      setSelectedIntegrationType({ ...type, ...fullDetails });
      setShowCreateForm(true);
      setFormHasChanges(false);
      setCreateError(null);
    } catch (error) {
      logger.error('Failed to load integration type details:', error, logCtx('loadTypeDetails'));
      // Fallback to basic type if details fail to load
      setSelectedIntegrationType(type);
      setShowCreateForm(true);
      setFormHasChanges(false);
      setCreateError(null);
    }
  };

  // Handle clicking on an integration type in the sidebar - show preview
  const handlePreviewIntegrationType = async (type: IntegrationType) => {
    try {
      // Fetch full integration type details including tools
      const fullDetails = await backendApi.getIntegrationType(type.integration_type);
      setPreviewIntegrationType({ ...type, ...fullDetails });
    } catch (error) {
      logger.error('Failed to load integration type details:', error, logCtx('loadTypeDetails'));
      // Fallback to basic type if details fail to load
      setPreviewIntegrationType(type);
    }
  };

  // Helper: health status → dot color class
  const getHealthDotColor = (status: string | undefined): string => {
    switch (status) {
      case 'healthy':
        return 'bg-green-500';
      case 'degraded':
        return 'bg-yellow-500';
      case 'unhealthy':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  // Helper: parse error from integration creation API response.
  // RFC 9457 validation errors arrive in `errors` array; legacy in `detail` array.
  interface ValidationError {
    loc?: unknown[];
    type?: string;
    msg?: string;
  }

  const parseCreateError = (
    error: unknown,
    schemaProps?: Record<string, { display_name?: string }>
  ): string => {
    const axiosErr = error as {
      response?: { data?: Record<string, unknown> };
      message?: string;
    };
    const data = axiosErr.response?.data;

    // Extract validation error array from RFC 9457 `errors` or legacy `detail`
    let validationErrors: ValidationError[] | null = null;
    if (Array.isArray(data?.errors)) {
      validationErrors = data.errors as ValidationError[];
    } else if (Array.isArray(data?.detail)) {
      validationErrors = data.detail as ValidationError[];
    }

    if (validationErrors) {
      return validationErrors
        .map((ve: ValidationError) => {
          const field = ve.loc && ve.loc.length > 1 ? String(ve.loc.at(-1)) : 'field';
          const fieldName = schemaProps?.[field]?.display_name || field;
          switch (ve.type) {
            case 'missing':
              return `${fieldName} is required`;
            case 'string_pattern_mismatch':
              return `${fieldName}: Invalid format. ${ve.msg || 'Please check the format requirements'}`;
            case 'value_error':
              return `${fieldName}: ${ve.msg}`;
            default:
              return `${fieldName}: ${ve.msg || ve.type}`;
          }
        })
        .join('. ');
    }

    return extractApiErrorMessage(error, 'Failed to create integration.');
  };

  // Helper: build settings object from form data and schema
  const buildSettingsFromForm = (
    formData: FormData,
    schemaProps: Record<string, { type?: string; secret?: boolean }> | undefined
  ): Record<string, unknown> => {
    const settings: Record<string, unknown> = {};
    if (!schemaProps) return settings;
    for (const key of Object.keys(schemaProps)) {
      const value = formData.get(key);
      const property = schemaProps[key];
      if (property.type === 'integer' && value) {
        settings[key] = Number.parseInt(value as string, 10);
      } else if (property.type === 'boolean') {
        settings[key] = formData.get(key) === 'true';
      } else if (value) {
        settings[key] = value;
      }
    }
    return settings;
  };

  // Helper: determine display value for a settings field
  const getSettingsDisplayValue = (
    value: unknown,
    isSensitive: boolean,
    isVisible: boolean
  ): string => {
    if (isSensitive && !isVisible) return '••••••••';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean')
      return String(value);
    return JSON.stringify(value);
  };

  // Helper: check if a settings key is a credential field
  const isCredentialField = (key: string): boolean => {
    return (
      isSensitiveField(key) &&
      (key.includes('password') ||
        key.includes('secret') ||
        key.includes('key') ||
        (key.includes('token') && !key.includes('max_')))
    );
  };

  // Helper: safely stringify an unknown default value
  const stringifyDefault = (val: unknown): string | undefined => {
    if (val == null) return undefined;
    if (typeof val === 'object') return JSON.stringify(val);
    return String(val as string | number | boolean);
  };

  // Helper: schema property → input field type
  const getFieldType = (property: { secret?: boolean; type?: string }): string => {
    if (property.secret) return 'password';
    if (property.type === 'integer') return 'number';
    if (property.type === 'boolean') return 'checkbox';
    return 'text';
  };

  // Helper function to get integration icon with size option
  const getIntegrationIcon = (
    integrationType: string,
    size: 'small' | 'large' = 'small'
  ): React.ReactElement => {
    const sizeClass = size === 'large' ? 'w-8 h-8' : 'w-6 h-6';

    switch (integrationType) {
      case 'echo_edr':
        return <CircleStackIcon className={`${sizeClass} text-primary`} />;
      case 'databricks':
        return <CubeIcon className={`${sizeClass} text-primary`} />;
      case 'snowflake':
      case 's3':
        return <CloudIcon className={`${sizeClass} text-primary`} />;
      case 'elasticsearch':
        return <MagnifyingGlassIcon className={`${sizeClass} text-primary`} />;
      default:
        return <ServerIcon className={`${sizeClass} text-primary`} />;
    }
  };

  // Helper function to render integration icon
  const renderIntegrationIcon = (
    integrationType: string,
    size: 'small' | 'large' = 'small'
  ): React.ReactElement => {
    return getIntegrationIcon(integrationType, size);
  };

  // Helper function to check if an integration is an AI archetype
  const isAIArchetype = useCallback(
    (integration: Integration): boolean => {
      const type = availableIntegrations.find(
        (t) => t.integration_type === integration.integration_type
      );
      return type?.archetypes?.includes('AI') ?? false;
    },
    [availableIntegrations]
  );

  // Helper function to check if a field should be redacted
  const isSensitiveField = (fieldName: string): boolean => {
    const sensitivePatterns = [
      /^password$/i, // Exact match: password
      /^.*password.*$/i, // Contains password
      /^secret$/i, // Exact match: secret
      /^.*secret.*$/i, // Contains secret
      /^api[_-]?key$/i, // Exact match: api_key, api-key
      /^.*api[_-]?key.*$/i, // Contains api_key, api-key
      /^access_token$/i, // Exact match: access_token
      /^auth_token$/i, // Exact match: auth_token
      /^bearer_token$/i, // Exact match: bearer_token
      /^refresh_token$/i, // Exact match: refresh_token
      /^credential$/i, // Exact match: credential
      /^.*credential.*$/i, // Contains credential
      /^private[_-]?key$/i, // Exact match: private_key, private-key
      /^.*private[_-]?key.*$/i, // Contains private_key, private-key
      /^auth$/i, // Exact match: auth
      /^authorization$/i, // Exact match: authorization
      /^client_secret$/i, // Exact match: client_secret
      /^hec_token$/i, // Exact match: hec_token (Splunk specific)
    ];
    return sensitivePatterns.some((pattern) => pattern.test(fieldName));
  };

  // Recursively redact sensitive fields in objects, but only in credential/secret contexts
  const redactSensitiveData = (obj: unknown, isInCredentialContext = false): unknown => {
    if (typeof obj !== 'object' || obj === null) {
      return obj;
    }

    if (Array.isArray(obj)) {
      return obj.map((item: unknown) => redactSensitiveData(item, isInCredentialContext));
    }

    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
      // Check if we're entering a credential context
      const isCredentialKey = /^(credential|secret|auth|token)s?$/i.test(key);
      const shouldEnterCredentialContext = isCredentialKey || isInCredentialContext;

      // Only redact fields when in credential context OR if it's a top-level sensitive field
      const shouldRedact =
        (shouldEnterCredentialContext || key === 'password' || key === 'api_key') &&
        isSensitiveField(key);

      if (shouldRedact) {
        result[key] = '••••••••';
      } else if (typeof value === 'object') {
        result[key] = redactSensitiveData(value, shouldEnterCredentialContext);
      } else {
        result[key] = value;
      }
    }
    return result;
  };

  // Handle viewing integration details
  const handleViewDetails = async (integration: Integration) => {
    // Reset any running state when opening a new modal
    for (const controller of modalPollingControllers.current.values()) controller.stop();
    modalPollingControllers.current.clear();
    setRunningActions(new Map());
    setCurrentRunId(null);

    setSelectedIntegration(integration);
    setDetailsTab('overview');
    setShowDetails(true);
    setLoadingRuns(true);
    setLoadingSchedules(true);
    setLoadingCredentials(true);
    setManagedSchedules({});
    setManagedResourceKeys([]);
    setIntegrationCredentials([]);

    // Fetch runs and integration type details in parallel
    const [runsResult, integTypeResult] = await Promise.allSettled([
      backendApi.getManagedRuns(integration.integration_id, 'health_check', { limit: 10 }),
      backendApi.getIntegrationType(integration.integration_type),
    ]);

    // Handle runs result
    if (runsResult.status === 'fulfilled') {
      setIntegrationRuns(runsResult.value);
    } else {
      logger.error(
        'Failed to fetch integration runs',
        runsResult.reason,
        logCtx('handleViewDetails')
      );
      setIntegrationRuns([]);
    }
    setLoadingRuns(false);

    // Update the integration type with fresh data (includes actions)
    if (integTypeResult.status === 'fulfilled') {
      const freshType = integTypeResult.value;
      setAvailableIntegrations((prev) =>
        prev.map((t) => (t.integration_type === freshType.integration_type ? freshType : t))
      );
    }

    // Fetch managed resources (schedules + resource keys)
    try {
      const resources = await backendApi.getManagedResources(integration.integration_id);
      setManagedResourceKeys(Object.keys(resources));
      const schedulesMap: Record<string, ManagedSchedule> = {};

      for (const [resourceKey, resource] of Object.entries(resources)) {
        if ((resource as { schedule_id?: string }).schedule_id) {
          try {
            const schedule = await backendApi.getManagedSchedule(
              integration.integration_id,
              resourceKey
            );
            schedulesMap[resourceKey] = schedule;
          } catch (error) {
            logger.error(
              `Failed to fetch schedule for ${resourceKey}`,
              error,
              logCtx('fetchSchedules')
            );
          }
        }
      }

      setManagedSchedules(schedulesMap);
    } catch (error) {
      logger.error('Failed to fetch managed resources', error, logCtx('fetchSchedules'));
    }
    setLoadingSchedules(false);

    // Fetch credentials linked to this integration
    try {
      const credLinks = await backendApi.getIntegrationCredentials(integration.integration_id);
      // Fetch full details (including secrets) for each credential
      const details: CredentialDetail[] = [];
      for (const link of credLinks) {
        try {
          const full = (await backendApi.getCredential(link.credential_id)) as CredentialDetail;
          full.is_primary = link.is_primary;
          full.purpose = link.purpose;
          full.created_at = full.created_at ?? link.created_at;
          details.push(full);
        } catch {
          // Skip credentials that can't be fetched
        }
      }
      setIntegrationCredentials(details);
    } catch (error) {
      logger.error('Failed to fetch integration credentials', error, logCtx('fetchCredentials'));
    }
    setLoadingCredentials(false);
  };

  // Helper: update a single run in the runs list
  const updateRunInList = (targetRunId: string, runDetails: ManagedRun) => {
    setIntegrationRuns((prevRuns) =>
      prevRuns.map((run) =>
        run.task_run_id === targetRunId
          ? {
              ...run,
              status: runDetails.status,
              completed_at: runDetails.completed_at,
              started_at: runDetails.started_at,
            }
          : run
      )
    );
  };

  // Helper: update integration's last run info in the main list
  const updateIntegrationRunInfo = (integrationId: string, runDetails: ManagedRun) => {
    setUserIntegrations((prev) =>
      prev.map((int) =>
        int.integration_id === integrationId
          ? {
              ...int,
              last_run_at:
                runDetails.completed_at || runDetails.started_at || runDetails.created_at,
              last_run_status: runDetails.status as Integration['last_run_status'],
            }
          : int
      )
    );
  };

  // Helper: remove action from running set
  const removeRunningAction = (pollKey: string) => {
    setRunningActions((prev) => {
      const newMap = new Map(prev);
      newMap.delete(pollKey);
      return newMap;
    });
  };

  // Cancel a running managed resource run (stops polling only — backend runs to completion)
  const handleCancelManagedRun = (
    integrationId: string,
    resourceKey: string,
    fromCard: boolean
  ) => {
    const pollKey = `${integrationId}-${resourceKey}`;

    // Stop polling immediately
    const controllers = fromCard ? cardPollingControllers : modalPollingControllers;
    controllers.current.get(pollKey)?.stop();
    controllers.current.delete(pollKey);

    removeRunningAction(pollKey);
    if (fromCard) {
      setRunningIntegrationId(null);
    } else {
      setCurrentRunId(null);
      void refreshIntegrationRuns(integrationId);
    }
  };

  // Find the running action key for an integration (for card-view cancel)
  const findRunningActionForIntegration = (integrationId: string): string | null => {
    for (const [key] of runningActions) {
      if (key.startsWith(`${integrationId}-`)) {
        return key.replace(`${integrationId}-`, '');
      }
    }
    return null;
  };

  // Helper: fetch health and update integration after a run completes
  const refreshIntegrationHealth = async (integrationId: string, runDetails: ManagedRun) => {
    try {
      const health = await backendApi.getIntegrationHealth(integrationId);
      setUserIntegrations((prev) =>
        prev.map((int) =>
          int.integration_id === integrationId
            ? {
                ...int,
                health_status: health.status,
                last_run_at:
                  runDetails.completed_at || runDetails.started_at || runDetails.created_at,
                last_run_status: runDetails.status as Integration['last_run_status'],
              }
            : int
        )
      );
    } catch (error) {
      logger.error(
        'Failed to update integration health after run',
        error,
        logCtx('refreshIntegrationHealth')
      );
    }
  };

  // Helper function to refresh integration runs
  const refreshIntegrationRuns = async (integrationId: string) => {
    try {
      const runs = await backendApi.getManagedRuns(integrationId, 'health_check', { limit: 10 });
      setIntegrationRuns(runs);
      return runs;
    } catch (error) {
      logger.error('Failed to fetch integration runs', error, logCtx('refreshIntegrationRuns'));
      return [];
    }
  };

  // Poll for managed run status (for modal)
  const pollModalManagedRunStatus = (integrationId: string, resourceKey: string, runId: string) => {
    const pollKey = `${integrationId}-${resourceKey}`;

    const existingController = modalPollingControllers.current.get(pollKey);
    if (existingController) {
      existingController.stop();
    }

    const controller = startPolling<ManagedRun>({
      pollFn: async () => {
        const runs = await backendApi.getManagedRuns(integrationId, resourceKey, { limit: 1 });
        return (
          runs[0] || { task_run_id: runId, status: 'running', created_at: new Date().toISOString() }
        );
      },

      shouldStop: (runDetails) => {
        return runDetails.status === 'completed' || runDetails.status === 'failed';
      },

      onPoll: (runDetails) => {
        updateRunInList(runId, runDetails);
      },

      onComplete: (runDetails) => {
        removeRunningAction(pollKey);
        setCurrentRunId(null);
        void refreshIntegrationRuns(integrationId);
        updateIntegrationRunInfo(integrationId, runDetails);
        logger.info(
          `Managed run ${runDetails.status}:`,
          runDetails,
          logCtx('pollModalManagedRunStatus')
        );
        modalPollingControllers.current.delete(pollKey);
      },

      onError: (error) => {
        logger.error('Failed to check run status', error, logCtx('pollModalManagedRunStatus'));
        removeRunningAction(pollKey);
        setCurrentRunId(null);
        modalPollingControllers.current.delete(pollKey);
      },

      maxAttempts: 60,
      delayIntervals: [1000, 2000, 2000, 3000, 5000],
    });

    modalPollingControllers.current.set(pollKey, controller);
  };

  // Poll for managed run status (for card)
  const pollCardManagedRunStatus = (integrationId: string, resourceKey: string, runId: string) => {
    const pollKey = `${integrationId}-${resourceKey}`;

    const existingController = cardPollingControllers.current.get(pollKey);
    if (existingController) {
      existingController.stop();
    }

    const controller = startPolling<ManagedRun>({
      pollFn: async () => {
        const runs = await backendApi.getManagedRuns(integrationId, resourceKey, { limit: 1 });
        return (
          runs[0] || { task_run_id: runId, status: 'running', created_at: new Date().toISOString() }
        );
      },

      shouldStop: (runDetails) => {
        return runDetails.status === 'completed' || runDetails.status === 'failed';
      },

      onPoll: (runDetails) => {
        updateIntegrationRunInfo(integrationId, runDetails);
      },

      onComplete: (runDetails) => {
        setRunningIntegrationId(null);
        logger.info(
          `Managed run ${runDetails.status} for ${integrationId}`,
          runDetails,
          logCtx('pollCardManagedRunStatus')
        );
        cardPollingControllers.current.delete(pollKey);
        void refreshIntegrationHealth(integrationId, runDetails);
      },

      onError: (error) => {
        logger.error('Failed to check run status', error, logCtx('pollCardManagedRunStatus'));
        setRunningIntegrationId(null);
        cardPollingControllers.current.delete(pollKey);
      },

      maxAttempts: 60,
      delayIntervals: [1000, 2000, 2000, 3000, 5000],
    });

    cardPollingControllers.current.set(pollKey, controller);
  };

  // Handle running a managed resource (e.g. health_check, alert_ingestion)
  const handleRunManagedResource = async (
    integration: Integration,
    resourceKey: string = 'health_check',
    fromCard: boolean = false
  ) => {
    const runKey = `${integration.integration_id}-${resourceKey}`;

    if (runningActions.has(runKey)) {
      logger.debug(
        `Resource ${resourceKey} is already running for ${integration.integration_id}`,
        null,
        logCtx('handleRunManagedResource')
      );
      return;
    }

    if (fromCard) {
      setRunningIntegrationId(integration.integration_id);
    }

    setRunningActions((prev) => new Map(prev).set(runKey, 'starting'));

    try {
      const result = await backendApi.triggerManagedRun(integration.integration_id, resourceKey);

      logger.info('Managed run triggered', result, logCtx('handleRunManagedResource'));
      setCurrentRunId(result.task_run_id);

      setRunningActions((prev) => new Map(prev).set(runKey, result.task_run_id));

      if (fromCard) {
        setUserIntegrations((prev) =>
          prev.map((int) =>
            int.integration_id === integration.integration_id
              ? { ...int, last_run_status: 'running' as const }
              : int
          )
        );
        pollCardManagedRunStatus(integration.integration_id, resourceKey, result.task_run_id);
      } else {
        const newRun: ManagedRun = {
          task_run_id: result.task_run_id,
          status: 'running',
          created_at: new Date().toISOString(),
        };
        setIntegrationRuns((prev) => [newRun, ...prev.slice(0, 9)]);
        pollModalManagedRunStatus(integration.integration_id, resourceKey, result.task_run_id);
      }
    } catch (error) {
      logger.error('Failed to trigger managed run', error, logCtx('handleRunManagedResource'));
      setRunningActions((prev) => {
        const newMap = new Map(prev);
        newMap.delete(runKey);
        return newMap;
      });
      if (fromCard) {
        setRunningIntegrationId(null);
      }
      setCurrentRunId(null);
    }
  };

  // Handle enable/disable toggle
  const handleToggleIntegration = async (integration: Integration) => {
    try {
      await (integration.enabled
        ? backendApi.disableIntegration(integration.integration_id)
        : backendApi.enableIntegration(integration.integration_id));

      // Refresh integrations list
      await refreshIntegrations(false);
    } catch (error) {
      logger.error('Failed to toggle integration', error, logCtx('handleToggleIntegration'));
    }
  };

  // Handle save settings
  const handleSaveSettings = async () => {
    if (!selectedIntegration) return;

    setIsSavingSettings(true);
    try {
      // Merge edited settings with existing settings
      const updatedSettings = {
        ...selectedIntegration.settings,
        ...editedSettings,
      };

      await backendApi.updateIntegration(selectedIntegration.integration_id, {
        settings: updatedSettings,
      });

      // Update local state
      setSelectedIntegration({
        ...selectedIntegration,
        settings: updatedSettings,
      });

      // Clear edit mode
      setSettingsEditMode(false);
      setEditedSettings({});

      // Refresh integrations list
      await refreshIntegrations(false);
    } catch (error) {
      logger.error('Failed to save settings', error, logCtx('handleSaveSettings'));
    } finally {
      setIsSavingSettings(false);
    }
  };

  // Handle setting an AI integration as primary (mutually exclusive, radio-button semantics).
  // The backend requires at least one primary to always exist, so we only support setting a NEW
  // primary — not un-setting the current one. Order matters: set the new primary first, then
  // clear others (backend rejects clearing the sole primary).
  const handleSetAIPrimary = async (integration: Integration) => {
    const updatedSettings = { ...integration.settings, is_primary: true };
    await backendApi.updateIntegration(integration.integration_id, { settings: updatedSettings });

    // Mutual exclusivity: unset all other AI integrations now that a new primary is set
    const others = userIntegrations.filter(
      (i) => i.integration_id !== integration.integration_id && isAIArchetype(i)
    );
    await Promise.all(
      others.map((i) =>
        backendApi.updateIntegration(i.integration_id, {
          settings: { ...i.settings, is_primary: false },
        })
      )
    );

    // Update local state immediately (optimistic)
    setSelectedIntegration({ ...integration, settings: updatedSettings });
    await refreshIntegrations(false);
  };

  // Handle save schedule via managed resources API
  const handleSaveSchedule = async () => {
    if (!selectedIntegration || !editingSchedule) return;

    setSavingSchedule(true);
    try {
      const { actionId: resourceKey, schedule } = editingSchedule;

      if (!schedule) {
        // Disable the schedule (managed schedules can't be deleted, only disabled)
        const existing = managedSchedules[resourceKey];
        if (existing) {
          const updated = await backendApi.updateManagedSchedule(
            selectedIntegration.integration_id,
            resourceKey,
            { enabled: false }
          );
          setManagedSchedules((prev) => ({ ...prev, [resourceKey]: updated }));
        }
      } else {
        // Create or update via managed schedule API (always PUT)
        const updated = await backendApi.updateManagedSchedule(
          selectedIntegration.integration_id,
          resourceKey,
          {
            schedule_value: schedule.schedule_value,
            enabled: schedule.enabled,
          }
        );
        setManagedSchedules((prev) => ({ ...prev, [resourceKey]: updated }));
      }

      setEditingSchedule(null);
    } catch (error) {
      logger.error('Failed to save schedule', error, logCtx('handleSaveSchedule'));
    } finally {
      setSavingSchedule(false);
    }
  };

  // Handle delete integration
  const handleDeleteIntegration = async () => {
    if (!deleteConfirmation.integration) return;

    try {
      await backendApi.deleteIntegration(deleteConfirmation.integration.integration_id);

      // Refresh integrations list
      await refreshIntegrations(false);

      // Close confirmation modal
      setDeleteConfirmation({ show: false, integration: null });
    } catch (error) {
      logger.error('Failed to delete integration', error, logCtx('handleDeleteIntegration'));
    }
  };

  // Render health status icon
  const renderHealthIcon = (
    status?: Integration['health_status'],
    size: 'small' | 'normal' = 'normal'
  ) => {
    const sizeClass = size === 'small' ? 'w-3 h-3' : 'w-5 h-5';
    switch (status) {
      case 'healthy': {
        return <CheckCircleIcon className={`${sizeClass} text-green-400`} />;
      }
      case 'degraded': {
        return <ExclamationCircleIcon className={`${sizeClass} text-yellow-400`} />;
      }
      case 'unhealthy': {
        return <ExclamationCircleIcon className={`${sizeClass} text-red-400`} />;
      }
      default: {
        return <ServerIcon className={`${sizeClass} text-gray-400`} />;
      }
    }
  };

  // Render run status badge
  const renderRunStatus = (status?: string) => {
    if (!status) return null;

    const statusColors = {
      completed: 'bg-green-500/20 text-green-400',
      failed: 'bg-red-500/20 text-red-400',
      running: 'bg-blue-500/20 text-blue-400',
      pending: 'bg-yellow-500/20 text-yellow-400',
    };

    return (
      <span
        className={`px-2 py-1 rounded-sm text-xs ${statusColors[status as keyof typeof statusColors] || 'bg-gray-500/20 text-gray-400'}`}
      >
        {status}
      </span>
    );
  };

  // Get archetype badge color
  const getArchetypeBadgeColor = (archetype: string): string => {
    const archetypeColors: Record<string, string> = {
      // Security & Monitoring (from actual backend data)
      SIEM: 'bg-blue-500/20 text-blue-400',
      EDR: 'bg-green-500/20 text-green-400',
      ThreatIntel: 'bg-purple-500/20 text-purple-400',
      Sandbox: 'bg-orange-500/20 text-orange-400',
      NetworkSecurity: 'bg-cyan-500/20 text-cyan-400',
      VulnerabilityManagement: 'bg-red-500/20 text-red-400',
      EmailSecurity: 'bg-amber-500/20 text-amber-400',

      // Identity & Access
      IdentityProvider: 'bg-indigo-500/20 text-indigo-400',

      // Data & Infrastructure
      Lakehouse: 'bg-emerald-500/20 text-emerald-400',
      Geolocation: 'bg-teal-500/20 text-teal-400',

      // Operations & Collaboration
      TicketingSystem: 'bg-fuchsia-500/20 text-fuchsia-400',
      Notification: 'bg-yellow-500/20 text-yellow-400',
      Communication: 'bg-pink-500/20 text-pink-400',

      // AI & Analytics
      AI: 'bg-rose-500/20 text-rose-400',
    };
    return archetypeColors[archetype] || 'bg-slate-500/20 text-slate-400';
  };

  return (
    <ErrorBoundary component="IntegrationsPage">
      <div className="flex h-full bg-dark-900">
        {/* Available Integrations Sidebar */}
        <div className="w-64 bg-dark-800 border-l border-r border-gray-700 p-4 overflow-y-auto shrink-0">
          <h2 className="text-lg font-semibold text-white mb-2">Available Integrations</h2>
          <div className="mb-4 text-sm text-gray-400">
            <span className="font-medium text-primary">{configuredCount}</span> of{' '}
            {availableIntegrations.length} configured
          </div>

          {/* Search Input */}
          <div className="mb-4">
            <div className="relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={integrationSearchTerm}
                onChange={(e) => setIntegrationSearchTerm(e.target.value)}
                placeholder="Search integrations..."
                className="w-full pl-9 pr-3 py-2 bg-dark-700 border border-gray-600 rounded-sm text-white text-sm placeholder-gray-500 focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>
            {integrationSearchTerm && (
              <div className="mt-2 text-xs text-gray-400">
                Found {filteredAvailableIntegrations.length} integration
                {filteredAvailableIntegrations.length === 1 ? '' : 's'}
              </div>
            )}
          </div>

          {loading ? (
            <div className="space-y-3 p-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="rounded-lg bg-dark-700 p-3 animate-pulse">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-md bg-gray-600" />
                    <div className="flex-1 space-y-2">
                      <div className="h-3 w-24 bg-gray-600 rounded" />
                      <div className="h-2 w-36 bg-gray-700 rounded" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              {availableIntegrations.length === 0 && (
                <div className="text-gray-400 text-sm p-3">
                  No integration types available. Please check backend configuration.
                </div>
              )}
              {availableIntegrations.length > 0 && filteredAvailableIntegrations.length === 0 && (
                <div className="text-gray-400 text-sm p-3">
                  No integrations match your search. Try a different term.
                </div>
              )}
              {filteredAvailableIntegrations.length > 0 && (
                <>
                  {filteredAvailableIntegrations.map((integrationType, index) => {
                    const activeCount = getActiveIntegrationCount(integrationType.integration_type);
                    const isConfigured = activeCount > 0;
                    const prevIntegrationType =
                      index > 0 ? filteredAvailableIntegrations[index - 1] : null;
                    const prevConfigured = prevIntegrationType
                      ? getActiveIntegrationCount(prevIntegrationType.integration_type) > 0
                      : false;
                    const showSeparator = index > 0 && prevConfigured && !isConfigured;

                    return (
                      <React.Fragment key={integrationType.integration_type}>
                        {showSeparator && (
                          <div className="py-2">
                            <div className="border-t border-gray-700 relative">
                              <span className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2 px-2 bg-dark-800 text-xs text-gray-400">
                                Available to Configure
                              </span>
                            </div>
                          </div>
                        )}
                        <button
                          onClick={() => void handlePreviewIntegrationType(integrationType)}
                          className={`w-full p-3 rounded-lg transition-colors text-left ${
                            previewIntegrationType?.integration_type ===
                            integrationType.integration_type
                              ? 'bg-primary/20 ring-2 ring-primary'
                              : 'bg-dark-700 hover:bg-dark-600'
                          } ${!isConfigured ? 'opacity-60' : ''}`}
                          title={integrationType.description || integrationType.display_name}
                        >
                          <div className="flex items-center space-x-3">
                            <div className="shrink-0">
                              {renderIntegrationIcon(integrationType.integration_type, 'large')}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between mb-1">
                                <div
                                  className={`font-medium ${isConfigured ? 'text-white' : 'text-gray-400'}`}
                                >
                                  {integrationType.display_name}
                                </div>
                                {activeCount > 0 && (
                                  <span className="inline-flex items-center justify-center w-5 h-5 text-xs font-medium text-white bg-green-600 rounded-full">
                                    {activeCount}
                                  </span>
                                )}
                              </div>

                              {/* Archetype badges */}
                              {integrationType.archetypes &&
                                integrationType.archetypes.length > 0 && (
                                  <div className="flex flex-wrap gap-1 mb-1">
                                    {integrationType.archetypes.slice(0, 2).map((archetype) => (
                                      <span
                                        key={archetype}
                                        className={`px-1.5 py-0.5 rounded-sm text-[10px] font-medium ${getArchetypeBadgeColor(archetype)}`}
                                      >
                                        {archetype}
                                      </span>
                                    ))}
                                  </div>
                                )}

                              <div className="text-xs mt-1 text-gray-400">
                                {integrationType.actions?.length ??
                                  integrationType.action_count ??
                                  0}{' '}
                                action
                                {(integrationType.actions?.length ??
                                  integrationType.action_count ??
                                  0) === 1
                                  ? ''
                                  : 's'}
                              </div>
                            </div>
                          </div>
                        </button>
                      </React.Fragment>
                    );
                  })}
                </>
              )}
            </div>
          )}
        </div>

        {/* Main Content Area */}
        <div className="flex-1 p-6 overflow-y-auto">
          <div className="w-full">
            <div className="mb-6">
              <div className="flex justify-between items-start">
                <div>
                  <h1 className="text-2xl font-semibold text-white">Your Integrations</h1>
                  <p className="text-gray-400 mt-1">
                    {userIntegrations.length} integration{userIntegrations.length !== 1 ? 's' : ''}
                    {' · '}
                    {totalEnabledActions} action{totalEnabledActions !== 1 ? 's' : ''} enabled
                  </p>
                </div>
                <div className="flex items-center space-x-4">
                  <span className="text-xs text-gray-400">
                    Last updated: {lastRefreshTime.toLocaleTimeString()}
                  </span>
                  <button
                    onClick={() => void handleProvisionFree()}
                    disabled={isProvisioning}
                    className="flex items-center space-x-2 px-3 py-1.5 bg-primary hover:bg-primary-dark rounded-sm transition-colors text-sm text-white font-medium disabled:opacity-50"
                    title="Add all free integrations that don't require API keys"
                  >
                    <BoltIcon className={`w-4 h-4 ${isProvisioning ? 'animate-pulse' : ''}`} />
                    <span>{isProvisioning ? 'Provisioning...' : 'Add Free Integrations'}</span>
                  </button>
                  <button
                    onClick={() => void refreshIntegrations(false)}
                    disabled={isRefreshing}
                    className="flex items-center space-x-2 px-3 py-1.5 bg-dark-700 hover:bg-dark-600 rounded-sm transition-colors text-sm text-white disabled:opacity-50"
                    title="Refresh integrations"
                  >
                    <ArrowPathIcon className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
                    <span>Refresh</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Provision Free Result Banner */}
            {provisionResult && (
              <div className="mb-6 bg-dark-800 border border-green-500/30 rounded-lg p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-start space-x-3">
                    <CheckCircleIcon className="w-5 h-5 text-green-400 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="text-white font-medium">Free integrations provisioned</p>
                      <p className="text-gray-400 text-sm mt-1">
                        {provisionResult.created} created, {provisionResult.already_exists} already
                        existed
                      </p>
                      {provisionResult.integrations.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-2">
                          {provisionResult.integrations.map((i) => (
                            <span
                              key={i.integration_id}
                              className={`inline-flex items-center px-2 py-0.5 rounded text-xs border ${
                                i.status === 'created'
                                  ? 'bg-green-500/10 text-green-400 border-green-500/20'
                                  : 'bg-gray-500/10 text-gray-400 border-gray-500/20'
                              }`}
                            >
                              {i.name}
                              {i.status === 'created' && (
                                <CheckCircleIcon className="w-3 h-3 ml-1" />
                              )}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => setProvisionResult(null)}
                    className="text-gray-400 hover:text-white"
                  >
                    <XCircleIcon className="w-5 h-5" />
                  </button>
                </div>
              </div>
            )}

            {/* Integration Cards */}
            {userIntegrations.length === 0 ? (
              <div className="bg-dark-800 rounded-lg p-12 text-center">
                <ServerIcon className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                <h3 className="text-xl font-medium text-white mb-2">No integrations yet</h3>
                <p className="text-gray-400">Click on an available integration to get started</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {userIntegrations.map((integration) => (
                  <div
                    key={integration.integration_id}
                    role="button"
                    tabIndex={0}
                    className="bg-dark-800 rounded-lg p-6 hover:ring-2 hover:ring-primary/50 transition-all cursor-pointer"
                    onClick={() => void handleViewDetails(integration)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        void handleViewDetails(integration);
                      }
                    }}
                  >
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex items-center space-x-3">
                        <div className="relative">
                          {renderIntegrationIcon(integration.integration_type, 'small')}
                          <div className="absolute -bottom-1 -right-1 bg-dark-800 rounded-full p-0.5">
                            {renderHealthIcon(integration.health_status, 'small')}
                          </div>
                        </div>
                        <div>
                          <h3 className="text-white font-medium">{integration.name}</h3>
                          <p className="text-gray-400 text-sm">{integration.integration_type}</p>
                        </div>
                      </div>

                      {/* Enable/Disable Toggle Switch */}
                      <div className="flex flex-col items-end space-y-1">
                        <span className="text-xs text-gray-400">
                          {integration.enabled ? 'Active' : 'Inactive'}
                        </span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleToggleIntegration(integration);
                          }}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-hidden focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-dark-800 ${
                            integration.enabled ? 'bg-green-500' : 'bg-gray-600'
                          }`}
                          role="switch"
                          aria-checked={integration.enabled}
                          title={
                            integration.enabled
                              ? 'Click to disable integration'
                              : 'Click to enable integration'
                          }
                        >
                          <span className="sr-only">
                            {integration.enabled ? 'Disable' : 'Enable'} integration
                          </span>
                          <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                              integration.enabled ? 'translate-x-6' : 'translate-x-1'
                            }`}
                          />
                        </button>
                      </div>
                    </div>

                    {/* Description with consistent spacing */}
                    <p className="text-gray-400 text-sm mb-4 min-h-[20px]">
                      {integration.description || ''}
                    </p>

                    {/* Last Run Info - Always show the box for consistency */}
                    <div className="mb-4 p-3 bg-dark-700 rounded-sm min-h-[44px] flex items-center">
                      {integration.last_run_at ? (
                        <div className="flex items-center justify-between text-sm w-full">
                          <span className="text-gray-400">Last run:</span>
                          <div className="flex items-center space-x-2">
                            {renderRunStatus(integration.last_run_status)}
                            <span className="text-gray-400 text-xs">
                              {new Date(integration.last_run_at).toLocaleString([], {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                                second: '2-digit',
                              })}
                            </span>
                          </div>
                        </div>
                      ) : (
                        <span className="text-gray-400 text-sm w-full text-center">
                          No runs yet
                        </span>
                      )}
                    </div>

                    {/* Action Buttons */}
                    <div className="flex space-x-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleViewDetails(integration);
                        }}
                        className="flex-1 bg-dark-700 hover:bg-dark-600 px-3 py-2 rounded-sm transition-colors text-sm text-white"
                        title="View integration details and run history"
                      >
                        View Details
                      </button>
                      <div className="relative flex-1" data-action-menu>
                        {runningIntegrationId === integration.integration_id ? (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              const actionKey = findRunningActionForIntegration(
                                integration.integration_id
                              );
                              if (actionKey) {
                                handleCancelManagedRun(integration.integration_id, actionKey, true);
                              }
                            }}
                            className="w-full px-3 py-2 rounded transition-colors text-sm flex items-center justify-center space-x-1 bg-red-500/20 text-red-400 hover:bg-red-500/30"
                            title="Cancel running action"
                          >
                            <XCircleIcon className="w-4 h-4" />
                            <span>Cancel</span>
                          </button>
                        ) : (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              const integType = availableIntegrations.find(
                                (t) => t.integration_type === integration.integration_type
                              );
                              const actions = integType?.actions ?? [];
                              if (actions.length > 1) {
                                setShowActionMenu(
                                  showActionMenu === integration.integration_id
                                    ? null
                                    : integration.integration_id
                                );
                              } else {
                                const firstAction = actions[0];
                                void handleRunManagedResource(
                                  integration,
                                  firstAction?.action_id ?? 'health_check',
                                  true
                                );
                              }
                            }}
                            className="w-full px-3 py-2 rounded transition-colors text-sm flex items-center justify-center space-x-1 bg-primary/20 text-primary hover:bg-primary/30"
                            title="Run action now"
                          >
                            <ArrowPathIcon className="w-4 h-4" />
                            <span>Run</span>
                          </button>
                        )}

                        {/* Action dropdown menu */}
                        {showActionMenu === integration.integration_id && (
                          <div className="absolute top-full mt-1 left-0 right-0 bg-dark-700 border border-gray-600 rounded-sm shadow-lg z-10">
                            {availableIntegrations
                              .find((t) => t.integration_type === integration.integration_type)
                              ?.actions?.map((action) => {
                                const runKey = `${integration.integration_id}-${action.action_id}`;
                                const isRunning = runningActions.has(runKey);
                                return (
                                  <button
                                    key={action.action_id}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setShowActionMenu(null);
                                      if (isRunning) {
                                        handleCancelManagedRun(
                                          integration.integration_id,
                                          action.action_id,
                                          true
                                        );
                                      } else {
                                        void handleRunManagedResource(
                                          integration,
                                          action.action_id,
                                          true
                                        );
                                      }
                                    }}
                                    className={`w-full px-3 py-2 text-left text-sm transition-colors flex items-center justify-between ${
                                      isRunning
                                        ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                                        : 'hover:bg-dark-600 text-white'
                                    }`}
                                  >
                                    <span>{isRunning ? `Cancel ${action.name}` : action.name}</span>
                                    {isRunning && <XCircleIcon className="w-3 h-3" />}
                                  </button>
                                );
                              })}
                          </div>
                        )}
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteConfirmation({ show: true, integration });
                        }}
                        className="p-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-sm transition-colors"
                        title="Delete integration"
                      >
                        <TrashIcon className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Create Integration Modal - Wizard or Classic Form */}
        {showCreateForm && selectedIntegrationType && useWizard ? (
          <IntegrationSetupWizard
            integrationType={
              selectedIntegrationType as unknown as React.ComponentProps<
                typeof IntegrationSetupWizard
              >['integrationType']
            }
            existingIntegrations={userIntegrations}
            onClose={() => {
              setShowCreateForm(false);
              setSelectedIntegrationType(null);
              setFormHasChanges(false);
              setCreateError(null);
            }}
            onSuccess={() => {
              // Refresh integrations list
              void refreshIntegrations(false);

              // Close modal
              setShowCreateForm(false);
              setSelectedIntegrationType(null);
              setFormHasChanges(false);
              setCreateError(null);
            }}
          />
        ) : (
          showCreateForm &&
          selectedIntegrationType && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
              <div className="bg-dark-800 rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
                <div className="flex justify-between items-start mb-4">
                  <h2 className="text-xl font-semibold text-white">
                    Add {selectedIntegrationType.display_name} Integration
                  </h2>
                  <button
                    onClick={() => {
                      if (formHasChanges) {
                        setShowCloseConfirmation(true);
                      } else {
                        setShowCreateForm(false);
                        setSelectedIntegrationType(null);
                      }
                    }}
                    className="text-gray-400 hover:text-white"
                  >
                    <span className="text-2xl">&times;</span>
                  </button>
                </div>

                <form
                  className="space-y-4"
                  onChange={() => setFormHasChanges(true)}
                  onSubmit={(e) => {
                    e.preventDefault();
                    void (async () => {
                      const formData = new FormData(e.currentTarget);

                      // Build settings object from schema
                      const schemaProps = selectedIntegrationType.settings_schema?.properties as
                        | Record<string, { type?: string; secret?: boolean }>
                        | undefined;
                      const settings = buildSettingsFromForm(formData, schemaProps);

                      try {
                        setCreateError(null);

                        // Get integration_id from settings or form
                        const integrationId =
                          (settings.integration_id as string | undefined) ||
                          (formData.get('integration_id') as string);

                        // Remove integration_id from settings if it exists
                        // eslint-disable-next-line @typescript-eslint/no-unused-vars, sonarjs/no-unused-vars
                        const { integration_id: _omitted, ...cleanSettings } = settings;

                        const newIntegration = await backendApi.createIntegration({
                          integration_id: integrationId,
                          integration_type: selectedIntegrationType.integration_type,
                          name: formData.get('integration_name') as string,
                          description: formData.get('integration_description') as string,
                          settings: cleanSettings,
                        });

                        logger.info(
                          'Integration created:',
                          newIntegration,
                          logCtx('handleCreateIntegration')
                        );

                        // Refresh integrations list with health status
                        const integrations = await fetchUserIntegrations();
                        const integrationsWithHealth = await fetchIntegrationHealth(integrations);
                        setUserIntegrations(integrationsWithHealth);

                        // Close modal
                        setShowCreateForm(false);
                        setSelectedIntegrationType(null);
                        setFormHasChanges(false);
                        setCreateError(null);
                      } catch (error: unknown) {
                        logger.error(
                          'Failed to create integration',
                          error,
                          logCtx('handleCreateIntegration')
                        );
                        const displayNameMap = selectedIntegrationType.settings_schema
                          ?.properties as Record<string, { display_name?: string }> | undefined;
                        setCreateError(parseCreateError(error, displayNameMap));
                      }
                    })();
                  }}
                >
                  <div>
                    <label
                      htmlFor="integration_name"
                      className="block text-sm font-medium text-gray-300 mb-1"
                    >
                      Integration Name <span className="text-red-400">*</span>
                    </label>
                    <input
                      id="integration_name"
                      name="integration_name"
                      type="text"
                      required
                      className="w-full bg-dark-700 border border-gray-600 rounded-sm px-3 py-2 text-white focus:outline-hidden focus:ring-2 focus:ring-primary"
                      placeholder={`My ${selectedIntegrationType.display_name}`}
                    />
                    {createError && (
                      <div className="mt-2 p-3 bg-red-500/10 border border-red-500/20 rounded-sm">
                        <div className="flex items-start space-x-2">
                          <XCircleIcon className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                          <div>
                            <p className="text-sm font-medium text-red-400">
                              Error Creating Integration
                            </p>
                            <p className="text-sm text-red-300 mt-1">{createError}</p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  <div>
                    <label
                      htmlFor="integration_description"
                      className="block text-sm font-medium text-gray-300 mb-1"
                    >
                      Description
                    </label>
                    <textarea
                      id="integration_description"
                      name="integration_description"
                      rows={3}
                      className="w-full bg-dark-700 border border-gray-600 rounded-sm px-3 py-2 text-white focus:outline-hidden focus:ring-2 focus:ring-primary"
                      placeholder="Optional description for this integration"
                    />
                  </div>

                  {/* Dynamic fields from settings_schema */}
                  {Boolean(selectedIntegrationType.settings_schema?.properties) && (
                    <div className="space-y-4 border-t border-gray-700 pt-4">
                      <h3 className="text-sm font-medium text-gray-300">Configuration Settings</h3>
                      {Object.entries(
                        selectedIntegrationType.settings_schema.properties as Record<
                          string,
                          {
                            type?: string;
                            secret?: boolean;
                            required?: boolean;
                            display_name?: string;
                            description?: string;
                            default?: unknown;
                            pattern?: string;
                            placeholder?: string;
                          }
                        >
                      ).map(([key, property]) => {
                        const isRequired = property.required === true;
                        const fieldType = getFieldType(property);
                        const rawPattern = property.pattern ?? undefined;
                        // Sanitize for HTML pattern attr: strip anchors, escape trailing hyphen in char classes
                        const pattern = rawPattern
                          ? rawPattern
                              .replace(/^\^/, '')
                              .replace(/\$$/, '')
                              .replace(/([^\\])-\]/g, '$1\\-]')
                          : undefined;

                        // Special styling for integration_id field
                        const isIntegrationId = key === 'integration_id';

                        return (
                          <div key={key}>
                            <label
                              htmlFor={`field-${key}`}
                              className="block text-sm font-medium text-gray-300 mb-1"
                            >
                              {property.display_name || key}
                              {isRequired && <span className="text-red-400 ml-1">*</span>}
                            </label>
                            {property.description && (
                              <p className="text-xs text-gray-400 mb-2">{property.description}</p>
                            )}
                            {fieldType === 'checkbox' ? (
                              <input
                                id={`field-${key}`}
                                name={key}
                                type="checkbox"
                                defaultChecked={property.default === true}
                                className="h-4 w-4 rounded-sm border-gray-600 bg-dark-700 text-primary focus:ring-primary"
                              />
                            ) : (
                              <input
                                id={`field-${key}`}
                                name={key}
                                type={fieldType}
                                required={isRequired}
                                defaultValue={stringifyDefault(property.default)}
                                pattern={pattern}
                                title={
                                  pattern ? `Format: ${property.description ?? ''}` : undefined
                                }
                                className={`w-full bg-dark-700 border border-gray-600 rounded px-3 py-2 text-white focus:outline-hidden focus:ring-2 focus:ring-primary ${
                                  isIntegrationId ? 'font-mono' : ''
                                }`}
                                placeholder={
                                  property.placeholder ??
                                  stringifyDefault(property.default) ??
                                  `Enter ${property.display_name ?? key}`
                                }
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Connectors available */}
                  <div className="border-t border-gray-700 pt-4">
                    <span className="block text-sm font-medium text-gray-300 mb-2">
                      Available Connectors
                    </span>
                    <p className="text-xs text-gray-400 mb-3">
                      These actions will be available once the integration is created:
                    </p>
                    <div className="grid grid-cols-1 gap-2">
                      {selectedIntegrationType.actions?.map((action) => (
                        <div
                          key={action.action_id}
                          className="flex items-center p-2 bg-dark-700 rounded-sm"
                        >
                          <CheckCircleIcon className="w-4 h-4 text-green-400 mr-2 shrink-0" />
                          <div>
                            <span className="text-white text-sm">{action.name}</span>
                            {action.description && (
                              <p className="text-gray-400 text-xs mt-0.5">{action.description}</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="flex justify-end space-x-3 mt-6">
                    <button
                      type="button"
                      onClick={() => {
                        if (formHasChanges) {
                          setShowCloseConfirmation(true);
                        } else {
                          setShowCreateForm(false);
                          setSelectedIntegrationType(null);
                        }
                      }}
                      className="px-4 py-2 bg-gray-600 text-white rounded-sm hover:bg-gray-500 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="px-4 py-2 bg-primary text-white rounded-sm hover:bg-primary-dark transition-colors"
                    >
                      Create Integration
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )
        )}

        {/* Integration Type Preview Modal */}
        {previewIntegrationType && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-dark-800 rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-y-auto">
              {/* Header */}
              <div className="flex items-start justify-between mb-6">
                <div className="flex items-center space-x-4">
                  {renderIntegrationIcon(previewIntegrationType.integration_type, 'large')}
                  <div>
                    <h2 className="text-xl font-semibold text-white">
                      {previewIntegrationType.display_name}
                    </h2>
                    {previewIntegrationType.description && (
                      <p className="text-gray-400 mt-1 max-w-xl">
                        {previewIntegrationType.description}
                      </p>
                    )}
                    {/* Archetype badges */}
                    {previewIntegrationType.archetypes &&
                      previewIntegrationType.archetypes.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {previewIntegrationType.archetypes.map((archetype) => (
                            <span
                              key={archetype}
                              className={`px-2 py-0.5 rounded-sm text-xs font-medium ${getArchetypeBadgeColor(archetype)}`}
                            >
                              {archetype}
                            </span>
                          ))}
                        </div>
                      )}
                  </div>
                </div>
                <button
                  onClick={() => setPreviewIntegrationType(null)}
                  className="text-gray-400 hover:text-white"
                >
                  <span className="text-2xl">&times;</span>
                </button>
              </div>

              {/* Connectors and Tools Grid */}
              <div className="mb-6">
                <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center space-x-2">
                  <CubeIcon className="w-4 h-4" />
                  <span>Actions ({previewIntegrationType.actions?.length ?? 0})</span>
                </h3>
                <div className="space-y-2 max-h-[400px] overflow-y-auto">
                  {previewIntegrationType.actions?.map((action) => (
                    <div key={action.action_id} className="bg-dark-700 rounded-lg p-3">
                      <div className="flex items-center justify-between">
                        <div className="font-medium text-white text-sm">{action.name}</div>
                        <div className="flex gap-1">
                          {action.categories.map((cat) => (
                            <span
                              key={cat}
                              className="px-1.5 py-0.5 bg-dark-600 rounded-sm text-[10px] text-gray-400"
                            >
                              {cat}
                            </span>
                          ))}
                          {!action.enabled && (
                            <span className="px-1.5 py-0.5 bg-gray-600 rounded-sm text-[10px] text-gray-400">
                              Disabled
                            </span>
                          )}
                        </div>
                      </div>
                      <p className="text-gray-400 text-xs mt-1">{action.description}</p>
                    </div>
                  ))}
                  {(!previewIntegrationType.actions ||
                    previewIntegrationType.actions.length === 0) && (
                    <div className="bg-dark-700 rounded-lg p-3 text-gray-400 text-sm">
                      No actions available for this integration
                    </div>
                  )}
                </div>
              </div>

              {/* Existing Instances */}
              {(() => {
                const existingInstances = userIntegrations.filter(
                  (i) => i.integration_type === previewIntegrationType.integration_type
                );
                if (existingInstances.length === 0) return null;
                return (
                  <div className="mb-6 pt-4 border-t border-gray-700">
                    <h3 className="text-sm font-medium text-gray-400 mb-3">
                      Existing Instances ({existingInstances.length})
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {existingInstances.map((instance) => (
                        <button
                          key={instance.integration_id}
                          onClick={() => {
                            setPreviewIntegrationType(null);
                            void handleViewDetails(instance);
                          }}
                          className="flex items-center space-x-2 px-3 py-2 bg-dark-700 hover:bg-dark-600 rounded-lg transition-colors"
                        >
                          <div
                            className={`w-2 h-2 rounded-full ${getHealthDotColor(instance.health_status)}
                            }`}
                          />
                          <span className="text-white text-sm">{instance.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })()}

              {/* Footer with Configure button */}
              <div className="flex justify-end pt-4 border-t border-gray-700">
                <button
                  onClick={() => {
                    const typeToCreate = previewIntegrationType;
                    setPreviewIntegrationType(null);
                    void handleCreateIntegration(typeToCreate);
                  }}
                  className="px-6 py-2 bg-primary hover:bg-primary/80 text-white rounded-lg transition-colors text-sm font-medium"
                >
                  Configure Integration
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Integration Details Modal */}
        {showDetails && selectedIntegration && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-dark-800 rounded-lg p-6 w-full max-w-4xl h-[80vh] flex flex-col">
              {/* Header with status */}
              <div className="flex justify-between items-start mb-4">
                <div className="flex items-center space-x-4">
                  <div>
                    <h2 className="text-xl font-semibold text-white">{selectedIntegration.name}</h2>
                    <div className="flex items-center space-x-2 mt-1">
                      <span className="text-gray-400 text-sm">
                        {selectedIntegration.integration_type}
                      </span>
                      <span className="text-gray-600">•</span>
                      <div className="flex items-center space-x-1">
                        {renderHealthIcon(selectedIntegration.health_status)}
                        <span className="text-gray-400 text-sm">
                          {selectedIntegration.health_status || 'Unknown'}
                        </span>
                      </div>
                      {selectedIntegration.enabled ? (
                        <span className="px-2 py-0.5 bg-green-500/20 text-green-400 rounded-sm text-xs flex items-center space-x-1">
                          <PowerIcon className="w-3 h-3" />
                          <span>Enabled</span>
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 bg-gray-500/20 text-gray-400 rounded-sm text-xs flex items-center space-x-1">
                          <PowerIcon className="w-3 h-3" />
                          <span>Disabled</span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => {
                    // Stop all polling when closing
                    for (const controller of modalPollingControllers.current.values())
                      controller.stop();
                    modalPollingControllers.current.clear();
                    setShowDetails(false);
                    setSelectedIntegration(null);
                    setRunningActions(new Map());
                    setCurrentRunId(null);
                    setVisiblePasswords(new Set()); // Clear visible passwords
                  }}
                  className="text-gray-400 hover:text-white"
                >
                  <span className="text-2xl">&times;</span>
                </button>
              </div>

              {/* Tab Navigation */}
              <div className="flex space-x-1 border-b border-gray-700 mb-6">
                {(
                  [
                    { id: 'overview', label: 'Overview' },
                    { id: 'actions', label: 'Actions' },
                    { id: 'runs', label: 'Runs' },
                    { id: 'configuration', label: 'Configuration' },
                  ] as const
                ).map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setDetailsTab(tab.id)}
                    className={`px-4 py-2 text-sm font-medium transition-colors relative ${
                      detailsTab === tab.id ? 'text-primary' : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {tab.label}
                    {detailsTab === tab.id && (
                      <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />
                    )}
                  </button>
                ))}
              </div>

              {/* Tab Content - Scrollable Area */}
              <div className="flex-1 overflow-y-auto">
                {detailsTab === 'overview' && (
                  <>
                    {/* Overview Tab */}
                    <div className="space-y-6">
                      {/* Quick Stats */}
                      <div className="grid grid-cols-3 gap-4">
                        <div className="bg-dark-700 rounded-lg p-4">
                          <h3 className="text-xs font-medium text-gray-400 mb-1">Created</h3>
                          <p className="text-white text-lg">
                            {new Date(selectedIntegration.created_at).toLocaleDateString()}
                          </p>
                        </div>
                        <div className="bg-dark-700 rounded-lg p-4">
                          <h3 className="text-xs font-medium text-gray-400 mb-1">Actions</h3>
                          <p className="text-white text-lg">
                            {(() => {
                              const integType = availableIntegrations.find(
                                (t) => t.integration_type === selectedIntegration.integration_type
                              );
                              return integType?.actions?.length ?? integType?.action_count ?? 0;
                            })()}
                          </p>
                        </div>
                      </div>

                      {/* Description */}
                      {selectedIntegration.description && (
                        <div>
                          <h3 className="text-sm font-medium text-gray-400 mb-2">Description</h3>
                          <p className="text-gray-300">{selectedIntegration.description}</p>
                        </div>
                      )}
                    </div>
                  </>
                )}

                {/* Configuration Tab */}
                {detailsTab === 'configuration' && (
                  <div className="space-y-6">
                    {/* AI Role Section - only shown for AI archetype integrations */}
                    {isAIArchetype(selectedIntegration) && (
                      <div>
                        <h3 className="text-sm font-medium text-gray-400 mb-2">AI Role</h3>
                        <div className="bg-dark-700 p-4 rounded-sm flex items-center justify-between">
                          <div>
                            <p className="text-white text-sm font-medium">Primary AI Integration</p>
                            <p className="text-gray-400 text-xs mt-1">
                              When enabled, this integration is used as the default LLM for task
                              execution. Only one AI integration can be primary at a time.
                            </p>
                          </div>
                          <button
                            role="switch"
                            aria-checked={!!selectedIntegration.settings?.is_primary}
                            disabled={!!selectedIntegration.settings?.is_primary}
                            onClick={() => void handleSetAIPrimary(selectedIntegration)}
                            title={
                              selectedIntegration.settings?.is_primary
                                ? 'Already the primary AI integration'
                                : 'Set as primary AI integration'
                            }
                            className={`relative inline-flex h-6 w-11 shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                              selectedIntegration.settings?.is_primary
                                ? 'bg-primary cursor-not-allowed'
                                : 'bg-gray-600 cursor-pointer'
                            }`}
                          >
                            <span
                              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                                selectedIntegration.settings?.is_primary
                                  ? 'translate-x-5'
                                  : 'translate-x-0'
                              }`}
                            />
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Settings Section */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <h3 className="text-sm font-medium text-gray-400">Settings</h3>
                        {selectedIntegration.settings &&
                          Object.keys(selectedIntegration.settings).length > 0 && (
                            <button
                              onClick={() => {
                                if (settingsEditMode) {
                                  // Cancel editing
                                  setSettingsEditMode(false);
                                  setEditedSettings({});
                                } else {
                                  // Enter edit mode with current values
                                  setSettingsEditMode(true);
                                  setEditedSettings({});
                                }
                              }}
                              className="text-xs text-primary hover:text-primary-light transition-colors"
                            >
                              {settingsEditMode ? 'Cancel' : 'Edit'}
                            </button>
                          )}
                      </div>
                      <div className="bg-dark-700 p-4 rounded-sm">
                        {selectedIntegration.settings &&
                        Object.keys(selectedIntegration.settings).length > 0 ? (
                          <div className="space-y-3">
                            {/* eslint-disable-next-line sonarjs/cognitive-complexity -- JSX rendering branches */}
                            {Object.entries(selectedIntegration.settings).map(([key, value]) => {
                              if (key === 'is_primary') return null;
                              const isSensitive = isCredentialField(key);
                              const fieldKey = `${selectedIntegration.integration_id}-${key}`;
                              const isVisible = visiblePasswords.has(fieldKey);
                              const isEditable = !isSensitive && typeof value !== 'object';
                              const currentValue =
                                editedSettings[key] !== undefined ? editedSettings[key] : value;
                              const displayValue = getSettingsDisplayValue(
                                value,
                                isSensitive,
                                isVisible
                              );

                              return (
                                <div
                                  key={key}
                                  className="flex items-start justify-between py-2 border-b border-gray-600 last:border-0"
                                >
                                  <label className="text-gray-400 text-sm min-w-[140px] pt-1">
                                    {key}:
                                  </label>
                                  <div className="flex-1 ml-4">
                                    {settingsEditMode && isEditable ? (
                                      <input
                                        type={typeof value === 'number' ? 'number' : 'text'}
                                        value={String(currentValue)}
                                        onChange={(e) => {
                                          const newValue =
                                            typeof value === 'number'
                                              ? Number(e.target.value)
                                              : e.target.value;
                                          setEditedSettings({
                                            ...editedSettings,
                                            [key]: newValue,
                                          });
                                        }}
                                        className="w-full px-3 py-1.5 bg-dark-600 border border-gray-600 rounded-sm text-white text-sm focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
                                      />
                                    ) : (
                                      <div className="flex items-start space-x-2">
                                        {isSensitive ? (
                                          <div className="relative flex-1 min-w-0">
                                            <span
                                              className={`font-mono text-sm ${isVisible ? 'text-white' : 'text-gray-400'}`}
                                            >
                                              {displayValue}
                                            </span>
                                          </div>
                                        ) : (
                                          <span className="text-white font-mono text-sm flex-1 break-all">
                                            {displayValue}
                                          </span>
                                        )}
                                        {isSensitive && (
                                          <button
                                            type="button"
                                            onClick={() => {
                                              const newVisible = new Set(visiblePasswords);
                                              if (isVisible) {
                                                newVisible.delete(fieldKey);
                                              } else {
                                                newVisible.add(fieldKey);
                                              }
                                              setVisiblePasswords(newVisible);
                                            }}
                                            className="p-1 text-gray-400 hover:text-white transition-colors shrink-0"
                                            title={
                                              isVisible
                                                ? 'Hide sensitive value'
                                                : 'Show sensitive value'
                                            }
                                          >
                                            {isVisible ? (
                                              <EyeSlashIcon className="w-4 h-4" />
                                            ) : (
                                              <EyeIcon className="w-4 h-4" />
                                            )}
                                          </button>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                            {settingsEditMode && (
                              <div className="flex justify-end pt-3">
                                <button
                                  onClick={() => void handleSaveSettings()}
                                  disabled={
                                    isSavingSettings || Object.keys(editedSettings).length === 0
                                  }
                                  className={`px-4 py-2 rounded text-sm transition-colors ${
                                    isSavingSettings || Object.keys(editedSettings).length === 0
                                      ? 'bg-gray-600 text-gray-400 cursor-not-allowed'
                                      : 'bg-primary text-white hover:bg-primary-dark'
                                  }`}
                                >
                                  {isSavingSettings ? 'Saving...' : 'Save Changes'}
                                </button>
                              </div>
                            )}
                          </div>
                        ) : (
                          <span className="text-gray-400">No configuration settings</span>
                        )}
                      </div>
                    </div>

                    {/* Credentials Section */}
                    <div>
                      <h3 className="text-sm font-medium text-gray-400 mb-2">Credentials</h3>
                      <div className="bg-dark-700 p-4 rounded-sm">
                        {loadingCredentials && (
                          <div className="flex items-center space-x-2 text-gray-400">
                            <ArrowPathIcon className="w-4 h-4 animate-spin" />
                            <span>Loading credentials...</span>
                          </div>
                        )}
                        {!loadingCredentials && integrationCredentials.length > 0 && (
                          <div className="space-y-4">
                            {integrationCredentials.map((cred) => (
                              <div key={cred.id} className="space-y-2">
                                {/* Header row */}
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2">
                                    <span className="text-white text-sm font-medium">
                                      {cred.account}
                                    </span>
                                    <span className="text-xs text-gray-500">{cred.provider}</span>
                                    {cred.is_primary && (
                                      <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-primary/20 text-primary border border-primary/30">
                                        Primary
                                      </span>
                                    )}
                                    {cred.purpose && (
                                      <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-dark-600 text-gray-400 border border-gray-600">
                                        {cred.purpose}
                                      </span>
                                    )}
                                  </div>
                                  <span className="text-xs text-gray-500">v{cred.key_version}</span>
                                </div>

                                {/* Secret fields */}
                                {cred.secret &&
                                  Object.entries(cred.secret).map(([key, value]) => {
                                    const fieldKey = `cred-${cred.id}-${key}`;
                                    const isVisible = visiblePasswords.has(fieldKey);
                                    return (
                                      <div
                                        key={key}
                                        className="flex items-center justify-between py-1.5 border-b border-gray-600/50 last:border-0"
                                      >
                                        <span className="text-gray-400 text-sm min-w-[140px]">
                                          {key}:
                                        </span>
                                        <div className="flex items-center gap-2 flex-1 ml-4 justify-end">
                                          <span
                                            className={`font-mono text-sm ${isVisible ? 'text-white break-all' : 'text-gray-400'}`}
                                          >
                                            {isVisible ? value : '••••••••'}
                                          </span>
                                          <button
                                            type="button"
                                            onClick={() => {
                                              const newVisible = new Set(visiblePasswords);
                                              if (isVisible) {
                                                newVisible.delete(fieldKey);
                                              } else {
                                                newVisible.add(fieldKey);
                                              }
                                              setVisiblePasswords(newVisible);
                                            }}
                                            className="p-1 text-gray-400 hover:text-white transition-colors shrink-0"
                                            title={
                                              isVisible
                                                ? 'Hide credential value'
                                                : 'Show credential value'
                                            }
                                          >
                                            {isVisible ? (
                                              <EyeSlashIcon className="w-4 h-4" />
                                            ) : (
                                              <EyeIcon className="w-4 h-4" />
                                            )}
                                          </button>
                                        </div>
                                      </div>
                                    );
                                  })}

                                {/* Metadata */}
                                {cred.credential_metadata &&
                                  Object.keys(cred.credential_metadata).length > 0 && (
                                    <div className="flex flex-wrap gap-2 mt-1">
                                      {Object.entries(cred.credential_metadata).map(
                                        ([key, value]) => (
                                          <span key={key} className="text-xs text-gray-500">
                                            {key}: {String(value)}
                                          </span>
                                        )
                                      )}
                                    </div>
                                  )}
                              </div>
                            ))}
                          </div>
                        )}
                        {!loadingCredentials && integrationCredentials.length === 0 && (
                          <span className="text-gray-400 text-sm">No credentials configured</span>
                        )}
                      </div>
                    </div>

                    {/* Manage Schedules Section */}
                    <div>
                      <h3 className="text-sm font-medium text-gray-400 mb-2 flex items-center space-x-2">
                        <ClockIcon className="w-4 h-4" />
                        <span>Schedules</span>
                      </h3>
                      <div className="bg-dark-700 p-4 rounded-sm">
                        {loadingSchedules ? (
                          <div className="flex items-center space-x-2 text-gray-400">
                            <ArrowPathIcon className="w-4 h-4 animate-spin" />
                            <span>Loading schedules...</span>
                          </div>
                        ) : (
                          (() => {
                            const integType = availableIntegrations.find(
                              (t) => t.integration_type === selectedIntegration.integration_type
                            );
                            if (!integType)
                              return <span className="text-gray-400">Loading...</span>;

                            return (
                              <div className="space-y-3">
                                {integType.actions?.map((action) => {
                                  const activeSchedule = managedSchedules[action.action_id] || null;

                                  return (
                                    <div
                                      key={action.action_id}
                                      className="flex items-center justify-between p-3 bg-dark-600 rounded-sm"
                                    >
                                      <div>
                                        <div className="font-medium text-white text-sm">
                                          {action.name}
                                        </div>
                                        {activeSchedule ? (
                                          <div className="text-xs text-gray-400 mt-1">
                                            <span
                                              className={`inline-flex items-center px-1.5 py-0.5 rounded ${
                                                activeSchedule.enabled
                                                  ? 'bg-green-500/20 text-green-400'
                                                  : 'bg-gray-600 text-gray-400'
                                              }`}
                                            >
                                              {activeSchedule.enabled ? 'Enabled' : 'Disabled'}
                                            </span>
                                            <span className="ml-2">
                                              {activeSchedule.schedule_type === 'every'
                                                ? `Every ${activeSchedule.schedule_value}`
                                                : `Cron: ${activeSchedule.schedule_value}`}
                                            </span>
                                          </div>
                                        ) : (
                                          <div className="text-xs text-gray-500 mt-1">
                                            No schedule configured
                                          </div>
                                        )}
                                      </div>
                                      <button
                                        onClick={() => {
                                          setEditingSchedule({
                                            actionId: action.action_id,
                                            schedule: activeSchedule
                                              ? {
                                                  schedule_id: activeSchedule.schedule_id,
                                                  schedule_type: activeSchedule.schedule_type,
                                                  schedule_value: activeSchedule.schedule_value,
                                                  enabled: activeSchedule.enabled,
                                                }
                                              : {
                                                  schedule_type: 'every',
                                                  schedule_value: '5m',
                                                  enabled: true,
                                                },
                                          });
                                        }}
                                        className="px-3 py-1.5 text-xs bg-dark-700 hover:bg-dark-500 text-gray-300 rounded-sm transition-colors"
                                      >
                                        Configure
                                      </button>
                                    </div>
                                  );
                                })}
                              </div>
                            );
                          })()
                        )}
                      </div>
                    </div>

                    {/* Integration Status */}
                    <div>
                      <h3 className="text-sm font-medium text-gray-400 mb-2 flex items-center space-x-2">
                        <PowerIcon className="w-4 h-4" />
                        <span>Integration Status</span>
                      </h3>
                      <div className="bg-dark-700 p-4 rounded-sm">
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="text-white text-sm font-medium">
                              {selectedIntegration.enabled ? 'Enabled' : 'Disabled'}
                            </div>
                            <div className="text-xs text-gray-400 mt-1">
                              {selectedIntegration.enabled
                                ? 'This integration is active and running'
                                : 'This integration is paused'}
                            </div>
                          </div>
                          <button
                            onClick={() => void handleToggleIntegration(selectedIntegration)}
                            className={`px-4 py-2 rounded transition-colors text-sm ${
                              selectedIntegration.enabled
                                ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                                : 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                            }`}
                          >
                            {selectedIntegration.enabled ? 'Disable' : 'Enable'}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Actions Tab */}
                {detailsTab === 'actions' && (
                  <div className="space-y-4">
                    {(() => {
                      const integType = availableIntegrations.find(
                        (t) => t.integration_type === selectedIntegration.integration_type
                      );
                      const actions = integType?.actions ?? [];

                      return (
                        <>
                          <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center space-x-2">
                            <CubeIcon className="w-4 h-4" />
                            <span>Actions ({actions.length})</span>
                          </h3>
                          {actions.length > 0 ? (
                            <div className="bg-dark-700 rounded-sm overflow-hidden">
                              <div className="max-h-[500px] overflow-y-auto">
                                {actions.map((action, index) => (
                                  <div
                                    key={action.action_id}
                                    className={`p-3 ${index !== actions.length - 1 ? 'border-b border-gray-600' : ''}`}
                                  >
                                    <div className="flex items-center justify-between">
                                      <div className="flex items-center space-x-2">
                                        <span className="font-medium text-white text-sm">
                                          {action.name}
                                        </span>
                                        {!action.enabled && (
                                          <span className="px-1.5 py-0.5 bg-gray-600 rounded-sm text-[10px] text-gray-400">
                                            Disabled
                                          </span>
                                        )}
                                      </div>
                                      <div className="flex gap-1 flex-wrap">
                                        {action.categories.map((category) => (
                                          <span
                                            key={category}
                                            className="px-1.5 py-0.5 bg-dark-600 rounded-sm text-[10px] text-gray-400"
                                          >
                                            {category}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                    <p className="text-gray-500 text-xs mt-0.5 font-mono">
                                      {action.cy_name}
                                    </p>
                                    <p className="text-gray-400 text-xs mt-1">
                                      {action.description}
                                    </p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : (
                            <div className="bg-dark-700 rounded-lg p-4 text-gray-400 text-sm">
                              No actions available for this integration.
                            </div>
                          )}
                        </>
                      );
                    })()}
                  </div>
                )}

                {/* Runs Tab */}
                {detailsTab === 'runs' && (
                  <div className="space-y-6">
                    {/* Run Action Section — only show managed (runnable) actions */}
                    <div>
                      <h3 className="text-sm font-medium text-gray-400 mb-3">Run Action</h3>
                      <div className="flex flex-wrap gap-2">
                        {(() => {
                          const integType = availableIntegrations.find(
                            (t) => t.integration_type === selectedIntegration.integration_type
                          );
                          if (!integType) return null;

                          // Only show actions that are managed resources (have tasks/schedules)
                          const runnableActions = integType.actions?.filter((a) =>
                            managedResourceKeys.includes(a.action_id)
                          );

                          if (!runnableActions || runnableActions.length === 0) {
                            return null;
                          }

                          return runnableActions.map((action) => {
                            const runKey = `${selectedIntegration.integration_id}-${action.action_id}`;
                            const isRunning = runningActions.has(runKey);

                            return isRunning ? (
                              <button
                                key={action.action_id}
                                onClick={() =>
                                  handleCancelManagedRun(
                                    selectedIntegration.integration_id,
                                    action.action_id,
                                    false
                                  )
                                }
                                className="flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors bg-red-500/20 text-red-400 hover:bg-red-500/30"
                              >
                                <XCircleIcon className="w-4 h-4" />
                                <span>Cancel</span>
                              </button>
                            ) : (
                              <button
                                key={action.action_id}
                                onClick={() =>
                                  void handleRunManagedResource(
                                    selectedIntegration,
                                    action.action_id,
                                    false
                                  )
                                }
                                className="flex items-center space-x-2 px-4 py-2 rounded-lg transition-colors bg-primary/20 text-primary hover:bg-primary/30"
                              >
                                <ArrowPathIcon className="w-4 h-4" />
                                <span>{`Run ${action.name}`}</span>
                              </button>
                            );
                          });
                        })()}
                      </div>
                    </div>

                    {/* Recent Runs */}
                    <div>
                      <h3 className="text-sm font-medium text-gray-400 mb-2">Recent Runs</h3>
                      {loadingRuns && (
                        <div className="bg-dark-700 p-4 rounded-sm text-gray-400">
                          Loading runs...
                        </div>
                      )}
                      {!loadingRuns && integrationRuns.length > 0 && (
                        <div className="bg-dark-700 rounded-sm overflow-hidden">
                          <table className="w-full">
                            <thead>
                              <tr className="border-b border-gray-600">
                                <th className="text-left py-2 px-4 text-gray-400 text-sm">
                                  Action
                                </th>
                                <th className="text-left py-2 px-4 text-gray-400 text-sm">
                                  Status
                                </th>
                                <th className="text-left py-2 px-4 text-gray-400 text-sm">Type</th>
                                <th className="text-left py-2 px-4 text-gray-400 text-sm">
                                  Started
                                </th>
                                <th className="text-left py-2 px-4 text-gray-400 text-sm">
                                  Duration
                                </th>
                                <th className="text-left py-2 px-4 text-gray-400 text-sm">
                                  Details
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {integrationRuns.map((run) => {
                                // Calculate duration in milliseconds first, then convert to seconds with decimal
                                const durationMs = (() => {
                                  if (run.completed_at && run.started_at) {
                                    return (
                                      new Date(run.completed_at).getTime() -
                                      new Date(run.started_at).getTime()
                                    );
                                  }
                                  if (run.status === 'running' && run.started_at) {
                                    return Date.now() - new Date(run.started_at).getTime();
                                  }
                                  if (run.status === 'pending') return 0;
                                  return null;
                                })();

                                const duration = durationMs === null ? null : durationMs / 1000;

                                const formatDuration = (
                                  seconds: number | null,
                                  runStatus: string
                                ) => {
                                  if (seconds === null) return '-';

                                  // For pending/starting runs with 0 duration
                                  if (seconds === 0 && runStatus === 'pending')
                                    return 'Starting...';

                                  // For short durations (less than 60 seconds), show with decimal precision
                                  if (seconds < 60) {
                                    // Show 3 decimal places for very short durations, 1 for longer ones
                                    const precision = seconds < 10 ? 3 : 1;
                                    return `${seconds.toFixed(precision)}s`;
                                  }

                                  // For longer durations, use minutes/hours format
                                  const minutes = Math.floor(seconds / 60);
                                  const remainingSeconds = Math.floor(seconds % 60);

                                  if (minutes >= 60) {
                                    const hours = Math.floor(minutes / 60);
                                    const remainingMinutes = minutes % 60;
                                    return `${hours}h ${remainingMinutes}m`;
                                  }

                                  return remainingSeconds > 0
                                    ? `${minutes}m ${remainingSeconds}s`
                                    : `${minutes}m`;
                                };

                                return (
                                  <React.Fragment key={run.task_run_id}>
                                    <tr
                                      onClick={() =>
                                        setExpandedRunId(
                                          expandedRunId === run.task_run_id ? null : run.task_run_id
                                        )
                                      }
                                      className={`border-b border-gray-600 last:border-0 transition-colors cursor-pointer ${
                                        run.task_run_id === currentRunId
                                          ? 'bg-primary/10'
                                          : 'hover:bg-dark-600'
                                      }`}
                                    >
                                      <td className="py-2 px-4 text-white text-sm">health_check</td>
                                      <td className="py-2 px-4">
                                        <div className="flex items-center space-x-2">
                                          {run.status === 'running' && (
                                            <ArrowPathIcon className="w-4 h-4 animate-spin text-blue-400" />
                                          )}
                                          {renderRunStatus(run.status)}
                                        </div>
                                      </td>
                                      <td className="py-2 px-4 text-white text-sm">
                                        {run.run_context ? 'scheduled' : 'manual'}
                                      </td>
                                      <td className="py-2 px-4 text-gray-400 text-sm">
                                        {new Date(run.created_at).toLocaleTimeString([], {
                                          hour: '2-digit',
                                          minute: '2-digit',
                                        })}
                                      </td>
                                      <td className="py-2 px-4 text-gray-400 text-sm">
                                        {run.status === 'running' ? (
                                          <div className="flex items-center space-x-1">
                                            <ClockIcon className="w-4 h-4 text-blue-400" />
                                            <span>{formatDuration(duration, run.status)}</span>
                                          </div>
                                        ) : (
                                          formatDuration(duration, run.status)
                                        )}
                                      </td>
                                      <td className="py-2 px-4 text-gray-400 text-sm">
                                        {run.run_context ? (
                                          <button
                                            className="text-primary hover:text-primary-dark text-xs underline"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              setExpandedRunId(
                                                expandedRunId === run.task_run_id
                                                  ? null
                                                  : run.task_run_id
                                              );
                                            }}
                                          >
                                            {expandedRunId === run.task_run_id ? 'Hide' : 'Show'}
                                          </button>
                                        ) : (
                                          <span className="text-gray-400 text-xs">-</span>
                                        )}
                                      </td>
                                    </tr>
                                    {expandedRunId === run.task_run_id && run.run_context && (
                                      <tr className="bg-dark-600/50">
                                        <td colSpan={6} className="p-4">
                                          <div className="space-y-2">
                                            <div className="text-xs text-gray-400 mb-1">
                                              Run ID: {run.task_run_id}
                                            </div>
                                            <div className="bg-dark-800 rounded-sm p-3">
                                              <pre className="text-xs text-gray-300 whitespace-pre-wrap wrap-break-word overflow-auto max-h-40">
                                                {JSON.stringify(
                                                  redactSensitiveData(run.run_context, false),
                                                  null,
                                                  2
                                                )}
                                              </pre>
                                            </div>
                                            {/password|secret|api[_-]?key|token|credential/i.exec(
                                              JSON.stringify(run.run_context)
                                            ) && (
                                              <div className="mt-2 flex items-center space-x-2 text-xs text-yellow-500">
                                                <ExclamationCircleIcon className="w-4 h-4" />
                                                <span>
                                                  Some sensitive information has been redacted for
                                                  security
                                                </span>
                                              </div>
                                            )}
                                          </div>
                                        </td>
                                      </tr>
                                    )}
                                  </React.Fragment>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}
                      {!loadingRuns && integrationRuns.length === 0 && (
                        <div className="bg-dark-700 p-4 rounded-sm text-gray-400">No runs yet</div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Close Setup Confirmation Modal */}
        {showCloseConfirmation && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-60">
            <div className="bg-dark-800 rounded-lg p-6 w-full max-w-md">
              <div className="flex items-center space-x-3 mb-4">
                <div className="p-2 bg-yellow-500/10 rounded-full">
                  <ExclamationTriangleIcon className="w-6 h-6 text-yellow-400" />
                </div>
                <h2 className="text-xl font-semibold text-white">Unsaved Changes</h2>
              </div>

              <p className="text-gray-300 mb-6">
                You have unsaved changes in the integration setup form. Are you sure you want to
                close without saving?
              </p>

              <div className="bg-dark-700 rounded-sm p-3 mb-6">
                <p className="text-sm text-gray-400">
                  Your configuration will be lost if you close now.
                </p>
              </div>

              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setShowCloseConfirmation(false)}
                  className="px-4 py-2 bg-gray-600 text-white rounded-sm hover:bg-gray-500 transition-colors"
                >
                  Continue Editing
                </button>
                <button
                  onClick={() => {
                    setShowCloseConfirmation(false);
                    setShowCreateForm(false);
                    setSelectedIntegrationType(null);
                    setFormHasChanges(false);
                  }}
                  className="px-4 py-2 bg-red-500 text-white rounded-sm hover:bg-red-600 transition-colors"
                >
                  Discard Changes
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Delete Confirmation Modal */}
        {deleteConfirmation.show && deleteConfirmation.integration && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-dark-800 rounded-lg p-6 w-full max-w-md">
              <div className="flex items-center space-x-3 mb-4">
                <div className="p-2 bg-red-500/10 rounded-full">
                  <ExclamationTriangleIcon className="w-6 h-6 text-red-400" />
                </div>
                <h2 className="text-xl font-semibold text-white">Delete Integration</h2>
              </div>

              <p className="text-gray-300 mb-4">
                Are you sure you want to delete{' '}
                <span className="font-semibold text-white">
                  {deleteConfirmation.integration.name}
                </span>
                ?
              </p>

              <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-sm p-3 mb-6">
                <p className="text-sm text-yellow-400">
                  <strong>Note:</strong> If you only want to temporarily stop this integration, you
                  can disable it instead of deleting it.
                </p>
                <div className="mt-2 flex items-center space-x-2">
                  <PowerIcon className="w-4 h-4 text-gray-400" />
                  <span className="text-xs text-gray-400">
                    Current status:{' '}
                    {deleteConfirmation.integration.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
              </div>

              <div className="bg-dark-700 rounded-sm p-3 mb-6">
                <p className="text-sm text-gray-400 mb-2">This action will:</p>
                <ul className="text-sm text-gray-300 space-y-1">
                  <li className="flex items-start">
                    <span className="text-red-400 mr-2">•</span>
                    <span>Permanently delete this integration configuration</span>
                  </li>
                  <li className="flex items-start">
                    <span className="text-red-400 mr-2">•</span>
                    <span>Remove all associated schedules</span>
                  </li>
                  <li className="flex items-start">
                    <span className="text-red-400 mr-2">•</span>
                    <span>Stop any running actions</span>
                  </li>
                  <li className="flex items-start">
                    <span className="text-red-400 mr-2">•</span>
                    <span>Keep historical run data for audit purposes</span>
                  </li>
                </ul>
              </div>

              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setDeleteConfirmation({ show: false, integration: null })}
                  className="px-4 py-2 bg-gray-600 text-white rounded-sm hover:bg-gray-500 transition-colors"
                >
                  Cancel
                </button>
                {deleteConfirmation.integration.enabled && (
                  <button
                    onClick={() => {
                      if (deleteConfirmation.integration) {
                        void handleToggleIntegration(deleteConfirmation.integration);
                      }
                      setDeleteConfirmation({ show: false, integration: null });
                    }}
                    className="px-4 py-2 bg-yellow-500/20 text-yellow-400 rounded-sm hover:bg-yellow-500/30 transition-colors"
                  >
                    Disable Instead
                  </button>
                )}
                <button
                  onClick={() => void handleDeleteIntegration()}
                  className="px-4 py-2 bg-red-500 text-white rounded-sm hover:bg-red-600 transition-colors"
                >
                  Delete Integration
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Schedule Configuration Modal */}
        {editingSchedule && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-dark-800 rounded-lg p-6 w-full max-w-md">
              <div className="flex items-center space-x-3 mb-4">
                <div className="p-2 bg-primary/10 rounded-full">
                  <ClockIcon className="w-6 h-6 text-primary" />
                </div>
                <h2 className="text-xl font-semibold text-white">Configure Schedule</h2>
              </div>

              <p className="text-gray-400 text-sm mb-4">
                Configure the schedule for{' '}
                <span className="font-semibold text-white">
                  {editingSchedule.actionId.replaceAll('_', ' ')}
                </span>
              </p>

              <div className="space-y-4">
                {/* Enabled Toggle */}
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-300">Schedule Enabled</span>
                  <button
                    onClick={() => {
                      if (editingSchedule.schedule) {
                        setEditingSchedule({
                          ...editingSchedule,
                          schedule: {
                            ...editingSchedule.schedule,
                            enabled: !editingSchedule.schedule.enabled,
                          },
                        });
                      }
                    }}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out ${
                      editingSchedule.schedule?.enabled ? 'bg-primary' : 'bg-gray-600'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        editingSchedule.schedule?.enabled ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>

                {/* Schedule Type */}
                <div>
                  <label htmlFor="schedule-type" className="block text-sm text-gray-300 mb-2">
                    Schedule Type
                  </label>
                  <select
                    id="schedule-type"
                    value={editingSchedule.schedule?.schedule_type || 'every'}
                    onChange={(e) => {
                      if (editingSchedule.schedule) {
                        setEditingSchedule({
                          ...editingSchedule,
                          schedule: {
                            ...editingSchedule.schedule,
                            schedule_type: e.target.value as 'every' | 'cron',
                            schedule_value: e.target.value === 'every' ? '5m' : '0 * * * *',
                          },
                        });
                      }
                    }}
                    className="w-full bg-dark-700 border border-dark-600 rounded-sm px-3 py-2 text-white text-sm focus:outline-hidden focus:ring-2 focus:ring-primary"
                  >
                    <option value="every">Interval (Every X)</option>
                    <option value="cron">Cron Expression</option>
                  </select>
                </div>

                {/* Schedule Value */}
                <div>
                  <label htmlFor="schedule-value" className="block text-sm text-gray-300 mb-2">
                    {editingSchedule.schedule?.schedule_type === 'cron'
                      ? 'Cron Expression'
                      : 'Interval'}
                  </label>
                  {editingSchedule.schedule?.schedule_type === 'cron' ? (
                    <input
                      id="schedule-value"
                      type="text"
                      value={editingSchedule.schedule?.schedule_value || '0 * * * *'}
                      onChange={(e) => {
                        if (editingSchedule.schedule) {
                          setEditingSchedule({
                            ...editingSchedule,
                            schedule: {
                              ...editingSchedule.schedule,
                              schedule_value: e.target.value,
                            },
                          });
                        }
                      }}
                      placeholder="0 * * * *"
                      className="w-full bg-dark-700 border border-dark-600 rounded-sm px-3 py-2 text-white text-sm focus:outline-hidden focus:ring-2 focus:ring-primary"
                    />
                  ) : (
                    <select
                      id="schedule-value"
                      value={editingSchedule.schedule?.schedule_value || '5m'}
                      onChange={(e) => {
                        if (editingSchedule.schedule) {
                          setEditingSchedule({
                            ...editingSchedule,
                            schedule: {
                              ...editingSchedule.schedule,
                              schedule_value: e.target.value,
                            },
                          });
                        }
                      }}
                      className="w-full bg-dark-700 border border-dark-600 rounded-sm px-3 py-2 text-white text-sm focus:outline-hidden focus:ring-2 focus:ring-primary"
                    >
                      <option value="1m">Every 1 minute</option>
                      <option value="5m">Every 5 minutes</option>
                      <option value="15m">Every 15 minutes</option>
                      <option value="30m">Every 30 minutes</option>
                      <option value="1h">Every 1 hour</option>
                      <option value="6h">Every 6 hours</option>
                      <option value="12h">Every 12 hours</option>
                      <option value="24h">Every 24 hours</option>
                    </select>
                  )}
                  {editingSchedule.schedule?.schedule_type === 'cron' && (
                    <p className="text-xs text-gray-500 mt-1">
                      Format: minute hour day month weekday (e.g., &quot;0 * * * *&quot; for every
                      hour)
                    </p>
                  )}
                </div>
              </div>

              <div className="flex justify-between mt-6">
                <div>
                  {editingSchedule.schedule?.schedule_id && (
                    <button
                      onClick={() => {
                        setEditingSchedule({
                          ...editingSchedule,
                          schedule: null,
                        });
                        void handleSaveSchedule();
                      }}
                      disabled={savingSchedule}
                      className="px-4 py-2 bg-red-500/20 text-red-400 rounded-sm hover:bg-red-500/30 transition-colors disabled:opacity-50"
                    >
                      Delete Schedule
                    </button>
                  )}
                </div>
                <div className="flex space-x-3">
                  <button
                    onClick={() => setEditingSchedule(null)}
                    disabled={savingSchedule}
                    className="px-4 py-2 bg-gray-600 text-white rounded-sm hover:bg-gray-500 transition-colors disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => void handleSaveSchedule()}
                    disabled={savingSchedule}
                    className="px-4 py-2 bg-primary text-white rounded-sm hover:bg-primary-dark transition-colors disabled:opacity-50"
                  >
                    {savingSchedule ? 'Saving...' : 'Save Schedule'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
};

export default IntegrationsPage;
