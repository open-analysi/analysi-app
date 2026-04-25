/* eslint-disable sonarjs/deprecation */
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';

import { Dialog, Combobox } from '@headlessui/react';
import {
  XMarkIcon,
  SparklesIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  ArrowPathIcon,
  CodeBracketIcon,
  ChevronUpDownIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import type { Alert } from '../../types/alert';
import type {
  TaskBuildingRun,
  TaskBuildingRunStatus,
  TaskGenerationProgressMessage,
} from '../../types/taskRun';
import { ConfirmDialog } from '../common/ConfirmDialog';

// Helper to get severity badge styles
const getSeverityBadgeClass = (severity: string): string => {
  switch (severity) {
    case 'critical':
      return 'bg-red-900/50 text-red-300';
    case 'high':
      return 'bg-orange-900/50 text-orange-300';
    case 'medium':
      return 'bg-yellow-900/50 text-yellow-300';
    default:
      return 'bg-gray-700 text-gray-300';
  }
};

interface TaskGenerationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onComplete: (taskId: string, taskName: string) => void;
  /** When provided, the AI modifies this task instead of creating from scratch. */
  taskId?: string | null;
  taskName?: string | null;
}

interface TaskGenerationResult {
  task_id: string;
  cy_name: string;
  error?: string;
}

const MIN_DESCRIPTION_LENGTH = 10;
const MAX_DESCRIPTION_LENGTH = 5000;

// Example prompts to inspire users - these can be clicked to populate the textarea
const EXAMPLE_PROMPTS = [
  {
    title: 'VirusTotal IP Check',
    prompt:
      'Create a task that checks an IP address against VirusTotal. Extract the IP from the alert (try alert.observables[0].value first, then alert.evidences[0].src_endpoint.ip). Return the detection count and use an LLM to summarize whether the IP is malicious.',
  },
  {
    title: 'Splunk Event Correlation',
    prompt:
      'Create a task that searches Splunk for related events within ±15 minutes of the alert time. Use the source IP from the alert, build an SPL query to find related activity, and have an LLM summarize any suspicious patterns.',
  },
  {
    title: 'EDR Terminal History',
    prompt:
      'Create a task that pulls terminal command history from the EDR for the endpoint IP in the alert. Analyze the commands with an LLM to identify suspicious activity like privilege escalation or persistence mechanisms.',
  },
  {
    title: 'Domain Reputation Check',
    prompt:
      'Create a task that checks domain reputation using VirusTotal. Extract domains from the alert IOCs, query each one, and summarize the threat level with detection counts and categories.',
  },
];

// Helper function to get status icon
const getStatusIcon = (status: TaskBuildingRunStatus | null) => {
  if (status === 'completed') {
    return <CheckCircleIcon className="h-5 w-5 text-green-400" />;
  }
  if (status === 'failed') {
    return <ExclamationCircleIcon className="h-5 w-5 text-red-400" />;
  }
  return <ArrowPathIcon className="h-5 w-5 text-purple-400 animate-spin" />;
};

// Helper function to get status text
const getStatusText = (status: TaskBuildingRunStatus | null): string => {
  switch (status) {
    case 'completed':
      return 'Task Generated Successfully';
    case 'failed':
      return 'Generation Failed';
    case 'running':
      return 'Generating Task...';
    default:
      return 'Starting Generation...';
  }
};

// Helper function to get message color
const getMessageColor = (level: string): string => {
  switch (level) {
    case 'error':
      return 'text-red-400';
    case 'warning':
      return 'text-yellow-400';
    default:
      return 'text-gray-300';
  }
};

