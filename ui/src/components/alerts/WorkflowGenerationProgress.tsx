/* eslint-disable no-undef, sonarjs/cognitive-complexity, sonarjs/function-return-type, sonarjs/no-nested-conditional */
import React, { useEffect, useRef, useState } from 'react';

import {
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
  DocumentTextIcon,
  ListBulletIcon,
  CodeBracketIcon,
  RectangleGroupIcon,
} from '@heroicons/react/24/outline';

import { backendApi } from '../../services/backendApi';
import type {
  WorkflowGeneration,
  WorkflowGenerationStage,
  OrchestrationResults,
  StageMetrics,
} from '../../types/alert';

/**
 * Helper to safely access orchestration_results as OrchestrationResults.
 * The generated type is `{ [key: string]: unknown }` but runtime data has structured fields.
 */
function getOrchResults(generation: WorkflowGeneration): OrchestrationResults | undefined {
  return generation.orchestration_results as OrchestrationResults | undefined;
}

interface WorkflowGenerationProgressProps {
  analysisId: string;
  onComplete?: (workflowId: string) => void;
}

// Stage configuration with icons and labels
const generationStages: Array<{
  key: WorkflowGenerationStage;
  label: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  description: string;
}> = [
  {
    key: 'runbook_generation',
    label: 'Generating Runbook',
    icon: DocumentTextIcon,
    description: 'Creating investigation procedures',
  },
  {
    key: 'task_proposals',
    label: 'Proposing Tasks',
    icon: ListBulletIcon,
    description: 'Analyzing required tasks',
  },
  {
    key: 'task_building',
    label: 'Building Tasks',
    icon: CodeBracketIcon,
    description: 'Creating task implementations',
  },
  {
    key: 'workflow_assembly',
    label: 'Assembling Workflow',
    icon: RectangleGroupIcon,
    description: 'Composing final workflow',
  },
];

const formatDuration = (ms: number): string => {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
  } else if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  } else if (seconds > 0) {
    return `${seconds}s`;
  } else {
    return `${ms}ms`;
  }
};

