import React, { useState, useEffect, useCallback } from 'react';

import {
  XMarkIcon,
  EyeIcon,
  EyeSlashIcon,
  CheckIcon,
  ExclamationCircleIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

import { extractApiErrorMessage } from '../../services/apiClient';
import { backendApi } from '../../services/backendApi';
import { logger } from '../../utils/errorHandler';

/**
 * Sanitize a JS regex pattern for use in an HTML `pattern` attribute.
 * HTML pattern is implicitly anchored (^…$), and some browsers reject
 * an unescaped trailing hyphen inside a character class (e.g. [a-z0-9-]).
 */
const sanitizeHtmlPattern = (pattern: string): string => {
  // Strip explicit ^ and $ anchors — HTML pattern adds them implicitly
  let sanitized = pattern.replace(/^\^/, '').replace(/\$$/, '');
  // Escape trailing hyphen before ] in character classes: [a-z0-9-] → [a-z0-9\-]
  sanitized = sanitized.replace(/([^\\])-\]/g, '$1\\-]');
  return sanitized;
};

interface SchemaProperty {
  type: string;
  display_name?: string;
  description?: string;
  required?: boolean;
  format?: string;
  default?: unknown;
  pattern?: string;
  min?: number;
  max?: number;
  placeholder?: string;
}

interface Schema {
  type: string;
  properties?: Record<string, SchemaProperty>;
}

interface IntegrationActionInfo {
  action_id: string;
  name: string;
  description: string;
  categories: string[];
  cy_name: string;
  enabled: boolean;
  params_schema?: Record<string, unknown>;
  result_schema?: Record<string, unknown>;
}

interface IntegrationType {
  integration_type: string;
  display_name: string;
  actions?: IntegrationActionInfo[];
  /** @deprecated Use `actions` instead */
  connectors?: string[];
  settings_schema?: Schema;
  credential_schema?: Schema;
  archetypes?: string[];
  integration_id_config?: {
    default: string;
    pattern: string;
    placeholder: string;
    display_name: string;
    description: string;
  };
}

interface ActionDetail {
  action_id: string;
  display_name: string;
  description: string;
  credential_scopes?: string[];
  default_schedule?: {
    schedule_type: string;
    schedule_value: string;
    enabled: boolean;
  };
  params_schema?: {
    type?: string;
    properties?: Record<string, SchemaProperty>;
    required?: string[];
  };
}

interface IntegrationSetupWizardProps {
  integrationType: IntegrationType;
  onClose: () => void;
  onSuccess: () => void;
  existingIntegrations?: Array<{ settings: Record<string, unknown> | null }>;
}

type WizardStep = 'integration' | 'credentials' | 'schedules' | 'summary';

interface CredentialConfig {
  name: string;
  secret: Record<string, string>;
}

interface ScheduleConfig {
  action_id: string;
  enabled: boolean;
  schedule_type: 'every' | 'cron';
  schedule_value: string;
  params?: Record<string, unknown>;
}