// Helper to format progress message with details
const formatProgressMessage = (msg: TaskGenerationProgressMessage): string => {
  const { message, details } = msg;

  // If it's a tool call, try to extract meaningful info from details
  if (
    message.startsWith('Tool call:') &&
    details &&
    typeof details.input === 'object' &&
    details.input !== null
  ) {
    const input = details.input as Record<string, unknown>;

    // For Skill tool, show the skill name
    if (message === 'Tool call: Skill' && typeof input.skill === 'string') {
      return `Tool call: Skill (${input.skill})`;
    }

    // For Write/Edit/Read tools, show the file path
    if (typeof input.file_path === 'string') {
      const fileName = input.file_path.split('/').pop();
      return `${message} → ${fileName}`;
    }

    // For Bash, show truncated command
    if (typeof input.command === 'string') {
      const cmd = input.command.length > 50 ? input.command.slice(0, 50) + '...' : input.command;
      return `${message}: ${cmd}`;
    }
  }

  return message;
};

export const TaskGenerationModal: React.FC<TaskGenerationModalProps> = ({
  isOpen,
  onClose,
  onComplete,
  taskId,
  taskName,
}) => {
  const hasExistingTask = Boolean(taskId);
  const { runSafe } = useErrorHandler('TaskGenerationModal');

  // Mode: 'create' (new task from scratch) or 'improve' (modify existing task)
  const [mode, setMode] = useState<'create' | 'improve'>('create');

  // Form state
  const [description, setDescription] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [status, setStatus] = useState<TaskBuildingRunStatus | null>(null);
  const [progressMessages, setProgressMessages] = useState<TaskGenerationProgressMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ task_id: string; cy_name: string } | null>(null);

  // Example prompts state
  const [showExamples, setShowExamples] = useState(true);

  // Alert selector state
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [alertQuery, setAlertQuery] = useState('');

  // Generated script preview
  const [generatedScript, setGeneratedScript] = useState<string | null>(null);

  // Confirmation dialog state
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

  // Polling ref
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressEndRef = useRef<HTMLDivElement>(null);

  // Track if we've reset state for this modal session
  const hasResetRef = useRef(false);

  // Reset form when modal opens
  // This pattern is intentional: we reset state when the modal opens to ensure clean slate.
  // The cascading renders are minimal (single batch) and necessary for the modal pattern.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (isOpen && !hasResetRef.current) {
      hasResetRef.current = true;
      setDescription('');
      setMode('create');
      setIsGenerating(false);
      setStatus(null);
      setProgressMessages([]);
      setError(null);
      setResult(null);
      setShowDiscardConfirm(false);
      setGeneratedScript(null);
      setShowExamples(true);
      setSelectedAlert(null);
      setAlertQuery('');
    } else if (!isOpen) {
      hasResetRef.current = false;
    }
  }, [isOpen]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // Fetch alerts when modal opens
  useEffect(() => {
    const fetchAlerts = async () => {
      if (!isOpen) return;

      setAlertsLoading(true);
      const [response, err] = await runSafe(
        backendApi.getAlerts({ limit: 10, sort: 'created_at', order: 'desc' }),
        'getAlerts',
        { action: 'fetching alerts for context selection' }
      );

      if (!err && response?.alerts) {
        setAlerts(response.alerts);
      }
      setAlertsLoading(false);
    };

    void fetchAlerts();
  }, [isOpen, runSafe]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    progressEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [progressMessages]);

  // Filter alerts based on search query
  const filteredAlerts = useMemo(() => {
    if (!alertQuery) return alerts;
    const query = alertQuery.toLowerCase();
    return alerts.filter(
      (alert) =>
        alert.title.toLowerCase().includes(query) ||
        alert.human_readable_id.toLowerCase().includes(query)
    );
  }, [alerts, alertQuery]);

  // Stop polling helper
  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  // Fetch the generated script for preview
  const fetchGeneratedScript = useCallback(
    async (taskId: string) => {
      const [task, err] = await runSafe(backendApi.getTask(taskId), 'getTask', {
        action: 'fetching generated task script',
        entityId: taskId,
      });

      if (!err && task?.script) {
        setGeneratedScript(String(task.script));
      }
    },
    [runSafe]
  );

  // Extract the expected task name from the last create_task progress message.
  // The backend's result.task_id can be wrong when concurrent task creation occurs,
  // so we use the progress messages to determine which task was actually generated.
  const extractExpectedTaskName = useCallback(
    (messages: TaskGenerationProgressMessage[]): string | null => {
      // Find the last create_task tool call in progress messages
      const createTaskMessages = messages.filter((m) =>
        m.message?.includes('mcp__cy-script-assistant__create_task')
      );

      if (createTaskMessages.length === 0) return null;

      const lastCreateTask = createTaskMessages[createTaskMessages.length - 1];
      const input = lastCreateTask.details?.input as Record<string, unknown> | undefined;
      return typeof input?.name === 'string' ? input.name : null;
    },
    []
  );

  // Resolve the correct task ID by verifying against the expected task name.
  // If result.task_id points to a task with a different name (concurrent creation race),
  // search for the task by the expected name instead.
  const resolveCorrectTaskId = useCallback(
    async (
      resultTaskId: string,
      resultCyName: string,
      progressMessages: TaskGenerationProgressMessage[]
    ): Promise<{ task_id: string; cy_name: string }> => {
      const expectedName = extractExpectedTaskName(progressMessages);

      // If we can't determine the expected name, fall back to result.task_id
      if (!expectedName) {
        return { task_id: resultTaskId, cy_name: resultCyName };
      }

      // Verify the task at result.task_id has the expected name
      const [task, taskErr] = await runSafe(backendApi.getTask(resultTaskId), 'getTask', {
        action: 'verifying generated task ID',
        entityId: resultTaskId,
      });

      if (!taskErr && task?.name === expectedName) {
        // result.task_id is correct
        return { task_id: resultTaskId, cy_name: resultCyName };
      }

      // result.task_id points to wrong task — search by name
      type TaskSearchResult = {
        tasks: Array<{ id: string; name: string; cy_name?: string }>;
        total: number;
      };
      const [searchResult, searchErr] = await runSafe<TaskSearchResult>(
        backendApi.getTasks({
          search: expectedName,
          sort: 'created_at',
          order: 'desc',
          limit: 5,
        }) as Promise<TaskSearchResult>,
        'getTasks',
        { action: 'searching for correct generated task by name' }
      );

      if (!searchErr && searchResult?.tasks && searchResult.tasks.length > 0) {
        // Find exact name match (search may return partial matches)
        const exactMatch = searchResult.tasks.find((t) => t.name === expectedName);
        if (exactMatch) {
          return {
            task_id: exactMatch.id,
            cy_name: exactMatch.cy_name || resultCyName,
          };
        }
      }

      // Could not find correct task — fall back to result.task_id
      return { task_id: resultTaskId, cy_name: resultCyName };
    },
    [runSafe, extractExpectedTaskName]
  );

  // Poll for generation status
  const pollStatus = useCallback(
    async (genId: string) => {
      const [response, err] = await runSafe<TaskBuildingRun>(
        backendApi.getTaskGeneration(genId),
        'getTaskGeneration',
        { action: 'polling task generation status', entityId: genId }
      );

      if (err || !response) {
        setError('Failed to fetch generation status');
        setIsGenerating(false);
        stopPolling();
        return;
      }

      setStatus(response.status);

      // Update progress messages (cast from Record<string,unknown>[] to typed array)
      const messages = response.progress_messages as unknown as
        | TaskGenerationProgressMessage[]
        | undefined;
      if (messages && messages.length > 0) {
        setProgressMessages(messages);
      }

      // Check for completion
      const result = response.result as TaskGenerationResult | null | undefined;
      if (response.status === 'completed') {
        stopPolling();
        setIsGenerating(false);

        if (result?.task_id) {
          // Verify and resolve the correct task ID (guards against concurrent creation race)
          const resolved = await resolveCorrectTaskId(
            result.task_id,
            result.cy_name || 'Generated Task',
            messages || []
          );

          setResult(resolved);

          // Fetch the generated script to show preview
          void fetchGeneratedScript(resolved.task_id);
        } else {
          setError('Task generation completed but no task was created');
        }
      } else if (response.status === 'failed') {
        stopPolling();
        setIsGenerating(false);
        setError(result?.error || 'Task generation failed');
      }
    },
    [runSafe, stopPolling, fetchGeneratedScript, resolveCorrectTaskId]
  );

  // Start generation
  const handleGenerate = async () => {
    if (description.trim().length < MIN_DESCRIPTION_LENGTH) {
      setError(`Description must be at least ${MIN_DESCRIPTION_LENGTH} characters`);
      return;
    }

    setIsGenerating(true);
    setError(null);
    setProgressMessages([]);
    setResult(null);

    const request: { description: string; alert_id?: string; task_id?: string } = {
      description: description.trim(),
    };

    if (selectedAlert) {
      request.alert_id = selectedAlert.alert_id;
    }

    if (mode === 'improve' && taskId) {
      request.task_id = taskId;
    }

    const [response, err] = await runSafe(
      backendApi.createTaskGeneration(request),
      'createTaskGeneration',
      { action: 'starting task generation', entityId: selectedAlert?.alert_id }
    );

    if (err || !response) {
      setError('Failed to start task generation');
      setIsGenerating(false);
      return;
    }

    setStatus(response.status as TaskBuildingRunStatus);

    // Start polling
    pollingRef.current = setInterval(() => {
      void pollStatus(response.id);
    }, 2000);

    // Also poll immediately
    void pollStatus(response.id);
  };

  // Handle using the generated task
  const handleUseTask = () => {
    if (result) {
      onComplete(result.task_id, result.cy_name);
      onClose();
    }
  };

  // Check if we should show discard confirmation
  const shouldConfirmClose = useCallback(() => {
    if (isGenerating) return true;
    if ((description.trim().length > 0 || selectedAlert) && !result) return true;
    return false;
  }, [isGenerating, description, selectedAlert, result]);

  // Handle escape key with confirmation if generating
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || event.key === 'Esc') {
        event.preventDefault();
        event.stopPropagation();

        if (shouldConfirmClose()) {
          setShowDiscardConfirm(true);
        } else {
          onClose();
        }
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape, true);
      return () => document.removeEventListener('keydown', handleEscape, true);
    }
  }, [isOpen, shouldConfirmClose, onClose]);

  const handleSafeClose = () => {
    if (shouldConfirmClose()) {
      setShowDiscardConfirm(true);
    } else {
      onClose();
    }
  };

  const handleConfirmDiscard = () => {
    stopPolling();
    setShowDiscardConfirm(false);
    onClose();
  };

  // Derived state for mode-aware labels
  const isImproveMode = mode === 'improve';
  const showFormInputs = !isGenerating && !result;
  const contentOverflowClass =
    isGenerating && progressMessages.length === 0 ? 'overflow-hidden' : 'overflow-y-auto';

  return (
    <>
      <Dialog open={isOpen} onClose={handleSafeClose} className="relative z-50">
        <div className="fixed inset-0 bg-black/50" aria-hidden="true" />

        <div className="fixed inset-0 flex items-center justify-center p-4">
          <Dialog.Panel className="mx-auto rounded-lg bg-dark-800 p-6 w-full max-w-2xl max-h-[90vh] flex flex-col">
            <ModalHeader mode={mode} taskName={taskName} onClose={handleSafeClose} />

            <div className={`space-y-4 flex-1 min-h-0 ${contentOverflowClass}`}>
              {showFormInputs && hasExistingTask && (
                <ModeSelector mode={mode} taskName={taskName} onModeChange={setMode} />
              )}

              {showFormInputs && (
                <AlertSelector
                  selectedAlert={selectedAlert}
                  onSelectAlert={setSelectedAlert}
                  alertQuery={alertQuery}
                  onAlertQueryChange={setAlertQuery}
                  alertsLoading={alertsLoading}
                  filteredAlerts={filteredAlerts}
                />
              )}

              {showFormInputs && (
                <DescriptionInput
                  mode={mode}
                  description={description}
                  onDescriptionChange={(val) => {
                    setDescription(val);
                    setError(null);
                  }}
                  showExamples={showExamples}
                  onToggleExamples={() => setShowExamples(!showExamples)}
                  onSelectExample={(prompt) => {
                    setDescription(prompt);
                    setShowExamples(false);
                  }}
                />
              )}

              {error && <ErrorBanner error={error} onDismiss={() => setError(null)} />}

              {(isGenerating || result) && (
                <ProgressSection
                  status={status}
                  progressMessages={progressMessages}
                  progressEndRef={progressEndRef}
                  result={result}
                  isImproveMode={isImproveMode}
                  generatedScript={generatedScript}
                />
              )}
            </div>

            <ModalFooter
              result={result}
              isGenerating={isGenerating}
              isImproveMode={isImproveMode}
              canGenerate={description.trim().length >= MIN_DESCRIPTION_LENGTH}
              onClose={handleSafeClose}
              onUseTask={handleUseTask}
              onGenerate={() => void handleGenerate()}
            />
          </Dialog.Panel>
        </div>
      </Dialog>

      <ConfirmDialog
        isOpen={showDiscardConfirm}
        onClose={() => setShowDiscardConfirm(false)}
        onConfirm={handleConfirmDiscard}
        title={isGenerating ? 'Cancel Generation?' : 'Discard Draft?'}
        message={
          isGenerating
            ? 'The task is still being generated. Are you sure you want to cancel?'
            : 'You have unsaved changes. Are you sure you want to exit?'
        }
        confirmLabel={isGenerating ? 'Cancel Generation' : 'Discard'}
        cancelLabel="Keep Editing"
        variant="warning"
      />
    </>
  );
};

