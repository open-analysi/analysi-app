import React, { useState, useCallback, useEffect } from 'react';

import {
  ChevronDownIcon,
  ChevronRightIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  ArrowTopRightOnSquareIcon,
  SparklesIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { TaskRun } from '../../types/taskRun';

interface FindingCardProps {
  taskRun: TaskRun;
  isExpanded: boolean;
  onToggle: () => void;
}

// Fields to exclude from enrichment display (metadata, not findings)
const EXCLUDED_ENRICHMENT_FIELDS = new Set([
  'trid',
  'cy_name',
  'status',
  'has_enrichment',
  'task_run_id',
  'task_id',
  'ai_analysis_title', // Displayed in header, not in findings list
]);

// Get the AI title field based on task name
const getAiTitleFromEnrichment = (
  enrichmentData: Record<string, unknown>,
  taskName: string | undefined
): string | null => {
  if (!taskName) return null;

  // Special handling for disposition task - try multiple possible field names
  // Use includes() for flexible matching (handles whitespace/casing variations)
  if (taskName.includes('Disposition Determination')) {
    // Try different field names that might contain the disposition
    const possibleFields = [
      'disposition',
      'alert_disposition',
      'disposition_category',
      'disposition_display_name',
    ];
    for (const field of possibleFields) {
      const value = enrichmentData[field];
      if (value && typeof value === 'string') {
        return value;
      }
    }
    return null;
  }

  // Special handling for summary task
  if (taskName.includes('Summary Generation')) {
    const summary = enrichmentData.summary;
    if (summary && typeof summary === 'string') {
      return summary;
    }
    return null;
  }

  // Default: use ai_analysis_title
  const aiTitle = enrichmentData.ai_analysis_title;
  if (aiTitle && typeof aiTitle === 'string') {
    return aiTitle;
  }

  return null;
};

// Helper to format value for display
// eslint-disable-next-line sonarjs/cognitive-complexity, sonarjs/function-return-type
const formatValue = (value: unknown): React.ReactNode => {
  if (value === null || value === undefined) {
    return <span className="text-gray-500 italic">N/A</span>;
  }

  if (typeof value === 'boolean') {
    return value ? (
      <span className="text-green-400">true</span>
    ) : (
      <span className="text-red-400">false</span>
    );
  }

  if (typeof value === 'number') {
    return <span className="text-blue-400">{value}</span>;
  }

  if (typeof value === 'string') {
    // Check if it's a long string (show 200 chars with expand hint)
    if (value.length > 200) {
      return (
        <span className="text-gray-200 wrap-break-word group cursor-help" title={value}>
          {value.slice(0, 200)}...
          <span className="ml-1 text-gray-500 text-xs inline-flex items-center">
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
              />
            </svg>
          </span>
        </span>
      );
    }
    return <span className="text-gray-200">{value}</span>;
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-gray-500 italic">Empty array</span>;
    }
    return (
      <span className="text-purple-400">
        [{value.length} item{value.length !== 1 ? 's' : ''}]
      </span>
    );
  }

  if (typeof value === 'object') {
    const keys = Object.keys(value);
    if (keys.length === 0) {
      return <span className="text-gray-500 italic">Empty object</span>;
    }
    return <span className="text-yellow-400">{'{...}'}</span>;
  }

  // eslint-disable-next-line @typescript-eslint/no-base-to-string
  return <span className="text-gray-200">{String(value)}</span>;
};

// Component to render expandable array or object