export const IntegrationSetupWizard: React.FC<IntegrationSetupWizardProps> = ({
  integrationType,
  onClose,
  onSuccess,
  existingIntegrations,
}) => {
  const [currentStep, setCurrentStep] = useState<WizardStep>('integration');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [existingIntegrationIds, setExistingIntegrationIds] = useState<string[]>([]);

  // Setup progress tracking
  const [setupProgress, setSetupProgress] = useState<
    {
      step: string;
      status: 'pending' | 'working' | 'done' | 'error';
      message?: string;
    }[]
  >([]);

  // Confirmation modal state
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [pendingCloseAction, setPendingCloseAction] = useState<(() => void) | null>(null);

  // Integration settings
  const [integrationSettings, setIntegrationSettings] = useState<Record<string, unknown>>({});
  const [integrationName, setIntegrationName] = useState('');
  const [integrationDescription, setIntegrationDescription] = useState('');

  // Action-specific settings overrides
  const [actionOverrides, setActionOverrides] = useState<Record<string, Record<string, unknown>>>(
    {}
  );

  // Credentials
  const [credentials, setCredentials] = useState<CredentialConfig[]>([]);
  const [revealedSecrets, setRevealedSecrets] = useState<Set<number>>(new Set());

  // Schedules
  const [schedules, setSchedules] = useState<ScheduleConfig[]>([]);
  const [actionDetails, setActionDetails] = useState<ActionDetail[]>([]);

  // Helper function to update schedule parameters
  const updateScheduleParam = (actionId: string, paramKey: string, value: unknown) => {
    setSchedules(
      schedules.map((s) =>
        s.action_id === actionId ? { ...s, params: { ...s.params, [paramKey]: value } } : s
      )
    );
  };

  // Helper function to get default value for a required param
  const getDefaultParamValue = (key: string, property: SchemaProperty): unknown => {
    if (property.default !== undefined) {
      return property.default;
    }
    if (!property.required) {
      return undefined;
    }

    // Set sensible defaults for required fields without defaults
    switch (property.type) {
      case 'integer': {
        // For lookback_seconds, use 5 minutes (300 seconds) as default
        if (key === 'lookback_seconds') {
          return 300;
        }
        if (property.min === undefined) {
          return 0;
        }
        return property.min;
      }
      case 'boolean': {
        return false;
      }
      case 'string': {
        return '';
      }
      default: {
        return undefined;
      }
    }
  };

  // Load existing integration IDs to check for duplicates
  useEffect(() => {
    const loadExistingIntegrations = async () => {
      try {
        const integrations = (await backendApi.getIntegrations()) as Array<{
          integration_id: string;
        }>;
        const ids = integrations.map((i) => i.integration_id);
        setExistingIntegrationIds(ids);
      } catch (error_) {
        console.warn('Failed to load existing integrations for validation', error_);
      }
    };
    void loadExistingIntegrations();
  }, []);

  // Load action details with default schedules
  useEffect(() => {
    const loadActionDetails = () => {
      try {
        const actions = integrationType.actions ?? [];

        const enrichedActions: ActionDetail[] = actions.map((action) => ({
          action_id: action.action_id,
          display_name: action.name,
          description: action.description,
          params_schema: action.params_schema as ActionDetail['params_schema'],
        }));

        setActionDetails(enrichedActions);

        // Initialize schedules with defaults
        const defaultSchedules: ScheduleConfig[] = enrichedActions
          .filter((a) => a.default_schedule)
          .map((a) => {
            const defaultParams: Record<string, unknown> = {};

            if (a.params_schema?.properties) {
              for (const [key, prop] of Object.entries(a.params_schema.properties)) {
                const defaultValue = getDefaultParamValue(key, prop);
                if (defaultValue !== undefined) {
                  defaultParams[key] = defaultValue;
                }
              }
            }

            return {
              action_id: a.action_id,
              enabled: a.default_schedule!.enabled,
              schedule_type: a.default_schedule!.schedule_type as 'every' | 'cron',
              schedule_value: a.default_schedule!.schedule_value,
              params: defaultParams,
            };
          });

        setSchedules(defaultSchedules);
      } catch (error_) {
        console.error('Failed to load action details', error_);
      }
    };

    if (integrationType) {
      loadActionDetails();
    }
  }, [integrationType]);

  // Determine required credential scopes
  const getRequiredCredentialScopes = () => {
    const scopes = new Set<string>();
    for (const action of actionDetails) {
      if (action.credential_scopes) {
        for (const scope of action.credential_scopes) scopes.add(scope);
      }
    }
    return [...scopes];
  };

  // Check if any data has been entered
  const hasUnsavedChanges = useCallback(() => {
    return (
      integrationName.length > 0 ||
      integrationDescription.length > 0 ||
      Object.keys(integrationSettings).length > 0 ||
      Object.keys(actionOverrides).length > 0 ||
      credentials.length > 0 ||
      schedules.some((s) => s.enabled) ||
      schedules.some((s) => s.params && Object.keys(s.params).length > 0)
    );
  }, [
    integrationName,
    integrationDescription,
    integrationSettings,
    actionOverrides,
    credentials,
    schedules,
  ]);

  // Safe close handler
  const handleSafeClose = useCallback(() => {
    if (hasUnsavedChanges()) {
      setShowConfirmDialog(true);
      setPendingCloseAction(() => () => onClose());
    } else {
      onClose();
    }
  }, [hasUnsavedChanges, onClose]);

  // Handle Escape key to close
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || event.key === 'Esc') {
        // Don't handle escape if confirmation dialog is showing
        if (showConfirmDialog) return;

        event.preventDefault();
        event.stopImmediatePropagation();
        handleSafeClose();
      }
    };

    // Use capture phase to catch the event before anything else
    document.addEventListener('keydown', handleEscape, true);
    return () => document.removeEventListener('keydown', handleEscape, true);
  }, [
    integrationName,
    integrationDescription,
    integrationSettings,
    actionOverrides,
    credentials,
    schedules,
    onClose,
    showConfirmDialog,
    handleSafeClose,
  ]);

  // Handle confirmation dialog actions
  const handleConfirmClose = () => {
    if (pendingCloseAction) {
      pendingCloseAction();
    }
    setShowConfirmDialog(false);
    setPendingCloseAction(null);
  };

  const handleCancelClose = () => {
    setShowConfirmDialog(false);
    setPendingCloseAction(null);
  };

  // Helper to check if any credential fields are required
  const hasRequiredCredentialFields = (): boolean => {
    if (!integrationType.credential_schema?.properties) {
      return false;
    }
    return Object.values(integrationType.credential_schema.properties).some(
      (prop: SchemaProperty) => prop.required === true
    );
  };

  const validateCredentials = (): Record<string, string> => {
    const errors: Record<string, string> = {};

    if (!integrationType.credential_schema?.properties) {
      return errors;
    }

    // Check each credential
    for (const [index, cred] of credentials.entries()) {
      if (!integrationType.credential_schema?.properties) continue;
      for (const [fieldKey, fieldSchema] of Object.entries(
        integrationType.credential_schema.properties
      )) {
        const value = cred.secret[fieldKey];
        const schema = fieldSchema;

        // Check required fields
        if (schema.required && !value) {
          errors[`credential_${index}_${fieldKey}`] =
            `${schema.display_name || fieldKey} is required`;
        }
      }
    }

    // Only require at least one credential if there are required credential fields
    if (hasRequiredCredentialFields() && credentials.length === 0) {
      errors.credentials = 'At least one credential is required for this integration';
    }

    return errors;
  };

  // Helper to validate integration ID
  const validateIntegrationId = (integrationId: string): string | undefined => {
    // Use pattern from integration_id_config if available, otherwise use default
    const patternStr = integrationType.integration_id_config?.pattern || '^[\\da-z][\\da-z-]*$';
    const idPattern = new RegExp(patternStr);
    if (!idPattern.test(integrationId)) {
      return 'Must start with lowercase letter or number, and contain only lowercase letters, numbers, and hyphens';
    }
    if (existingIntegrationIds.includes(integrationId)) {
      return `Integration ID "${integrationId}" already exists`;
    }
    return undefined;
  };

  // Helper to validate a single setting property
  const validateSettingProperty = (
    key: string,
    value: unknown,
    prop: SchemaProperty
  ): string | undefined => {
    // Check required fields
    if (prop.required && !value) {
      return `${prop.display_name || key} is required`;
    }

    // Validate integer ranges
    if (prop.type === 'integer' && value !== undefined) {
      const numValue = typeof value === 'number' ? value : Number.parseInt(value as string, 10);
      if (prop.min !== undefined && numValue < prop.min) {
        return `Must be at least ${prop.min}`;
      }
      if (prop.max !== undefined && numValue > prop.max) {
        return `Must be at most ${prop.max}`;
      }
    }

    // Validate string patterns
    if (prop.pattern && value && !new RegExp(prop.pattern).test(value as string)) {
      return prop.description || `Invalid format`;
    }

    return undefined;
  };

  const validateIntegrationSettings = (
    settings: Record<string, unknown>
  ): Record<string, string> => {
    const errors: Record<string, string> = {};

    // Validate integration_id
    const integrationId = settings.integration_id;
    if (integrationId && typeof integrationId === 'string') {
      const idError = validateIntegrationId(integrationId);
      if (idError) {
        errors.integration_id = idError;
      }
    }

    // Validate against settings_schema
    if (integrationType.settings_schema?.properties) {
      for (const [key, property] of Object.entries(integrationType.settings_schema.properties)) {
        const value = settings[key];
        const error = validateSettingProperty(key, value, property);
        if (error) {
          errors[key] = error;
        }
      }
    }

    return errors;
  };

  // Helper to validate a single schedule param
  const validateScheduleParam = (
    key: string,
    value: unknown,
    prop: SchemaProperty,
    actionDisplayName: string
  ): string | undefined => {
    // Check required fields
    if (prop.required && !value) {
      return `${prop.display_name || key} is required for ${actionDisplayName} schedule`;
    }

    // Validate format if specified
    if (prop.format === 'date-time' && value && typeof value === 'string') {
      // Basic ISO date validation
      const isoDateRegex = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z?$/;
      if (!isoDateRegex.test(value) && value !== 'now' && !value.startsWith('-')) {
        return `Invalid date format for ${key}`;
      }
    }

    return undefined;
  };

  const validateScheduleParams = (): Record<string, string> => {
    const errors: Record<string, string> = {};

    for (const [idx, schedule] of schedules.entries()) {
      if (!schedule.enabled) continue;

      const action = actionDetails.find((a) => a.action_id === schedule.action_id);
      if (!action?.params_schema?.properties) continue;

      // Validate schedule params against action's params_schema
      for (const [key, property] of Object.entries(action.params_schema.properties)) {
        const value = schedule.params?.[key];
        const error = validateScheduleParam(key, value, property, action.display_name);
        if (error) {
          errors[`schedule_${idx}_${key}`] = error;
        }
      }
    }

    return errors;
  };

  const handleIntegrationSubmit = (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);

    const settings: Record<string, unknown> = {};
    if (integrationType.settings_schema?.properties) {
      for (const key of Object.keys(integrationType.settings_schema.properties)) {
        const value = formData.get(key);
        const property = integrationType.settings_schema.properties[key];

        if (property.type === 'integer' && value) {
          settings[key] = Number.parseInt(value as string, 10);
        } else if (property.type === 'boolean') {
          settings[key] = formData.get(key) === 'true';
        } else if (value) {
          settings[key] = value;
        }
      }
    }

    // Validate settings before proceeding
    const errors = validateIntegrationSettings(settings);
    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors);
      setError('Please correct the errors before proceeding');
      return;
    }

    setValidationErrors({});
    setError(null);
    // Include integration_id in settings — it's a separate form field not in settings_schema
    const integrationIdValue = formData.get('integration_id') as string | null;
    if (integrationIdValue) {
      settings.integration_id = integrationIdValue;
    }
    setIntegrationSettings(settings);
    setIntegrationName(formData.get('integration_name') as string);
    setIntegrationDescription((formData.get('integration_description') as string) || '');
    setCurrentStep('credentials');
  };

  const addCredential = () => {
    setCredentials([
      ...credentials,
      {
        name: `${integrationType.display_name} Credential ${credentials.length + 1}`,
        secret: {},
      },
    ]);
  };

  const updateCredential = (index: number, updates: Partial<CredentialConfig>) => {
    const updated = [...credentials];
    updated[index] = { ...updated[index], ...updates };
    setCredentials(updated);
  };

  const removeCredential = (index: number) => {
    setCredentials(credentials.filter((_, i) => i !== index));
    setRevealedSecrets((prev) => {
      const next = new Set(prev);
      next.delete(index);
      return next;
    });
  };

  const toggleSchedule = (actionId: string) => {
    const existing = schedules.find((s) => s.action_id === actionId);
    if (existing) {
      setSchedules(
        schedules.map((s) => (s.action_id === actionId ? { ...s, enabled: !s.enabled } : s))
      );
    } else {
      setSchedules([
        ...schedules,
        {
          action_id: actionId,
          enabled: true,
          schedule_type: 'every',
          schedule_value: '5m',
        },
      ]);
    }
  };

  // Helper to update setup progress
  const updateSetupProgress = (
    step: string,
    status: 'pending' | 'working' | 'done' | 'error',
    message?: string
  ) => {
    setSetupProgress((prev) => {
      const existing = prev.find((p) => p.step === step);
      if (existing) {
        return prev.map((p) => (p.step === step ? { ...p, status, message } : p));
      }
      return [...prev, { step, status, message }];
    });
  };

  // Helper to create integration

  const createIntegrationStep = async (): Promise<string> => {
    updateSetupProgress('Creating integration', 'working');
    const integrationId = integrationSettings.integration_id as string;
    // eslint-disable-next-line @typescript-eslint/no-unused-vars, sonarjs/no-unused-vars
    const { integration_id: _integration_id, ...cleanSettings } = integrationSettings;

    // Auto-assign is_primary for AI archetype integrations
    const isAI = integrationType.archetypes?.includes('AI');
    const hasExistingPrimaryAI =
      isAI && (existingIntegrations ?? []).some((i) => i.settings?.is_primary === true);

    // Build settings with action overrides
    const settingsWithOverrides = {
      ...cleanSettings,
      ...(isAI ? { is_primary: !hasExistingPrimaryAI } : {}),
      actions: {} as Record<string, unknown>,
    };

    // Add action-specific overrides and enabled flags
    for (const action of actionDetails) {
      const schedule = schedules.find((s) => s.action_id === action.action_id);
      const overrides = actionOverrides[action.action_id];

      if (schedule?.enabled || overrides) {
        const actionSettings: Record<string, unknown> = {
          enabled: schedule?.enabled || false,
        };
        if (overrides?.host) {
          actionSettings.host = overrides.host;
        }
        if (overrides?.port) {
          actionSettings.port = overrides.port;
        }
        settingsWithOverrides.actions[action.action_id] = actionSettings;
      }
    }

    try {
      const createdIntegration = (await backendApi.createIntegration({
        integration_id: integrationId,
        integration_type: integrationType.integration_type,
        name: integrationName,
        description: integrationDescription,
        settings: settingsWithOverrides,
        enabled: true,
      })) as { integration_id: string };

      logger.info('Integration created successfully', createdIntegration, {
        component: 'IntegrationSetupWizard',
        method: 'createIntegrationStep',
        action: 'createIntegration',
      });
      updateSetupProgress(
        'Creating integration',
        'done',
        `Integration "${integrationName}" created`
      );
      return createdIntegration.integration_id;
    } catch (error_: unknown) {
      console.error('Failed to create integration:', error_);

      const errorMessage = extractApiErrorMessage(error_, 'Failed to create integration');
      updateSetupProgress('Creating integration', 'error', errorMessage);
      throw error_;
    }
  };

  // Helper to create credentials
  const createCredentialsStep = async (actualIntegrationId: string): Promise<void> => {
    if (credentials.length === 0) return;

    updateSetupProgress(`Creating ${credentials.length} credential(s)`, 'working');
    logger.info(
      `Creating ${credentials.length} credential(s)`,
      { count: credentials.length },
      {
        component: 'IntegrationSetupWizard',
        method: 'createCredentialsStep',
        action: 'createCredentials',
      }
    );

    for (let i = 0; i < credentials.length; i++) {
      const cred = credentials[i];
      try {
        logger.info(
          `Creating credential ${i + 1}`,
          { name: cred.name, hasSecret: !!cred.secret },
          {
            component: 'IntegrationSetupWizard',
            method: 'createCredentialsStep',
            action: 'createCredential',
          }
        );

        const createdCred = (await backendApi.createIntegrationCredential(actualIntegrationId, {
          provider: integrationType.integration_type,
          account: actualIntegrationId,
          secret: cred.secret,
          is_primary: i === 0,
          purpose: 'admin',
        })) as { credential_id: string };

        logger.info(
          'Credential created and associated',
          { credentialId: createdCred.credential_id, integrationId: actualIntegrationId },
          {
            component: 'IntegrationSetupWizard',
            method: 'createCredentialsStep',
            action: 'associateCredential',
          }
        );
        updateSetupProgress(`Creating credential ${i + 1}`, 'done');
      } catch (error_: unknown) {
        console.error(`Failed to create credential ${i + 1}:`, error_);

        const errorMessage = extractApiErrorMessage(error_, 'Failed to create credential');
        updateSetupProgress(`Creating ${credentials.length} credential(s)`, 'error', errorMessage);
        throw error_;
      }
    }

    updateSetupProgress(
      `Creating ${credentials.length} credential(s)`,
      'done',
      `${credentials.length} credential(s) created and associated`
    );
  };

  // Helper to create schedules
  const createSchedulesStep = async (actualIntegrationId: string): Promise<void> => {
    const enabledSchedules = schedules.filter((s) => s.enabled);
    if (enabledSchedules.length === 0) return;

    updateSetupProgress(`Creating ${enabledSchedules.length} schedule(s)`, 'working');
    logger.info(
      `Creating ${enabledSchedules.length} schedule(s)`,
      { count: enabledSchedules.length },
      {
        component: 'IntegrationSetupWizard',
        method: 'createSchedulesStep',
        action: 'createSchedules',
      }
    );

    for (const schedule of enabledSchedules) {
      try {
        logger.info(
          `Creating schedule for action`,
          {
            action_id: schedule.action_id,
            schedule_type: schedule.schedule_type,
            schedule_value: schedule.schedule_value,
          },
          {
            component: 'IntegrationSetupWizard',
            method: 'createSchedulesStep',
            action: 'createSchedule',
          }
        );

        // action_id maps directly to managed resource key
        await backendApi.updateManagedSchedule(actualIntegrationId, schedule.action_id, {
          schedule_value: schedule.schedule_value,
          enabled: true,
        });
        logger.info(
          'Schedule created successfully',
          { action_id: schedule.action_id },
          {
            component: 'IntegrationSetupWizard',
            method: 'createSchedulesStep',
            action: 'scheduleCreated',
          }
        );
      } catch (error_: unknown) {
        console.error(`Failed to create schedule for ${schedule.action_id}:`, error_);

        const errorMessage = extractApiErrorMessage(error_, 'Failed to create schedule');
        updateSetupProgress(
          `Creating ${enabledSchedules.length} schedule(s)`,
          'error',
          errorMessage
        );
        throw error_;
      }
    }

    updateSetupProgress(
      `Creating ${enabledSchedules.length} schedule(s)`,
      'done',
      `${enabledSchedules.length} schedule(s) created`
    );
  };

  // Helper to handle setup errors
  const handleSetupError = (error_: unknown) => {
    console.error('Setup failed:', error_);

    const axiosErr = error_ as { response?: { status?: number } };
    let errorStep = 'Setup';

    // Determine which step failed based on current progress
    const lastProgressStep = setupProgress.at(-1);
    if (lastProgressStep && lastProgressStep.status === 'working') {
      errorStep = lastProgressStep.step;
    }

    const errorMessage = extractApiErrorMessage(error_, 'Failed to complete setup');

    if (axiosErr.response?.status === 409) {
      updateSetupProgress(errorStep, 'error', errorMessage);
      if (errorMessage.includes('already exists')) {
        setError(
          `${errorMessage}. Please use a different Integration ID or delete the existing integration first.`
        );
      } else {
        setError(errorMessage);
      }
    } else {
      updateSetupProgress(errorStep, 'error', errorMessage);
      setError(errorMessage);
    }

    setIsSubmitting(false);
  };

  const executeSetup = async () => {
    setIsSubmitting(true);
    setError(null);
    setSetupProgress([]);

    logger.info(
      'Starting integration setup',
      {
        credentials: credentials.length,
        schedules: schedules.filter((s) => s.enabled).length,
        integrationId: integrationSettings.integration_id,
      },
      { component: 'IntegrationSetupWizard', method: 'executeSetup', action: 'startSetup' }
    );

    try {
      // Step 1: Create the integration
      const actualIntegrationId = await createIntegrationStep();

      // Step 2: Create credentials
      await createCredentialsStep(actualIntegrationId);

      // Step 3: Create schedules
      await createSchedulesStep(actualIntegrationId);

      // All done!
      updateSetupProgress('Setup complete', 'done', 'Your integration is ready to use!');

      // Wait a moment before closing to show success
      setTimeout(() => {
        onSuccess();
      }, 2000);
    } catch (error_: unknown) {
      handleSetupError(error_);
    }
  };

  const renderStepIndicator = () => {
    const steps: WizardStep[] = ['integration', 'credentials', 'schedules', 'summary'];
    const stepLabels = {
      integration: 'Integration',
      credentials: 'Credentials',
      schedules: 'Schedules',
      summary: 'Review',
    };

    return (
      <div className="flex justify-between mb-6">
        {steps.map((step, index) => (
          <div key={step} className="flex items-center">
            <div
              className={`
              flex items-center justify-center w-8 h-8 rounded-full
              ${(() => {
                if (currentStep === step) return 'bg-primary text-white';
                if (steps.indexOf(currentStep) > index) return 'bg-green-500 text-white';
                return 'bg-dark-700 text-gray-400';
              })()}
            `}
            >
              {steps.indexOf(currentStep) > index ? <CheckIcon className="w-5 h-5" /> : index + 1}
            </div>
            <span className="ml-2 text-sm text-gray-300">{stepLabels[step]}</span>
            {index < steps.length - 1 && (
              <div
                className={`w-20 h-0.5 ml-4 ${
                  steps.indexOf(currentStep) > index ? 'bg-green-500' : 'bg-dark-700'
                }`}
              />
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={handleSafeClose}
      onKeyDown={(e) => e.key === 'Escape' && handleSafeClose()}
      role="dialog"
      aria-modal="true"
    >
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
      <div
        className="bg-dark-800 rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
        role="document"
      >
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-xl font-semibold text-white">
              Setup {integrationType.display_name}
            </h2>
            <p className="text-gray-400 text-sm mt-1">
              Complete all steps to configure your integration
            </p>
          </div>
          <button onClick={handleSafeClose} className="text-gray-400 hover:text-white">
            <XMarkIcon className="w-6 h-6" />
          </button>
        </div>

        {renderStepIndicator()}

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500 rounded-sm text-red-400">
            {error}
          </div>
        )}

        {/* Integration Settings Step */}
        {currentStep === 'integration' && (
          <form onSubmit={handleIntegrationSubmit}>
            <div className="space-y-4">
              <div>
                <label
                  htmlFor="integration_name"
                  className="block text-sm font-medium text-gray-300 mb-2"
                >
                  Integration Name *
                </label>
                <input
                  id="integration_name"
                  name="integration_name"
                  type="text"
                  required
                  value={integrationName}
                  onChange={(e) => setIntegrationName(e.target.value)}
                  className="w-full bg-dark-700 border border-gray-600 rounded-sm px-3 py-2 text-white"
                  placeholder={`My ${integrationType.display_name} Instance`}
                />
              </div>

              <div>
                <label
                  htmlFor="integration_description"
                  className="block text-sm font-medium text-gray-300 mb-2"
                >
                  Description
                </label>
                <textarea
                  id="integration_description"
                  name="integration_description"
                  value={integrationDescription}
                  onChange={(e) => setIntegrationDescription(e.target.value)}
                  className="w-full bg-dark-700 border border-gray-600 rounded-sm px-3 py-2 text-white"
                  rows={3}
                  placeholder="Optional description for this integration"
                />
              </div>

              {/* Integration ID field using integration_id_config */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  {integrationType.integration_id_config?.display_name || 'Integration ID'}
                </label>
                {integrationType.integration_id_config?.description && (
                  <p className="text-xs text-gray-400 mb-2">
                    {integrationType.integration_id_config.description}
                  </p>
                )}
                <input
                  name="integration_id"
                  type="text"
                  defaultValue={
                    (integrationSettings.integration_id as string | undefined) ||
                    integrationType.integration_id_config?.default ||
                    `${integrationType.integration_type}-main`
                  }
                  pattern={sanitizeHtmlPattern(
                    integrationType.integration_id_config?.pattern || '^[a-z0-9][a-z0-9-]*$'
                  )}
                  className={`w-full bg-dark-700 border rounded px-3 py-2 text-white ${
                    validationErrors.integration_id ? 'border-red-500' : 'border-gray-600'
                  }`}
                  placeholder={
                    integrationType.integration_id_config?.placeholder ||
                    `${integrationType.integration_type}-main`
                  }
                />
                {validationErrors.integration_id && (
                  <p className="mt-1 text-xs text-red-400">{validationErrors.integration_id}</p>
                )}
              </div>

              {integrationType.settings_schema?.properties && (
                <div className="space-y-4">
                  <h3 className="text-lg font-medium text-white">Configuration</h3>
                  {Object.entries(integrationType.settings_schema.properties).map(
                    ([key, property]: [string, SchemaProperty]) => {
                      // Skip integration_id if it appears in settings_schema - it's handled separately above
                      if (key === 'integration_id') return null;

                      const isRequired = property.required || false;
                      const getFieldType = () => {
                        if (property.type === 'integer') return 'number';
                        if (property.type === 'boolean') return 'checkbox';
                        return 'text';
                      };
                      const fieldType = getFieldType();
                      const pattern = property.pattern
                        ? sanitizeHtmlPattern(property.pattern)
                        : undefined;

                      return (
                        <div key={key}>
                          <label className="block text-sm font-medium text-gray-300 mb-2">
                            {property.display_name || key} {isRequired && '*'}
                          </label>
                          {property.description && (
                            <p className="text-xs text-gray-400 mb-2">{property.description}</p>
                          )}
                          <input
                            name={key}
                            type={fieldType}
                            required={isRequired}
                            defaultValue={
                              (integrationSettings[key] as string | number | undefined) ||
                              (property.default as string | number | undefined) ||
                              ''
                            }
                            pattern={pattern}
                            title={pattern ? `Format: ${property.description}` : undefined}
                            className={`w-full bg-dark-700 border rounded px-3 py-2 text-white ${
                              validationErrors[key] ? 'border-red-500' : 'border-gray-600'
                            }`}
                            placeholder={
                              property.placeholder || (property.default as string | undefined) || ''
                            }
                          />
                          {validationErrors[key] && (
                            <p className="mt-1 text-xs text-red-400">{validationErrors[key]}</p>
                          )}
                        </div>
                      );
                    }
                  )}
                </div>
              )}
            </div>

            <div className="flex justify-end space-x-3 mt-6">
              <button
                type="button"
                onClick={handleSafeClose}
                className="px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-sm text-white"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-primary hover:bg-primary-dark rounded-sm text-white"
              >
                Next: Credentials
              </button>
            </div>
          </form>
        )}

        {/* Credentials Step */}
        {currentStep === 'credentials' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h3 className="text-lg font-medium text-white">Credentials</h3>
                <p className="text-sm text-gray-400">
                  Required scopes: {getRequiredCredentialScopes().join(', ') || 'None specified'}
                </p>
                {!hasRequiredCredentialFields() &&
                  integrationType.credential_schema?.properties && (
                    <p className="text-sm text-blue-400 mt-1">
                      All credential fields are optional for this integration
                    </p>
                  )}
              </div>
              <button
                type="button"
                onClick={addCredential}
                className="px-3 py-1 bg-primary hover:bg-primary-dark rounded-sm text-white text-sm"
              >
                Add Credential
              </button>
            </div>

            {credentials.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                No credentials configured. Click &quot;Add Credential&quot; to create one.
              </div>
            ) : (
              credentials.map((cred, index) => (
                <div key={index} className="p-4 bg-dark-700 rounded-sm space-y-3">
                  <div className="flex justify-between">
                    <h4 className="text-white">Credential {index + 1}</h4>
                    <button
                      onClick={() => removeCredential(index)}
                      className="text-red-400 hover:text-red-300"
                    >
                      Remove
                    </button>
                  </div>

                  <div>
                    <label
                      htmlFor={`cred-name-${index}`}
                      className="block text-sm text-gray-300 mb-1"
                    >
                      Credential Name
                    </label>
                    <input
                      id={`cred-name-${index}`}
                      type="text"
                      value={cred.name}
                      onChange={(e) => updateCredential(index, { name: e.target.value })}
                      className="w-full bg-dark-800 border border-gray-600 rounded-sm px-3 py-2 text-white"
                      placeholder="e.g., Production API Key"
                    />
                  </div>

                  {/* Dynamic credential fields based on credential_schema */}
                  {integrationType.credential_schema?.properties && (
                    <div className="space-y-3">
                      {Object.entries(integrationType.credential_schema.properties).map(
                        ([fieldKey, fieldSchema]: [string, SchemaProperty]) => {
                          const isPassword =
                            fieldSchema.format === 'password' ||
                            fieldKey.toLowerCase().includes('password');
                          const isRevealed = revealedSecrets.has(
                            index * 100 + fieldKey.charCodeAt(0)
                          ); // Unique key per field

                          return (
                            <div key={fieldKey}>
                              <label className="block text-sm text-gray-300 mb-1">
                                {fieldSchema.display_name || fieldKey} {fieldSchema.required && '*'}
                              </label>
                              {fieldSchema.description && (
                                <p className="text-xs text-gray-400 mb-1">
                                  {fieldSchema.description}
                                </p>
                              )}
                              <div className="flex items-center space-x-2">
                                <input
                                  type={isPassword && !isRevealed ? 'password' : 'text'}
                                  value={cred.secret[fieldKey] || ''}
                                  onChange={(e) =>
                                    updateCredential(index, {
                                      secret: { ...cred.secret, [fieldKey]: e.target.value },
                                    })
                                  }
                                  className={`flex-1 bg-dark-800 border rounded px-3 py-2 text-white ${
                                    validationErrors[`credential_${index}_${fieldKey}`]
                                      ? 'border-red-500'
                                      : 'border-gray-600'
                                  }`}
                                  placeholder={`Enter ${fieldSchema.display_name || fieldKey}`}
                                  required={fieldSchema.required}
                                />
                                {isPassword && (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const key = index * 100 + fieldKey.charCodeAt(0);
                                      const next = new Set(revealedSecrets);
                                      if (next.has(key)) {
                                        next.delete(key);
                                      } else {
                                        next.add(key);
                                      }
                                      setRevealedSecrets(next);
                                    }}
                                    className="p-2 text-gray-400 hover:text-white"
                                  >
                                    {isRevealed ? (
                                      <EyeSlashIcon className="w-5 h-5" />
                                    ) : (
                                      <EyeIcon className="w-5 h-5" />
                                    )}
                                  </button>
                                )}
                              </div>
                              {validationErrors[`credential_${index}_${fieldKey}`] && (
                                <p className="mt-1 text-xs text-red-400">
                                  {validationErrors[`credential_${index}_${fieldKey}`]}
                                </p>
                              )}
                            </div>
                          );
                        }
                      )}
                    </div>
                  )}

                  {/* Fallback if no credential_schema */}
                  {!integrationType.credential_schema && (
                    <div>
                      <label
                        htmlFor={`cred-token-${index}`}
                        className="block text-sm text-gray-300 mb-1"
                      >
                        API Token / Password
                      </label>
                      <div className="flex items-center space-x-2">
                        <input
                          id={`cred-token-${index}`}
                          type={revealedSecrets.has(index) ? 'text' : 'password'}
                          value={cred.secret.token || ''}
                          onChange={(e) =>
                            updateCredential(index, {
                              secret: { ...cred.secret, token: e.target.value },
                            })
                          }
                          className="flex-1 bg-dark-800 border border-gray-600 rounded-sm px-3 py-2 text-white"
                          placeholder="Enter token or password"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            const next = new Set(revealedSecrets);
                            if (next.has(index)) {
                              next.delete(index);
                            } else {
                              next.add(index);
                            }
                            setRevealedSecrets(next);
                          }}
                          className="p-2 text-gray-400 hover:text-white"
                        >
                          {revealedSecrets.has(index) ? (
                            <EyeSlashIcon className="w-5 h-5" />
                          ) : (
                            <EyeIcon className="w-5 h-5" />
                          )}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))
            )}

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setCurrentStep('integration')}
                className="px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-sm text-white"
              >
                Back
              </button>
              <button
                onClick={() => {
                  const errors = validateCredentials();
                  if (Object.keys(errors).length > 0) {
                    setValidationErrors(errors);
                    setError('Please fill in all required credential fields');
                  } else {
                    setValidationErrors({});
                    setError(null);
                    setCurrentStep('schedules');
                  }
                }}
                className="px-4 py-2 bg-primary hover:bg-primary-dark rounded-sm text-white"
              >
                Next: Schedules
              </button>
            </div>
          </div>
        )}

        {/* Schedules Step */}
        {currentStep === 'schedules' && (
          <div className="space-y-4">
            <h3 className="text-lg font-medium text-white mb-4">Configure Schedules</h3>
            <p className="text-sm text-gray-400 mb-4">
              Select which actions should run on a schedule
            </p>

            {actionDetails.map((action) => {
              const schedule = schedules.find((s) => s.action_id === action.action_id);
              const isEnabled = schedule?.enabled || false;

              return (
                <div key={action.action_id} className="p-4 bg-dark-700 rounded-sm">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h4 className="text-white">{action.display_name || action.action_id}</h4>
                      <p className="text-sm text-gray-400">
                        {action.description || 'No description available'}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => toggleSchedule(action.action_id)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        isEnabled ? 'bg-green-500' : 'bg-gray-600'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          isEnabled ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </div>

                  {isEnabled && schedule && (
                    <div className="mt-3 space-y-3">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label
                            htmlFor={`schedule-type-${action.action_id}`}
                            className="block text-sm text-gray-300 mb-1"
                          >
                            Schedule Type
                          </label>
                          <select
                            id={`schedule-type-${action.action_id}`}
                            value={schedule.schedule_type}
                            onChange={(e) =>
                              setSchedules(
                                schedules.map((s) =>
                                  s.action_id === action.action_id
                                    ? { ...s, schedule_type: e.target.value as 'every' | 'cron' }
                                    : s
                                )
                              )
                            }
                            className="w-full bg-dark-800 border border-gray-600 rounded-sm px-3 py-2 text-white"
                          >
                            <option value="every">Every</option>
                          </select>
                        </div>
                        <div>
                          <label
                            htmlFor={`schedule-interval-${action.action_id}`}
                            className="block text-sm text-gray-300 mb-1"
                          >
                            Interval
                          </label>
                          <input
                            id={`schedule-interval-${action.action_id}`}
                            type="text"
                            value={schedule.schedule_value}
                            onChange={(e) =>
                              setSchedules(
                                schedules.map((s) =>
                                  s.action_id === action.action_id
                                    ? { ...s, schedule_value: e.target.value }
                                    : s
                                )
                              )
                            }
                            className="w-full bg-dark-800 border border-gray-600 rounded-sm px-3 py-2 text-white"
                            placeholder="5m"
                          />
                        </div>
                      </div>

                      {/* Schedule Parameters */}
                      {action.params_schema?.properties &&
                        Object.keys(action.params_schema.properties).length > 0 && (
                          <div className="border-t border-gray-600 pt-3">
                            <h5 className="text-sm font-medium text-gray-300 mb-2">
                              Schedule Parameters
                            </h5>
                            <div className="space-y-2">
                              {Object.entries(action.params_schema.properties).map(
                                ([paramKey, paramSchema]) => {
                                  const value =
                                    schedule.params?.[paramKey] ?? paramSchema.default ?? '';

                                  // Compute placeholder for integer inputs
                                  let integerPlaceholder = paramSchema.placeholder;
                                  if (!integerPlaceholder) {
                                    let exampleValue = 0;
                                    if (typeof paramSchema.default === 'number') {
                                      exampleValue = paramSchema.default;
                                    } else if (typeof paramSchema.min === 'number') {
                                      exampleValue = paramSchema.min;
                                    }
                                    integerPlaceholder = `e.g., ${exampleValue}`;
                                  }

                                  return (
                                    <div key={paramKey}>
                                      <label className="block text-xs text-gray-400 mb-1">
                                        {paramSchema.display_name || paramKey}
                                        {paramSchema.required && (
                                          <span className="text-red-400 ml-1">*</span>
                                        )}
                                      </label>
                                      {paramSchema.description && (
                                        <p className="text-xs text-gray-500 mb-1">
                                          {paramSchema.description}
                                        </p>
                                      )}

                                      {(() => {
                                        if (paramSchema.type === 'boolean') {
                                          return (
                                            <input
                                              type="checkbox"
                                              checked={value === true}
                                              // eslint-disable-next-line sonarjs/no-nested-functions
                                              onChange={(e) =>
                                                updateScheduleParam(
                                                  action.action_id,
                                                  paramKey,
                                                  e.target.checked
                                                )
                                              }
                                              className="rounded-sm border-gray-600 bg-dark-800 text-primary"
                                            />
                                          );
                                        }
                                        if (paramSchema.type === 'integer') {
                                          return (
                                            <input
                                              type="number"
                                              value={
                                                typeof value === 'number'
                                                  ? value
                                                  : (value as string) || ''
                                              }
                                              min={paramSchema.min}
                                              max={paramSchema.max}
                                              // eslint-disable-next-line sonarjs/no-nested-functions
                                              onChange={(e) =>
                                                updateScheduleParam(
                                                  action.action_id,
                                                  paramKey,
                                                  e.target.value
                                                    ? Number.parseInt(e.target.value)
                                                    : undefined
                                                )
                                              }
                                              className="w-full bg-dark-800 border border-gray-600 rounded-sm px-2 py-1 text-sm text-white"
                                              placeholder={integerPlaceholder}
                                            />
                                          );
                                        }
                                        return (
                                          <input
                                            type="text"
                                            value={(value as string) || ''}
                                            // eslint-disable-next-line sonarjs/no-nested-functions
                                            onChange={(e) =>
                                              updateScheduleParam(
                                                action.action_id,
                                                paramKey,
                                                e.target.value
                                              )
                                            }
                                            className="w-full bg-dark-800 border border-gray-600 rounded-sm px-2 py-1 text-sm text-white"
                                            placeholder={
                                              paramSchema.placeholder ||
                                              (paramSchema.default as string | undefined) ||
                                              ''
                                            }
                                          />
                                        );
                                      })()}

                                      {/* Show validation errors if any */}
                                      {validationErrors[
                                        `schedule_${schedules.indexOf(schedule)}_${paramKey}`
                                      ] && (
                                        <p className="text-xs text-red-400 mt-1">
                                          {
                                            validationErrors[
                                              `schedule_${schedules.indexOf(schedule)}_${paramKey}`
                                            ]
                                          }
                                        </p>
                                      )}
                                    </div>
                                  );
                                }
                              )}
                            </div>
                          </div>
                        )}

                      {/* Connector-specific overrides */}
                      <div className="border-t border-gray-600 pt-3">
                        <h5 className="text-sm font-medium text-gray-300 mb-2">
                          Override Settings (Optional)
                        </h5>
                        <p className="text-xs text-gray-400 mb-2">
                          Override base settings for this action
                        </p>
                        <div className="space-y-2">
                          <div>
                            <label
                              htmlFor={`host-override-${action.action_id}`}
                              className="block text-xs text-gray-400 mb-1"
                            >
                              Host Override
                            </label>
                            <input
                              id={`host-override-${action.action_id}`}
                              type="text"
                              value={
                                (actionOverrides[action.action_id]?.host as string | undefined) ||
                                ''
                              }
                              onChange={(e) =>
                                setActionOverrides({
                                  ...actionOverrides,
                                  [action.action_id]: {
                                    ...actionOverrides[action.action_id],
                                    host: e.target.value,
                                  },
                                })
                              }
                              className="w-full bg-dark-800 border border-gray-600 rounded-sm px-2 py-1 text-sm text-white"
                              placeholder={
                                typeof integrationSettings.host === 'string'
                                  ? `Default: ${integrationSettings.host}`
                                  : 'Default: base host'
                              }
                            />
                          </div>
                          <div>
                            <label
                              htmlFor={`port-override-${action.action_id}`}
                              className="block text-xs text-gray-400 mb-1"
                            >
                              Port Override
                            </label>
                            <input
                              id={`port-override-${action.action_id}`}
                              type="number"
                              value={
                                (actionOverrides[action.action_id]?.port as number | undefined) ||
                                ''
                              }
                              onChange={(e) =>
                                setActionOverrides({
                                  ...actionOverrides,
                                  [action.action_id]: {
                                    ...actionOverrides[action.action_id],
                                    port: e.target.value
                                      ? Number.parseInt(e.target.value)
                                      : undefined,
                                  },
                                })
                              }
                              className="w-full bg-dark-800 border border-gray-600 rounded-sm px-2 py-1 text-sm text-white"
                              placeholder={
                                typeof integrationSettings.port === 'number'
                                  ? `Default: ${integrationSettings.port}`
                                  : 'Default: base port'
                              }
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setCurrentStep('credentials')}
                className="px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-sm text-white"
              >
                Back
              </button>
              <button
                onClick={() => {
                  const errors = validateScheduleParams();
                  if (Object.keys(errors).length > 0) {
                    setValidationErrors(errors);
                    setError('Please configure required schedule parameters');
                  } else {
                    setValidationErrors({});
                    setError(null);
                    setCurrentStep('summary');
                  }
                }}
                className="px-4 py-2 bg-primary hover:bg-primary-dark rounded-sm text-white"
              >
                Review Setup
              </button>
            </div>
          </div>
        )}

        {/* Summary Step */}
        {currentStep === 'summary' && (
          <div className="space-y-6">
            <h3 className="text-lg font-medium text-white">Review Configuration</h3>

            <div className="space-y-4">
              {/* Integration Details */}
              <div className="p-4 bg-dark-700 rounded-sm border border-dark-600">
                <h4 className="text-white font-medium mb-3 flex items-center">
                  <span className="text-primary mr-2">●</span>
                  Integration Details
                </h4>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-400">Name:</span>
                    <p className="text-white font-medium">{integrationName || 'Not specified'}</p>
                  </div>
                  <div>
                    <span className="text-gray-400">Type:</span>
                    <p className="text-white font-medium">{integrationType.display_name}</p>
                  </div>
                  <div>
                    <span className="text-gray-400">Integration ID:</span>
                    <p className="text-white font-mono">
                      {String(integrationSettings.integration_id)}
                    </p>
                  </div>
                  {integrationDescription && (
                    <div className="col-span-2">
                      <span className="text-gray-400">Description:</span>
                      <p className="text-white">{integrationDescription}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Configuration Settings */}
              <div className="p-4 bg-dark-700 rounded-sm border border-dark-600">
                <h4 className="text-white font-medium mb-3 flex items-center">
                  <span className="text-primary mr-2">●</span>
                  Configuration Settings
                </h4>
                <div className="space-y-2 text-sm">
                  {Object.entries(integrationSettings).map(([key, value]) => {
                    if (key === 'integration_id') return null;
                    const property = integrationType.settings_schema?.properties?.[
                      key
                    ] as SchemaProperty;
                    return (
                      <div
                        key={key}
                        className="flex justify-between py-1 border-b border-dark-600 last:border-0"
                      >
                        <span className="text-gray-400">{property?.display_name || key}:</span>
                        <span className="text-white font-mono">
                          {(() => {
                            if (typeof value === 'boolean') return value ? 'Yes' : 'No';
                            if (typeof value === 'string') return value;
                            if (typeof value === 'number') return String(value);
                            return String(value);
                          })()}
                        </span>
                      </div>
                    );
                  })}

                  {/* Connector-specific overrides */}
                  {Object.entries(actionOverrides).length > 0 && (
                    <div className="mt-3 pt-3 border-t border-dark-600">
                      <p className="text-gray-400 mb-2">Connector Overrides:</p>
                      {Object.entries(actionOverrides).map(([actionId, overrides]) => (
                        <div key={actionId} className="ml-4 mb-2">
                          <p className="text-white text-xs font-medium">{actionId}:</p>
                          {Object.entries(overrides).map(([key, value]) => (
                            <div key={key} className="ml-4 text-xs">
                              <span className="text-gray-500">{key}:</span>
                              <span className="text-gray-300 ml-2">
                                {typeof value === 'string' || typeof value === 'number'
                                  ? value
                                  : String(value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Credentials */}
              <div className="p-4 bg-dark-700 rounded-sm border border-dark-600">
                <h4 className="text-white font-medium mb-3 flex items-center">
                  <span className="text-primary mr-2">●</span>
                  Credentials ({credentials.length})
                </h4>
                {(() => {
                  if (credentials.length === 0) {
                    if (hasRequiredCredentialFields()) {
                      return (
                        <p className="text-sm text-yellow-400 bg-yellow-900/20 p-2 rounded-sm">
                          ⚠️ No credentials configured - actions may not be able to authenticate
                        </p>
                      );
                    }
                    return (
                      <p className="text-sm text-gray-400 p-2 rounded-sm">
                        No credentials configured (all credential fields are optional)
                      </p>
                    );
                  }
                  return (
                    <div className="space-y-2">
                      {credentials.map((cred, i) => (
                        <div key={i} className="p-2 bg-dark-800 rounded-sm">
                          <p className="text-white font-medium text-sm">{cred.name}</p>
                          <div className="mt-1 text-xs text-gray-400">
                            {Object.keys(cred.secret).map((key) => {
                              const fieldSchema = integrationType.credential_schema?.properties?.[
                                key
                              ] as SchemaProperty;
                              return (
                                <span key={key} className="mr-3">
                                  {fieldSchema?.display_name || key}:{' '}
                                  <span className="text-gray-500">●●●●●●</span>
                                </span>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  );
                })()}
              </div>

              {/* Scheduled Connectors */}
              <div className="p-4 bg-dark-700 rounded-sm border border-dark-600">
                <h4 className="text-white font-medium mb-3 flex items-center">
                  <span className="text-primary mr-2">●</span>
                  Connector Configuration
                </h4>
                <div className="space-y-3">
                  {actionDetails.map((action) => {
                    const schedule = schedules.find((s) => s.action_id === action.action_id);
                    const isEnabled = schedule?.enabled || false;
                    const override = actionOverrides[action.action_id];

                    return (
                      <div
                        key={action.action_id}
                        className={`p-3 rounded-sm border ${isEnabled ? 'bg-dark-800 border-primary/30' : 'bg-dark-900 border-dark-600 opacity-60'}`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center">
                            <span
                              className={`w-2 h-2 rounded-full mr-2 ${isEnabled ? 'bg-green-400' : 'bg-gray-600'}`}
                            />
                            <span className="text-white font-medium">{action.display_name}</span>
                          </div>
                          <span
                            className={`text-xs px-2 py-1 rounded-sm ${isEnabled ? 'bg-green-900/30 text-green-400' : 'bg-gray-900 text-gray-500'}`}
                          >
                            {isEnabled ? 'Enabled' : 'Disabled'}
                          </span>
                        </div>

                        {isEnabled && schedule && (
                          <>
                            <p className="text-xs text-gray-400 mb-2">{action.description}</p>
                            <div className="space-y-1 text-xs">
                              <div className="flex justify-between">
                                <span className="text-gray-500">Schedule:</span>
                                <span className="text-gray-300">
                                  {schedule.schedule_type === 'every'
                                    ? `Every ${schedule.schedule_value}`
                                    : `Cron: ${schedule.schedule_value}`}
                                </span>
                              </div>

                              {schedule.params && Object.keys(schedule.params).length > 0 && (
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Parameters:</span>
                                  <span className="text-gray-300">
                                    {Object.entries(schedule.params)
                                      .map(([k, v]) => `${k}: ${String(v)}`)
                                      .join(', ')}
                                  </span>
                                </div>
                              )}

                              {override && (
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Overrides:</span>
                                  <span className="text-yellow-400">
                                    {Object.entries(override)
                                      .map(([k, v]) => `${k}: ${String(v)}`)
                                      .join(', ')}
                                  </span>
                                </div>
                              )}

                              {action.credential_scopes && action.credential_scopes.length > 0 && (
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Required Scopes:</span>
                                  <span className="text-gray-300">
                                    {action.credential_scopes.join(', ')}
                                  </span>
                                </div>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Summary counts */}
                <div className="mt-3 pt-3 border-t border-dark-600 flex justify-between text-sm">
                  <span className="text-gray-400">Total Connectors:</span>
                  <span className="text-white">
                    {schedules.filter((s) => s.enabled).length} enabled / {actionDetails.length}{' '}
                    available
                  </span>
                </div>
              </div>

              {/* Warnings or Important Notes */}
              {((credentials.length === 0 && hasRequiredCredentialFields()) ||
                schedules.filter((s) => s.enabled).length === 0) && (
                <div className="p-4 bg-yellow-900/20 border border-yellow-600 rounded-sm">
                  <h4 className="text-yellow-400 font-medium mb-2">⚠️ Important Notes</h4>
                  <ul className="text-sm text-yellow-300 space-y-1">
                    {credentials.length === 0 && hasRequiredCredentialFields() && (
                      <li>
                        • No credentials configured - you may need to add credentials later for
                        actions to work
                      </li>
                    )}
                    {schedules.filter((s) => s.enabled).length === 0 && (
                      <li>
                        • No actions enabled - you can enable them later from the integration
                        settings
                      </li>
                    )}
                  </ul>
                </div>
              )}
            </div>

            {/* Setup Progress Display */}
            {setupProgress.length > 0 && (
              <div className="mt-6 p-4 bg-dark-700 rounded-sm">
                <h4 className="text-white font-medium mb-3">Setup Progress</h4>
                <div className="space-y-2">
                  {setupProgress.map((step, index) => (
                    <div key={index} className="flex items-center space-x-3">
                      {step.status === 'working' && (
                        <ArrowPathIcon className="w-5 h-5 text-blue-400 animate-spin" />
                      )}
                      {step.status === 'done' && <CheckIcon className="w-5 h-5 text-green-400" />}
                      {step.status === 'error' && (
                        <ExclamationCircleIcon className="w-5 h-5 text-red-400" />
                      )}
                      {step.status === 'pending' && (
                        <div className="w-5 h-5 rounded-full border-2 border-gray-600" />
                      )}
                      <div className="flex-1">
                        <span
                          className={`text-sm ${(() => {
                            if (step.status === 'error') return 'text-red-400';
                            if (step.status === 'done') return 'text-green-400';
                            if (step.status === 'working') return 'text-blue-400';
                            return 'text-gray-400';
                          })()}`}
                        >
                          {step.step}
                          {step.status === 'done' && ' ✓'}
                        </span>
                        {step.message && (
                          <p className="text-xs text-gray-500 mt-1">{step.message}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {error && setupProgress.length === 0 && (
              <div className="mt-4 p-3 bg-red-900/20 border border-red-500 rounded-sm text-red-400">
                {error}
              </div>
            )}

            <div className="flex justify-end space-x-3 mt-4">
              <button
                onClick={() => setCurrentStep('schedules')}
                disabled={isSubmitting}
                className="px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-sm text-white disabled:opacity-50"
              >
                Back
              </button>
              <button
                onClick={() => void executeSetup()}
                disabled={isSubmitting}
                className="px-4 py-2 bg-green-500 hover:bg-green-600 rounded-sm text-white disabled:opacity-50"
              >
                {(() => {
                  if (isSubmitting) return 'Setting up...';
                  if (error) return 'Retry Setup';
                  return 'Complete Setup';
                })()}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Confirmation Dialog for Unsaved Changes */}
      {showConfirmDialog && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-60"
          role="dialog"
          aria-modal="true"
        >
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
          <div
            className="bg-dark-800 rounded-lg p-6 max-w-md w-full mx-4 border border-dark-600"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
            role="document"
          >
            <div className="flex items-start space-x-3 mb-4">
              <div className="shrink-0">
                <ExclamationTriangleIcon className="w-6 h-6 text-yellow-500" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-medium text-white mb-2">Unsaved Changes</h3>
                <p className="text-gray-300 text-sm">
                  You have unsaved changes in the integration setup wizard. Are you sure you want to
                  exit? All your configuration and progress will be lost.
                </p>
              </div>
            </div>

            <div className="mt-6 flex justify-end space-x-3">
              <button
                onClick={handleCancelClose}
                className="px-4 py-2 bg-dark-700 hover:bg-dark-600 text-white rounded-sm transition-colors"
              >
                Continue Editing
              </button>
              <button
                onClick={handleConfirmClose}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-sm transition-colors"
              >
                Discard Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