// ─── Sub-components ───────────────────────────────────────────────────

const ACTIVE_MODE_CLASS = 'bg-purple-900/30 border-purple-600 text-purple-300';
const INACTIVE_MODE_CLASS =
  'bg-dark-700 border-gray-700 text-gray-400 hover:text-gray-200 hover:border-gray-500';

const ModalHeader: React.FC<{
  mode: 'create' | 'improve';
  taskName?: string | null;
  onClose: () => void;
}> = ({ mode, taskName, onClose }) => (
  <div className="flex justify-between items-start mb-4">
    <div>
      <Dialog.Title className="text-xl font-semibold text-white flex items-center gap-2">
        <SparklesIcon className="h-5 w-5 text-purple-400" />
        AI Task Assistant
      </Dialog.Title>
      <p className="text-gray-400 text-sm mt-1">
        {mode === 'improve'
          ? `Describe what to change about "${taskName || 'this task'}"`
          : 'Describe the task you want to create'}
      </p>
    </div>
    <button onClick={onClose} className="text-gray-400 hover:text-white">
      <XMarkIcon className="w-6 h-6" />
    </button>
  </div>
);

const ModeSelector: React.FC<{
  mode: 'create' | 'improve';
  taskName?: string | null;
  onModeChange: (mode: 'create' | 'improve') => void;
}> = ({ mode, taskName, onModeChange }) => (
  <div className="space-y-3">
    <div className="flex gap-2">
      <button
        type="button"
        onClick={() => onModeChange('create')}
        className={`flex-1 px-3 py-2 text-sm font-medium rounded-sm border transition-colors ${
          mode === 'create' ? ACTIVE_MODE_CLASS : INACTIVE_MODE_CLASS
        }`}
      >
        Create New Task
      </button>
      <button
        type="button"
        onClick={() => onModeChange('improve')}
        className={`flex-1 px-3 py-2 text-sm font-medium rounded-sm border transition-colors ${
          mode === 'improve' ? ACTIVE_MODE_CLASS : INACTIVE_MODE_CLASS
        }`}
      >
        Improve Current Task
      </button>
    </div>
    {mode === 'improve' && (
      <div className="flex items-center gap-2 px-3 py-2 bg-dark-900 border border-gray-700 rounded-md">
        <CodeBracketIcon className="h-4 w-4 text-purple-400 shrink-0" />
        <span className="text-sm text-gray-300 truncate">
          Improving: <span className="text-white font-medium">{taskName}</span>
        </span>
      </div>
    )}
  </div>
);

