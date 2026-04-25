/* eslint-disable sonarjs/no-nested-conditional, sonarjs/cognitive-complexity */
import React from 'react';

import {
  ArrowPathIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';

import type { AnalysisProgress } from '../../types/alert';

import { WorkflowGenerationProgress } from './WorkflowGenerationProgress';

interface AnalysisProgressDisplayProps {
  progress: AnalysisProgress;
  onClose?: () => void;
  wasWorkflowGenerated?: boolean;
  analysisId?: string;
}

export const AnalysisProgressDisplay: React.FC<AnalysisProgressDisplayProps> = ({
  progress,
  onClose,
  wasWorkflowGenerated,
  analysisId,
}) => {
  const analysisSteps = [
    { key: 'pre_triage', label: 'Pre-triage', order: 1 },
    {
      key: 'workflow_builder',
      label: wasWorkflowGenerated ? 'Workflow Builder (Generated)' : 'Workflow Builder (Retrieved)',
      order: 2,
    },
    { key: 'workflow_execution', label: 'Workflow Execution', order: 3 },
    { key: 'final_disposition_update', label: 'Final Disposition', order: 4 },
  ];

  const getCurrentStepIndex = () => {
    if (!progress.current_step) return -1;
    const step = analysisSteps.find(
      (s) =>
        s.key === progress.current_step ||
        s.label.toLowerCase().replaceAll(/[\s-_]/g, '') ===
          progress.current_step?.toLowerCase().replaceAll(/[\s-_]/g, '')
    );
    return step ? step.order - 1 : -1;
  };

  const currentStepIndex = getCurrentStepIndex();

  const actualCompletedSteps =
    progress.status === 'completed'
      ? progress.total_steps
      : currentStepIndex >= 0
        ? currentStepIndex
        : progress.completed_steps;
  const progressPercentage = (actualCompletedSteps / progress.total_steps) * 100;

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending':
        return <ClockIcon className="h-5 w-5 text-gray-400" />;
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

  const getStepStatus = (stepKey: string, stepIndex: number): string => {
    if (progress.status === 'completed') return 'completed';
    if (progress.steps_detail && progress.steps_detail[stepKey]?.completed) return 'completed';
    if (
      progress.progress_details &&
      progress.progress_details[stepKey as keyof typeof progress.progress_details]
    ) {
      const status =
        progress.progress_details[stepKey as keyof typeof progress.progress_details].status;
      if (status.toLowerCase() === 'completed') return 'completed';
    }
    if (currentStepIndex >= 0 && stepIndex < currentStepIndex) return 'completed';
    return 'pending';
  };

  const formatDuration = (ms: number): string => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    if (hours > 0) return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    if (seconds > 0) return `${seconds}s`;
    return `${ms}ms`;
  };

  const getStepTiming = (stepKey: string) => {
    const stepDetail = progress.steps_detail?.[stepKey];
    if (!stepDetail?.started_at || !stepDetail.completed_at) return null;
    const duration =
      new Date(stepDetail.completed_at).getTime() - new Date(stepDetail.started_at).getTime();
    return { duration: formatDuration(duration) };
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <h3 className="text-lg font-medium text-gray-200">Analysis Progress</h3>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            {getStatusIcon(progress.status)}
            <span className="text-sm text-gray-400 capitalize">{progress.status}</span>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-200 transition-colors p-1 -m-1"
              aria-label="Close progress"
            >
              <XCircleIcon className="h-5 w-5" />
            </button>
          )}
        </div>
      </div>

      <div className="mb-3">
        <div className="flex justify-between text-sm text-gray-400 mb-1">
          <span>
            Step {actualCompletedSteps} of {progress.total_steps}
          </span>
          <span>{Math.round(progressPercentage)}%</span>
        </div>
        <div className="w-full bg-gray-700 rounded-full h-2">
          <div
            className="bg-primary rounded-full h-2 transition-all duration-500"
            style={{ width: `${progressPercentage}%` }}
          />
        </div>
      </div>

      {progress.current_step && progress.status !== 'completed' && progress.status !== 'failed' && (
        <div className="text-sm text-gray-300">
          <span className="font-medium">Current:</span> {progress.current_step}
        </div>
      )}

      {progress.error && (
        <div className="mt-3 p-2 bg-red-900/30 border border-red-700 rounded-sm text-sm text-red-300">
          {progress.error}
        </div>
      )}

      <div className="mt-4 space-y-2">
        <h4 className="text-sm font-medium text-gray-300">Analysis Steps:</h4>
        {analysisSteps.map((step, index) => {
          const stepStatus = getStepStatus(step.key, index);
          const isCurrentStep = index === currentStepIndex;
          const isCompleted = stepStatus === 'completed';
          const isRunning = isCurrentStep && progress.status === 'running';
          const isPausedAtWorkflowBuilder =
            step.key === 'workflow_builder' &&
            isCurrentStep &&
            (progress.status === 'paused' ||
              (progress.status === 'running' && progress.current_step === 'workflow_builder'));

          return (
            <React.Fragment key={step.key}>
              <div
                className={`flex items-start gap-3 p-2 rounded-md transition-all duration-300 ${
                  isRunning || isPausedAtWorkflowBuilder
                    ? 'bg-gray-700/50 border border-primary/50'
                    : ''
                }`}
              >
                <div className="flex items-center justify-center w-6 h-6 shrink-0 mt-0.5">
                  {isCompleted ? (
                    <CheckCircleIcon className="h-6 w-6 text-green-400" />
                  ) : isRunning || isPausedAtWorkflowBuilder ? (
                    <div className="relative">
                      <div className="absolute inset-0 bg-primary rounded-full animate-ping opacity-75" />
                      <div className="relative w-3 h-3 bg-primary rounded-full animate-pulse" />
                    </div>
                  ) : (
                    <div
                      className={`w-3 h-3 rounded-full border-2 ${
                        index < currentStepIndex
                          ? 'border-primary bg-primary/20'
                          : 'border-gray-500 bg-gray-700'
                      }`}
                    />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div
                    className={`text-sm ${
                      isCompleted
                        ? 'text-green-400 font-medium'
                        : isRunning || isPausedAtWorkflowBuilder
                          ? 'text-primary font-medium'
                          : index < currentStepIndex
                            ? 'text-gray-300'
                            : 'text-gray-500'
                    }`}
                  >
                    {step.label}
                  </div>
                  {(() => {
                    const timing = getStepTiming(step.key);
                    if (timing) {
                      return (
                        <div className="text-xs text-gray-400 mt-1">
                          <span>{timing.duration}</span>
                        </div>
                      );
                    }
                    return null;
                  })()}
                </div>

                {(isRunning || isPausedAtWorkflowBuilder) && (
                  <span className="text-xs text-primary animate-pulse shrink-0">
                    {isPausedAtWorkflowBuilder ? 'Building Workflow...' : 'Processing...'}
                  </span>
                )}
              </div>

              {step.key === 'workflow_builder' && wasWorkflowGenerated && analysisId && (
                <div className="ml-9">
                  <WorkflowGenerationProgress
                    analysisId={analysisId}
                    onComplete={(_workflowId) => {
                      // Workflow generation completed
                    }}
                  />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