const ExpandableValue: React.FC<{ value: unknown; label: string }> = ({ value }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-gray-500 italic">Empty array</span>;
    }

    return (
      <div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-1 text-purple-400 hover:text-purple-300 transition-colors"
        >
          {isExpanded ? (
            <ChevronDownIcon className="h-3 w-3" />
          ) : (
            <ChevronRightIcon className="h-3 w-3" />
          )}
          [{value.length} item{value.length !== 1 ? 's' : ''}]
        </button>
        {isExpanded && (
          <div className="mt-2 ml-4 space-y-1">
            {value.map((item, index) => (
              <div key={index} className="text-sm text-gray-300">
                <span className="text-gray-500">{index}:</span>{' '}
                {typeof item === 'object' ? (
                  <pre className="inline text-xs bg-dark-900 px-2 py-1 rounded-sm">
                    {JSON.stringify(item, null, 2)}
                  </pre>
                ) : (
                  formatValue(item)
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value);
    if (entries.length === 0) {
      return <span className="text-gray-500 italic">Empty object</span>;
    }

    return (
      <div>
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-1 text-yellow-400 hover:text-yellow-300 transition-colors"
        >
          {isExpanded ? (
            <ChevronDownIcon className="h-3 w-3" />
          ) : (
            <ChevronRightIcon className="h-3 w-3" />
          )}
          {'{'}
          {entries.length} field{entries.length !== 1 ? 's' : ''}
          {'}'}
        </button>
        {isExpanded && (
          <div className="mt-2 ml-4 space-y-1 border-l border-gray-700 pl-3">
            {entries.map(([key, val]) => (
              <div key={key} className="text-sm">
                <span className="text-gray-400">{key}:</span>{' '}
                {typeof val === 'object' && val !== null ? (
                  <ExpandableValue value={val as unknown} label={key} />
                ) : (
                  formatValue(val)
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return <>{formatValue(value)}</>;
};

export const FindingCard: React.FC<FindingCardProps> = ({ taskRun, isExpanded, onToggle }) => {
  const navigate = useNavigate();
  const { runSafe } = useErrorHandler('FindingCard');
  const [enrichment, setEnrichment] = useState<Record<string, unknown> | null>(null);
  const [aiTitle, setAiTitle] = useState<string | null>(null);
  const [taskDescription, setTaskDescription] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  // Fetch enrichment data for task run
  // eslint-disable-next-line sonarjs/cognitive-complexity
  const fetchEnrichment = useCallback(async () => {
    if (hasFetched || loading) return;

    // Try to extract enrichment from output_location first (no extra API call needed).
    // Each task run's output contains accumulated enrichments; the last key is this
    // task's specific contribution.
    if (taskRun.output_location) {
      try {
        const output = JSON.parse(taskRun.output_location) as Record<string, unknown>;
        const enrichments = output.enrichments as Record<string, unknown> | undefined;
        if (enrichments && typeof enrichments === 'object') {
          const keys = Object.keys(enrichments);
          if (keys.length > 0) {
            const taskEnrichment = enrichments[keys[keys.length - 1]] as Record<string, unknown>;
            setEnrichment({ enrichment: taskEnrichment });
            const title = getAiTitleFromEnrichment(taskEnrichment, taskRun.task_name);
            if (title) setAiTitle(title);
            setHasFetched(true);
            return;
          }
        }
      } catch {
        // Fall through to API call
      }
    }

    // Fallback: call the enrichment API endpoint
    setLoading(true);
    setError(null);

    const [data, fetchError] = await runSafe(
      backendApi.getTaskRunEnrichment(taskRun.id),
      'fetchEnrichment',
      { action: 'fetching task enrichment', entityId: taskRun.id }
    );

    if (fetchError) {
      setError('Failed to load findings');
    } else if (data) {
      setEnrichment(data);
      // Extract AI title from enrichment data based on task type
      const enrichmentData = data.enrichment as Record<string, unknown> | undefined;
      if (enrichmentData) {
        const title = getAiTitleFromEnrichment(enrichmentData, taskRun.task_name);
        if (title) {
          setAiTitle(title);
        }
      }
    }

    setLoading(false);
    setHasFetched(true);
  }, [taskRun.id, taskRun.task_name, taskRun.output_location, runSafe, hasFetched, loading]);

  // Fetch task description on mount if task_id exists
  useEffect(() => {
    const fetchTaskDescription = async () => {
      if (!taskRun.task_id) return;

      const [taskData] = await runSafe(backendApi.getTask(taskRun.task_id), 'fetchTask', {
        action: 'fetching task details',
        entityId: taskRun.task_id,
      });

      if (taskData) {
        if (taskData.description) {
          setTaskDescription(taskData.description);
        }
      }
    };

    void fetchTaskDescription();
  }, [taskRun.task_id, runSafe]);

  // Pre-fetch enrichment on mount for succeeded tasks to get the AI title
  useEffect(() => {
    if (taskRun.status === 'completed' && !hasFetched) {
      void fetchEnrichment();
    }
    // Only run once on mount for the initial status
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Track previous expanded state to detect external expansion (e.g., via Expand All)
  // The fetchEnrichment call is intentional here - we need to trigger the fetch when
  // isExpanded changes from parent (e.g., via "Expand All" button)
  const prevExpandedRef = React.useRef(isExpanded);
  useEffect(() => {
    // Only fetch if expanded changed from false to true (external trigger) and hasn't fetched yet
    if (isExpanded && !prevExpandedRef.current && !hasFetched && taskRun.status === 'completed') {
      void fetchEnrichment();
    }
    prevExpandedRef.current = isExpanded;
  }, [isExpanded, hasFetched, taskRun.status, fetchEnrichment]);

  const handleToggle = () => {
    // Fetch enrichment on first expand via click
    if (!isExpanded && !hasFetched && taskRun.status === 'completed') {
      void fetchEnrichment();
    }
    onToggle();
  };

  const handleOpenInWorkbench = (e: React.MouseEvent) => {
    e.stopPropagation(); // Don't trigger card toggle

    // Parse input data for workbench
    let inputData = '';
    try {
      if (taskRun.input_location || taskRun.input) {
        const inputStr = taskRun.input_location || taskRun.input;
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        const parsed: Record<string, unknown> =
          typeof inputStr === 'string' ? JSON.parse(inputStr) : inputStr;

        const actualInput: unknown = parsed.input ?? parsed;
        inputData = JSON.stringify(actualInput, undefined, 2);
      }
    } catch {
      inputData = taskRun.input_location || taskRun.input || '{}';
    }

    const params = new URLSearchParams();
    if (taskRun.task_id) params.set('taskId', taskRun.task_id);
    params.set('taskRunId', taskRun.id);

    void navigate(`/workbench?${params.toString()}`, {
      state: {
        inputData: inputData,
        cyScript: taskRun.cy_script,
        isAdHoc: !!taskRun.cy_script && !taskRun.task_id,
      },
    });
  };

  const getStatusIcon = () => {
    switch (taskRun.status) {
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-green-400" />;
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-400" />;
      case 'running':
        return <ArrowPathIcon className="h-5 w-5 text-blue-400 animate-spin" />;
      case 'pending':
        return <ClockIcon className="h-5 w-5 text-yellow-400" />;
      default:
        return null;
    }
  };

  const getStatusBadge = () => {
    const baseClasses = 'px-2 py-0.5 text-xs font-medium rounded-full';
    switch (taskRun.status) {
      case 'completed':
        return `${baseClasses} bg-green-800 text-green-200`;
      case 'failed':
        return `${baseClasses} bg-red-800 text-red-200`;
      case 'running':
        return `${baseClasses} bg-blue-800 text-blue-200`;
      case 'pending':
        return `${baseClasses} bg-yellow-800 text-yellow-200`;
      default:
        return `${baseClasses} bg-gray-700 text-gray-200`;
    }
  };

  const canExpand = taskRun.status === 'completed' || taskRun.status === 'failed';

  // Extract the actual enrichment data (unwrap from 'enrichment' field if present)
  const getEnrichmentData = (): Record<string, unknown> | null => {
    if (!enrichment) return null;

    // If the response has an 'enrichment' field, use its contents directly
    if ('enrichment' in enrichment && typeof enrichment.enrichment === 'object') {
      return enrichment.enrichment as Record<string, unknown>;
    }

    // Otherwise filter out metadata fields and use remaining fields
    const filtered: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(enrichment)) {
      if (!EXCLUDED_ENRICHMENT_FIELDS.has(key)) {
        filtered[key] = value;
      }
    }
    return Object.keys(filtered).length > 0 ? filtered : null;
  };

  // Render the findings content
  const renderFindings = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-6 text-gray-400">
          <ArrowPathIcon className="h-5 w-5 animate-spin mr-2" />
          <span>Loading findings...</span>
        </div>
      );
    }

    if (error) {
      return (
        <div className="flex items-center justify-center py-6 text-red-400">
          <ExclamationTriangleIcon className="h-5 w-5 mr-2" />
          <span>{error}</span>
          <button
            onClick={() => {
              setHasFetched(false);
              void fetchEnrichment();
            }}
            className="ml-3 text-sm text-primary hover:text-primary/80 underline"
          >
            Retry
          </button>
        </div>
      );
    }

    if (taskRun.status === 'failed') {
      return (
        <div className="py-4">
          <div className="flex items-start gap-2 text-red-400">
            <ExclamationTriangleIcon className="h-5 w-5 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Task Failed</p>
              {taskRun.error && <p className="text-sm text-red-300 mt-1">{taskRun.error}</p>}
            </div>
          </div>
        </div>
      );
    }

    const enrichmentData = getEnrichmentData();

    if (!enrichmentData || Object.keys(enrichmentData).length === 0) {
      return (
        <div className="py-6 text-center text-gray-400">
          <p>No findings available</p>
        </div>
      );
    }

    // Render enrichment data as key-value pairs directly
    return (
      <div className="divide-y divide-gray-700">
        {Object.entries(enrichmentData).map(([key, value]) => (
          <div key={key} className="py-3 flex">
            <div className="w-1/3 text-sm font-medium text-gray-400 pr-4">{key}</div>
            <div className="w-2/3 text-sm">
              {typeof value === 'object' && value !== null ? (
                <ExpandableValue value={value} label={key} />
              ) : (
                formatValue(value)
              )}
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="bg-dark-800 border border-gray-700 rounded-lg overflow-hidden">
      {/* Card Header */}
      <button
        onClick={handleToggle}
        disabled={!canExpand}
        className={`w-full px-4 py-3 flex items-center justify-between text-left transition-colors ${
          canExpand ? 'hover:bg-dark-700 cursor-pointer' : 'cursor-default'
        }`}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {canExpand && isExpanded && (
            <ChevronDownIcon className="h-5 w-5 text-gray-400 shrink-0" />
          )}
          {canExpand && !isExpanded && (
            <ChevronRightIcon className="h-5 w-5 text-gray-400 shrink-0" />
          )}
          {!canExpand && <div className="w-5" />}

          {getStatusIcon()}

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-medium text-gray-200 truncate">
                {taskRun.task_name || 'Unnamed Task'}
              </h3>
              {aiTitle && (
                <>
                  <SparklesIcon className="h-4 w-4 text-purple-400 shrink-0" />
                  <ArrowRightIcon className="h-3.5 w-3.5 text-gray-500 shrink-0" />
                  <span className="text-sm text-purple-300 line-clamp-1">{aiTitle}</span>
                </>
              )}
            </div>
            {!aiTitle && taskDescription && (
              <p className="text-xs text-gray-400 truncate mt-0.5">{taskDescription}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 ml-4 shrink-0">
          {taskRun.task_id && (
            <button
              onClick={handleOpenInWorkbench}
              className="flex items-center gap-1 px-2 py-1 text-xs text-primary hover:text-primary/80 hover:bg-dark-600 rounded-sm transition-colors"
              title="Open in Workbench"
            >
              <ArrowTopRightOnSquareIcon className="h-3.5 w-3.5" />
              <span>Workbench</span>
            </button>
          )}
          <span className={getStatusBadge()}>
            {taskRun.status.charAt(0).toUpperCase() + taskRun.status.slice(1)}
          </span>
        </div>
      </button>

      {/* Expanded Content */}
      {isExpanded && canExpand && (
        <div className="border-t border-gray-700 px-4 bg-dark-900/50">{renderFindings()}</div>
      )}
    </div>
  );
};