const AlertSelector: React.FC<{
  selectedAlert: Alert | null;
  onSelectAlert: (alert: Alert | null) => void;
  alertQuery: string;
  onAlertQueryChange: (query: string) => void;
  alertsLoading: boolean;
  filteredAlerts: Alert[];
}> = ({
  selectedAlert,
  onSelectAlert,
  alertQuery,
  onAlertQueryChange,
  alertsLoading,
  filteredAlerts,
}) => (
  <div>
    <label htmlFor="alert-selector" className="block text-sm font-medium text-gray-300 mb-2">
      Select an alert for context (optional)
    </label>
    <Combobox value={selectedAlert} onChange={onSelectAlert}>
      <div className="relative">
        <div className="relative w-full">
          <Combobox.Input
            id="alert-selector"
            className="w-full px-3 py-2 pr-10 border border-gray-600 rounded-md shadow-xs focus:outline-hidden focus:ring-purple-500 focus:border-purple-500 bg-dark-700 text-gray-100 placeholder-gray-500"
            displayValue={(alert: Alert | null) =>
              alert ? `${alert.human_readable_id} - ${alert.title}` : ''
            }
            onChange={(e) => onAlertQueryChange(e.target.value)}
            placeholder={alertsLoading ? 'Loading alerts...' : 'Search alerts by title...'}
          />
          <Combobox.Button className="absolute inset-y-0 right-0 flex items-center pr-2">
            <ChevronUpDownIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
          </Combobox.Button>
        </div>
        <Combobox.Options className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md bg-dark-700 border border-gray-600 py-1 text-base shadow-lg focus:outline-hidden sm:text-sm">
          <Combobox.Option
            value={null}
            className={({ active }) =>
              `relative cursor-pointer select-none py-2 px-3 ${
                active ? 'bg-purple-600 text-white' : 'text-gray-400'
              }`
            }
          >
            <span className="italic">No alert (generate without context)</span>
          </Combobox.Option>
          {filteredAlerts.length === 0 && alertQuery !== '' ? (
            <div className="relative cursor-default select-none py-2 px-3 text-gray-500">
              No alerts found.
            </div>
          ) : (
            filteredAlerts.map((alert) => (
              <Combobox.Option
                key={alert.alert_id}
                value={alert}
                className={({ active }) =>
                  `relative cursor-pointer select-none py-2 px-3 ${
                    active ? 'bg-purple-600 text-white' : 'text-gray-100'
                  }`
                }
              >
                {({ selected, active }) => (
                  <div className="flex flex-col">
                    <div className="flex items-center gap-2">
                      <span
                        className={`inline-flex items-center px-1.5 py-0.5 rounded-sm text-xs font-medium ${getSeverityBadgeClass(alert.severity)}`}
                      >
                        {alert.severity}
                      </span>
                      <span
                        className={`font-mono text-xs ${active ? 'text-purple-200' : 'text-gray-400'}`}
                      >
                        {alert.human_readable_id}
                      </span>
                    </div>
                    <span
                      className={`mt-1 truncate ${selected ? 'font-semibold' : ''} ${active ? 'text-white' : 'text-gray-200'}`}
                    >
                      {alert.title}
                    </span>
                  </div>
                )}
              </Combobox.Option>
            ))
          )}
        </Combobox.Options>
      </div>
    </Combobox>
    {selectedAlert && (
      <div className="mt-2 flex items-start gap-2 p-2 bg-purple-900/20 border border-purple-700 rounded-md">
        <ExclamationTriangleIcon className="h-4 w-4 text-purple-400 mt-0.5 shrink-0" />
        <p className="text-xs text-purple-300">
          The AI will use this alert as context to generate a task tailored to its data structure.
        </p>
      </div>
    )}
  </div>
);