export const WorkflowGenerationProgress: React.FC<WorkflowGenerationProgressProps> = ({
  analysisId,
  onComplete,
}) => {
  const [generation, setGeneration] = useState<WorkflowGeneration | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Keep onComplete in a ref so the effect doesn't restart when the parent re-renders
  // with a new inline function reference
  const onCompleteRef = useRef(onComplete);
  useEffect(() => {
    onCompleteRef.current = onComplete;
  });

  // Keep generation in a ref for the polling interval to avoid stale closures
  // without needing generation?.status in the effect deps (which would cause re-runs)
  const generationRef = useRef<WorkflowGeneration | null>(null);

  useEffect(() => {
    let isMounted = true;
    let pollingInterval: NodeJS.Timeout | null = null;

    const fetchGeneration = async () => {
      try {
        const response = await backendApi.listWorkflowGenerations({
          triggering_alert_analysis_id: analysisId,
        });

        if (!isMounted) return;

        if (response.workflow_generations && response.workflow_generations.length > 0) {
          const latestGeneration = response.workflow_generations[0];
          generationRef.current = latestGeneration;
          setGeneration(latestGeneration);
          setError(null);

          // If completed, notify parent and stop polling
          if (latestGeneration.status === 'completed' && latestGeneration.workflow_id) {
            onCompleteRef.current?.(latestGeneration.workflow_id);
            if (pollingInterval) {
              clearInterval(pollingInterval);
            }
          }

          // If failed, stop polling
          if (latestGeneration.status === 'failed') {
            if (pollingInterval) {
              clearInterval(pollingInterval);
            }
          }
        }
        setLoading(false);
      } catch (err) {
        if (!isMounted) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch workflow generation');
        setLoading(false);
      }
    };

    // Initial fetch
    void fetchGeneration();

    // Poll every 5 seconds while running — use ref to get current status without stale closure
    pollingInterval = setInterval(() => {
      const currentGen = generationRef.current;
      if (currentGen?.status === 'running' || !currentGen) {
        void fetchGeneration();
      }
    }, 5000);

    return () => {
      isMounted = false;
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [analysisId]); // Only restarts when analysisId changes; refs used for generation and onComplete

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <ArrowPathIcon className="h-5 w-5 text-blue-400 animate-spin" />;
      case 'completed':
        return <CheckCircleIcon className="h-5 w-5 text-green-400" />;
      case 'failed':
        return <XCircleIcon className="h-5 w-5 text-red-400" />;
      default:
        return <ClockIcon className="h-5 w-5 text-gray-400" />;
    }
  };

  const getStageStatus = (stage: WorkflowGenerationStage): 'completed' | 'running' | 'pending' => {
    if (!generation) return 'pending';

    const stageIndex = generationStages.findIndex((s) => s.key === stage);

    // Check phase data for more accurate status
    const phaseData = generation.progress?.phases?.find((p) => p.stage === stage);

    // Also check metrics.stages as alternative source (completed stages have duration)
    const orchResults = getOrchResults(generation);
    const metricsStage = orchResults?.metrics?.stages?.find((s: StageMetrics) => s.stage === stage);

    // Check if any later stage has started (which means this stage must be completed)
    const laterStageStarted = generationStages.some((s, idx) => {
      if (idx <= stageIndex) return false;
      const laterPhaseData = generation.progress?.phases?.find((p) => p.stage === s.key);
      return (
        laterPhaseData?.started_at ||
        laterPhaseData?.status === 'in_progress' ||
        laterPhaseData?.status === 'completed'
      );
    });

    if (generation.status === 'completed') {
      return 'completed';
    }

    // Check the phase's own status field first (most accurate)
    if (phaseData?.status === 'completed') {
      return 'completed';
    }

    if (phaseData?.status === 'in_progress') {
      return 'running';
    }

    // Fallback: If phase has completed_at, it's completed
    if (phaseData?.completed_at) {
      return 'completed';
    }

    // Fallback: If phase has started_at but no completed_at, it's running
    if (phaseData?.started_at && !phaseData?.completed_at) {
      return 'running';
    }

    // Check metrics - if stage exists in metrics, it's completed
    if (metricsStage) {
      return 'completed';
    }

    // If any later stage has started, this one must be completed
    if (laterStageStarted) {
      return 'completed';
    }

    return 'pending';
  };

  if (loading && !generation) {
    return (
      <div className="bg-gray-800/50 border border-blue-700/50 rounded-lg p-4">
        <div className="flex items-center justify-center">
          <ArrowPathIcon className="h-5 w-5 text-blue-400 animate-spin mr-2" />
          <span className="text-sm text-gray-300">Loading workflow generation...</span>
        </div>
      </div>
    );
  }

  if (error && !generation) {
    return (
      <div className="bg-gray-800/50 border border-red-700/50 rounded-lg p-4">
        <div className="flex items-center">
          <XCircleIcon className="h-5 w-5 text-red-400 mr-2" />
          <span className="text-sm text-red-300">{error}</span>
        </div>
      </div>
    );
  }

  if (!generation) {
    return null;
  }

  return (
    <div className="bg-gray-800/50 border border-blue-700/50 rounded-lg p-4 mt-4">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <h4 className="text-sm font-medium text-blue-300 flex items-center gap-2">
            <RectangleGroupIcon className="h-4 w-4" />
            Workflow Generation
          </h4>
          <p className="text-xs text-gray-400 mt-1">Creating new workflow for this alert type</p>
        </div>
        <div className="flex items-center gap-2">
          {getStatusIcon(generation.status)}
          <span className="text-xs text-gray-400 capitalize">{generation.status}</span>
        </div>
      </div>

      {/* Progress stages */}
      <div className="space-y-2">
        {generationStages.map((stage) => {
          const stageStatus = getStageStatus(stage.key);
          const isCompleted = stageStatus === 'completed';
          const isRunning = stageStatus === 'running';
          const StageIcon = stage.icon;

          return (
            <div
              key={stage.key}
              className={`flex items-start gap-3 p-2 rounded-md transition-all duration-300 ${
                isRunning ? 'bg-blue-900/20 border border-blue-700/30' : ''
              }`}
            >
              {/* Stage indicator */}
              <div className="flex items-center justify-center w-6 h-6 shrink-0 mt-0.5">
                {isCompleted ? (
                  <CheckCircleIcon className="h-5 w-5 text-green-400" />
                ) : isRunning ? (
                  <div className="w-3 h-3 rounded-full bg-blue-400 animate-pulse" />
                ) : (
                  <div className="w-3 h-3 rounded-full border-2 border-gray-500 bg-gray-700" />
                )}
              </div>

              {/* Stage content */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <StageIcon
                    className={`h-4 w-4 ${
                      isCompleted ? 'text-green-400' : isRunning ? 'text-blue-400' : 'text-gray-500'
                    }`}
                  />
                  <span
                    className={`text-sm font-medium ${
                      isCompleted ? 'text-green-400' : isRunning ? 'text-blue-300' : 'text-gray-500'
                    }`}
                  >
                    {stage.label}
                  </span>
                </div>
                <p className={`text-xs mt-0.5 ${isRunning ? 'text-gray-300' : 'text-gray-400'}`}>
                  {stage.description}
                </p>

                {/* Timing information */}
                {(() => {
                  const phaseData = generation.progress?.phases?.find((p) => p.stage === stage.key);
                  const stageOrchResults = getOrchResults(generation);
                  const metricsStage = stageOrchResults?.metrics?.stages?.find(
                    (s: StageMetrics) => s.stage === stage.key
                  );

                  // First check progress.phases for timing
                  if (phaseData && phaseData.started_at) {
                    const duration = phaseData.completed_at
                      ? new Date(phaseData.completed_at).getTime() -
                        new Date(phaseData.started_at).getTime()
                      : Date.now() - new Date(phaseData.started_at).getTime();
                    const durationStr = formatDuration(duration);
                    return (
                      <div className="text-xs text-gray-500 mt-1">
                        <span>{durationStr}</span>
                      </div>
                    );
                  }

                  // Fallback: check metrics.stages for duration_ms
                  if (metricsStage && metricsStage.duration_ms) {
                    const durationStr = formatDuration(metricsStage.duration_ms);
                    return (
                      <div className="text-xs text-gray-500 mt-1">
                        <span>{durationStr}</span>
                      </div>
                    );
                  }

                  return null;
                })()}
              </div>

              {/* Status indicator */}
              {isRunning && (
                <span className="text-xs text-blue-400 animate-pulse shrink-0">Processing...</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Error message */}
      {(() => {
        const orchErr = getOrchResults(generation);
        return orchErr?.error ? (
          <div className="mt-3 p-2 bg-red-900/30 border border-red-700 rounded-sm text-sm text-red-300">
            <p className="font-medium">Generation Error:</p>
            <p className="text-xs mt-1">{orchErr.error.message}</p>
          </div>
        ) : null;
      })()}

      {/* Metrics (if available and completed) */}
      {(() => {
        const orchMetrics = getOrchResults(generation);
        return generation.status === 'completed' && orchMetrics?.metrics ? (
          <div className="mt-3 pt-3 border-t border-gray-700">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-gray-400">Total Cost:</span>
                <span className="ml-2 text-gray-200 font-medium">
                  ${orchMetrics.metrics.total_cost_usd.toFixed(2)}
                </span>
              </div>
              <div>
                <span className="text-gray-400">Stages:</span>
                <span className="ml-2 text-gray-200 font-medium">
                  {orchMetrics.metrics.stages.length}
                </span>
              </div>
            </div>
          </div>
        ) : null;
      })()}
    </div>
  );
};