const DescriptionInput: React.FC<{
  mode: 'create' | 'improve';
  description: string;
  onDescriptionChange: (value: string) => void;
  showExamples: boolean;
  onToggleExamples: () => void;
  onSelectExample: (prompt: string) => void;
}> = ({
  mode,
  description,
  onDescriptionChange,
  showExamples,
  onToggleExamples,
  onSelectExample,
}) => (
  <div>
    <label htmlFor="task-description" className="block text-sm font-medium text-gray-300 mb-2">
      {mode === 'improve'
        ? 'Describe what you want to change'
        : 'Describe the task you want to create'}
    </label>
    <textarea
      id="task-description"
      value={description}
      onChange={(e) => onDescriptionChange(e.target.value)}
      className="w-full px-3 py-2 border border-gray-600 rounded-md shadow-xs focus:outline-hidden focus:ring-purple-500 focus:border-purple-500 bg-dark-700 text-gray-100 placeholder-gray-500"
      rows={6}
      placeholder={
        mode === 'improve'
          ? 'Example: Add error handling for when the API returns no results. Also add a retry with exponential backoff for rate-limited requests.'
          : 'Example: Create a task that queries VirusTotal for a file hash and returns the detection ratio, file type, and any associated malware families. The task should handle both MD5 and SHA256 hashes.'
      }
      maxLength={MAX_DESCRIPTION_LENGTH}
    />
    <div className="flex justify-between mt-1">
      <p className="text-xs text-gray-500">
        {mode === 'improve'
          ? 'Be specific about what to change, add, or fix.'
          : 'Be specific about what integrations to use and what data to return.'}
      </p>
      <span className="text-xs text-gray-500">
        {description.length}/{MAX_DESCRIPTION_LENGTH}
      </span>
    </div>
    {mode === 'create' && (
      <div className="mt-4">
        <button
          type="button"
          onClick={onToggleExamples}
          className="flex items-center gap-2 text-sm text-purple-400 hover:text-purple-300"
        >
          <CodeBracketIcon className="h-4 w-4" />
          {showExamples ? 'Hide' : 'Show'} Example Prompts
        </button>
        {showExamples && (
          <div className="mt-3 grid grid-cols-2 gap-2">
            {EXAMPLE_PROMPTS.map((example, index) => (
              <button
                key={index}
                type="button"
                onClick={() => onSelectExample(example.prompt)}
                className="text-left p-3 bg-dark-900 border border-gray-700 rounded-lg hover:border-purple-500 hover:bg-dark-700 transition-colors group"
              >
                <div className="flex items-center gap-2 mb-1">
                  <SparklesIcon className="h-4 w-4 text-purple-400 group-hover:text-purple-300" />
                  <span className="text-sm font-medium text-gray-200 group-hover:text-white">
                    {example.title}
                  </span>
                </div>
                <p className="text-xs text-gray-500 line-clamp-2">
                  {example.prompt.slice(0, 80)}...
                </p>
              </button>
            ))}
          </div>
        )}
      </div>
    )}
  </div>
);

const ErrorBanner: React.FC<{ error: string; onDismiss: () => void }> = ({ error, onDismiss }) => (
  <div className="bg-red-900/20 border border-red-800 rounded-md p-3">
    <div className="flex items-start">
      <ExclamationCircleIcon className="h-5 w-5 text-red-400 mt-0.5 mr-2 shrink-0" />
      <div className="flex-1">
        <p className="text-sm text-red-300">{error}</p>
      </div>
      <button onClick={onDismiss} className="ml-3 text-red-400 hover:text-red-300">
        <XMarkIcon className="h-4 w-4" />
      </button>
    </div>
  </div>
);

const ProgressSection: React.FC<{
  status: TaskBuildingRunStatus | null;
  progressMessages: TaskGenerationProgressMessage[];
  progressEndRef: React.RefObject<HTMLDivElement | null>;
  result: { task_id: string; cy_name: string } | null;
  isImproveMode: boolean;
  generatedScript: string | null;
}> = ({ status, progressMessages, progressEndRef, result, isImproveMode, generatedScript }) => (
  <div className="space-y-3">
    <div className="flex items-center gap-2">
      {getStatusIcon(status)}
      <span className="text-sm font-medium text-gray-200">{getStatusText(status)}</span>
    </div>

    {progressMessages.length > 0 && (
      <div className="bg-dark-900 border border-gray-700 rounded-md p-3 max-h-48 overflow-y-auto">
        <div className="space-y-1.5">
          {progressMessages.map((msg, index) => (
            <div key={index} className="flex items-start gap-2 text-xs">
              <span className="text-gray-500 font-mono shrink-0">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </span>
              <span className={getMessageColor(msg.level)}>{formatProgressMessage(msg)}</span>
            </div>
          ))}
          <div ref={progressEndRef} />
        </div>
      </div>
    )}

    {result && (
      <div className="bg-green-900/20 border border-green-800 rounded-md p-4">
        <div className="flex items-start gap-3">
          <CheckCircleIcon className="h-6 w-6 text-green-400 shrink-0" />
          <div>
            <p className="text-sm font-medium text-green-300">
              {isImproveMode ? 'Task updated successfully!' : 'Task created successfully!'}
            </p>
            <p className="text-xs text-gray-400 mt-1">
              <span className="font-mono">{result.cy_name}</span>
            </p>
          </div>
        </div>
      </div>
    )}

    {generatedScript && (
      <div className="bg-dark-900 border border-gray-700 rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-3 py-2 bg-dark-700 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <CodeBracketIcon className="h-4 w-4 text-green-400" />
            <span className="text-xs font-medium text-gray-300">Generated Cy Script</span>
          </div>
        </div>
        <pre className="p-3 text-xs font-mono text-gray-300 overflow-x-auto max-h-64 overflow-y-auto">
          {generatedScript}
        </pre>
      </div>
    )}
  </div>
);

const ModalFooter: React.FC<{
  result: { task_id: string; cy_name: string } | null;
  isGenerating: boolean;
  isImproveMode: boolean;
  canGenerate: boolean;
  onClose: () => void;
  onUseTask: () => void;
  onGenerate: () => void;
}> = ({ result, isGenerating, isImproveMode, canGenerate, onClose, onUseTask, onGenerate }) => (
  <div className="flex justify-end space-x-3 mt-6 shrink-0">
    <button
      type="button"
      onClick={onClose}
      className="px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-sm text-white text-sm"
      disabled={isGenerating}
    >
      {result ? 'Close' : 'Cancel'}
    </button>

    {result ? (
      <button
        type="button"
        onClick={onUseTask}
        className="px-4 py-2 bg-primary hover:bg-primary-dark rounded-sm text-white text-sm font-medium flex items-center gap-2"
      >
        <SparklesIcon className="h-4 w-4" />
        {isImproveMode ? 'Reload in Editor' : 'Open in Editor'}
      </button>
    ) : (
      <button
        type="button"
        onClick={onGenerate}
        className="px-4 py-2 bg-primary hover:bg-primary-dark rounded-sm text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        disabled={isGenerating || !canGenerate}
      >
        {isGenerating ? (
          <>
            <ArrowPathIcon className="h-4 w-4 animate-spin" />
            {isImproveMode ? 'Improving...' : 'Generating...'}
          </>
        ) : (
          <>
            <SparklesIcon className="h-4 w-4" />
            {isImproveMode ? 'Improve Task' : 'Generate Task'}
          </>
        )}
      </button>
    )}
  </div>
);
