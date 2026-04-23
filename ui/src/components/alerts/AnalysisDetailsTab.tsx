/* eslint-disable sonarjs/no-nested-conditional, sonarjs/no-duplicate-string */
import React, { useEffect, useState, useCallback } from 'react';

import { ArrowPathIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import moment from 'moment-timezone';
import { JSONTree } from 'react-json-tree';

import useErrorHandler from '../../hooks/useErrorHandler';
import { useUrlState } from '../../hooks/useUrlState';
import { backendApi } from '../../services/backendApi';
import { useTimezoneStore } from '../../store/timezoneStore';
import {
  AlertAnalysis,
  Alert,
  AnalysisProgress,
  CurrentAnalysis,
  WorkflowGeneration,
  OrchestrationResults,
} from '../../types/alert';
import { Artifact } from '../../types/artifact';
import { TaskRun } from '../../types/taskRun';
import { Workflow, WorkflowRun } from '../../types/workflow';
import { formatDuration } from '../../utils/formatUtils';
import { ArtifactList } from '../common/ArtifactList';
import { TaskRunList } from '../common/TaskRunList';
import WorkflowExecutionReaflow from '../workflows/WorkflowExecutionReaflow';

import { AnalysisProgressDisplay } from './AnalysisProgressDisplay';
import { AnalysisRunSelector } from './AnalysisRunSelector';

/**
 * Helper to safely access orchestration_results as OrchestrationResults.
 * The generated type is `{ [key: string]: unknown }` but runtime data has structured fields.
 */
function getOrchResults(generation: WorkflowGeneration): OrchestrationResults | undefined {
  return generation.orchestration_results as OrchestrationResults | undefined;
}

interface AnalysisDetailsTabProps {
  alertId: string;
  alertAnalyses: AlertAnalysis[];
  currentAnalysis?: CurrentAnalysis | null;
  alert?: Alert;
  onAnalyze?: () => void;
  analysisProgress?: AnalysisProgress | null;
  wasWorkflowGenerated?: boolean;
  analysisId?: string;
}

export const AnalysisDetailsTab: React.FC<AnalysisDetailsTabProps> = ({
  alertId: _alertId,
  alertAnalyses,
  currentAnalysis: _currentAnalysis,
  alert,
  onAnalyze,
  analysisProgress,
  wasWorkflowGenerated,
  analysisId,
}) => {
  const { timezone } = useTimezoneStore();
  const { runSafe } = useErrorHandler('AnalysisDetailsTab');

  // URL state for selected analysis
  const [selectedAnalysisId, setSelectedAnalysisId] = useUrlState<string>('analysis', '');

  // Sub-tab state
  type SubTab = 'pipeline' | 'workflow' | 'tasks' | 'artifacts' | 'alert-json';
  const hasPipelineData =
    analysisProgress &&
    (analysisProgress.status === 'completed' ||
      analysisProgress.status === 'failed' ||
      analysisProgress.status === 'running' ||
      analysisProgress.status === 'paused');
  const [activeSubTab, setActiveSubTab] = useUrlState<SubTab>(
    'subtab',
    hasPipelineData ? 'pipeline' : 'workflow'
  );

  // Local state
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [workflowRun, setWorkflowRun] = useState<WorkflowRun | null>(null);
  const [workflowGeneration, setWorkflowGeneration] = useState<WorkflowGeneration | null>(null);
  const [taskRuns, setTaskRuns] = useState<TaskRun[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loadingWorkflow, setLoadingWorkflow] = useState(false);
  const [loadingTaskRuns, setLoadingTaskRuns] = useState(false);
  const [loadingArtifacts, setLoadingArtifacts] = useState(false);

  // Sort analyses by created_at descending (newest first)
  const sortedAnalyses = [...alertAnalyses].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  // Get the selected analysis object
  const selectedAnalysis = sortedAnalyses.find((a) => a.id === selectedAnalysisId);

  // Auto-select latest analysis if none selected
  useEffect(() => {
    if (!selectedAnalysisId && sortedAnalyses.length > 0) {
      setSelectedAnalysisId(sortedAnalyses[0].id);
    }
  }, [selectedAnalysisId, sortedAnalyses, setSelectedAnalysisId]);

  // Fetch workflow and task runs when selected analysis changes
  const fetchAnalysisData = useCallback(async () => {
    if (!selectedAnalysis?.workflow_run_id) {
      setWorkflow(null);
      setWorkflowRun(null);
      setWorkflowGeneration(null);
      setTaskRuns([]);
      setArtifacts([]);
      return;
    }

    setLoadingWorkflow(true);
    setLoadingTaskRuns(true);
    setLoadingArtifacts(true);

    try {
      // Fetch workflow run
      const [workflowRunData] = await runSafe(
        backendApi.getWorkflowRun(selectedAnalysis.workflow_run_id),
        'fetchWorkflowRun',
        { action: 'fetching workflow run data' }
      );

      if (workflowRunData) {
        setWorkflowRun(workflowRunData);

        // Fetch the workflow definition
        if (workflowRunData.workflow_id) {
          const [workflowData] = await runSafe(
            backendApi.getWorkflow(workflowRunData.workflow_id),
            'fetchWorkflow',
            { action: 'fetching workflow data' }
          );
          if (workflowData) {
            setWorkflow(workflowData);
          }
        }
      }

      // Fetch workflow generation (for LLM cost of the workflow building phase)
      const [generationData] = await runSafe(
        backendApi.listWorkflowGenerations({
          triggering_alert_analysis_id: selectedAnalysis.id,
        }),
        'fetchWorkflowGeneration',
        { action: 'fetching workflow generation data' }
      );

      if (generationData?.workflow_generations && generationData.workflow_generations.length > 0) {
        setWorkflowGeneration(generationData.workflow_generations[0]);
      } else {
        setWorkflowGeneration(null);
      }

      // Fetch task runs (use limit: 100 to get all task runs for this workflow run)
      const [taskRunsData] = await runSafe(
        backendApi.getTaskRuns({
          workflow_run_id: selectedAnalysis.workflow_run_id,
          limit: 100,
        }),
        'fetchTaskRuns',
        { action: 'fetching task runs for workflow' }
      );

      if (taskRunsData?.task_runs) {
        // Sort client-side by created_at descending (newest first)
        const sortedTaskRuns = [...taskRunsData.task_runs].sort(
          (a: TaskRun, b: TaskRun) =>
            new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
        );
        setTaskRuns(sortedTaskRuns);
      }

      // Fetch artifacts (use limit: 100 to get all artifacts for this workflow run)
      const [artifactsData] = await runSafe(
        backendApi.getArtifacts({
          workflow_run_id: selectedAnalysis.workflow_run_id,
          limit: 100,
        }),
        'fetchArtifacts',
        { action: 'fetching artifacts for workflow' }
      );

      if (artifactsData?.artifacts) {
        // Sort client-side by created_at descending (newest first)
        const sortedArtifacts = [...artifactsData.artifacts].sort(
          (a: Artifact, b: Artifact) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        setArtifacts(sortedArtifacts);
      }
    } finally {
      setLoadingWorkflow(false);
      setLoadingTaskRuns(false);
      setLoadingArtifacts(false);
    }
  }, [selectedAnalysis?.workflow_run_id, runSafe]);

  // Trigger data fetch when selected analysis changes
  useEffect(() => {
    if (selectedAnalysis) {
      void fetchAnalysisData();
    }
  }, [selectedAnalysis?.id, fetchAnalysisData]);

  const formatTimestamp = (dateStr: string): string => {
    return moment(dateStr).tz(timezone).format('MMM D, YYYY h:mm A');
  };

  const calculateDuration = (start: string, end?: string): string => {
    if (!end) return 'In progress';
    const durationMs = new Date(end).getTime() - new Date(start).getTime();
    return formatDuration(durationMs / 1000);
  };

  // No analyses available
  if (sortedAnalyses.length === 0) {
    return (
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-8 text-center">
        <ExclamationTriangleIcon className="h-12 w-12 text-gray-500 mx-auto mb-4" />
        <h3 className="text-lg font-medium text-gray-200 mb-2">No Analysis Runs</h3>
        <p className="text-gray-400 mb-4">This alert has not been analyzed yet.</p>
        {onAnalyze && (
          <button
            onClick={onAnalyze}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium transition-colors"
          >
            Start Analysis
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Analysis Selector */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div>
              <label htmlFor="analysis-run-selector" className="block text-xs text-gray-400 mb-1">
                Analysis Run
              </label>
              <AnalysisRunSelector
                analyses={sortedAnalyses}
                selectedId={selectedAnalysisId}
                onSelect={setSelectedAnalysisId}
              />
            </div>
          </div>

          {selectedAnalysis && (
            <div className="flex flex-wrap items-center gap-6 text-sm">
              <div>
                <span className="text-gray-400">ID: </span>
                <span className="text-gray-200 font-mono text-xs">{selectedAnalysis.id}</span>
              </div>
              <div>
                <span className="text-gray-400">Started: </span>
                <span className="text-gray-200">
                  {selectedAnalysis.started_at ? formatTimestamp(selectedAnalysis.started_at) : '—'}
                </span>
              </div>
              {selectedAnalysis.completed_at && selectedAnalysis.started_at && (
                <div>
                  <span className="text-gray-400">Duration: </span>
                  <span className="text-gray-200">
                    {calculateDuration(selectedAnalysis.started_at, selectedAnalysis.completed_at)}
                  </span>
                </div>
              )}
              {/* Workflow execution LLM cost */}
              {workflowRun?.llm_usage?.cost_usd != null && (
                <div>
                  <span className="text-gray-400">Execution Cost: </span>
                  <span className="text-emerald-400 font-semibold">
                    ${workflowRun.llm_usage.cost_usd.toFixed(4)}
                  </span>
                </div>
              )}
              {/* Workflow generation (build) LLM cost */}
              {(() => {
                const orchResults = workflowGeneration
                  ? getOrchResults(workflowGeneration)
                  : undefined;
                const buildCost = orchResults?.metrics?.total_cost_usd;
                return buildCost != null ? (
                  <div>
                    <span className="text-gray-400">Build Cost: </span>
                    <span className="text-emerald-400 font-semibold">${buildCost.toFixed(4)}</span>
                  </div>
                ) : null;
              })()}
              {/* Total combined cost */}
              {(() => {
                const orchResults = workflowGeneration
                  ? getOrchResults(workflowGeneration)
                  : undefined;
                const buildCost = orchResults?.metrics?.total_cost_usd ?? 0;
                const execCost = workflowRun?.llm_usage?.cost_usd ?? 0;
                return execCost > 0 || buildCost > 0 ? (
                  <div className="pl-2 border-l border-gray-600">
                    <span className="text-gray-400">Total Cost: </span>
                    <span className="text-emerald-300 font-bold">
                      ${(execCost + buildCost).toFixed(4)}
                    </span>
                  </div>
                ) : null;
              })()}
              {selectedAnalysis.error_message && (
                <div className="flex items-center text-red-400">
                  <ExclamationTriangleIcon className="h-4 w-4 mr-1" />
                  <span className="text-xs">Error occurred</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Error message display */}
        {selectedAnalysis?.error_message && (
          <div className="mt-4 p-3 bg-red-900/30 border border-red-700 rounded-md">
            <p className="text-sm text-red-300">{selectedAnalysis.error_message}</p>
          </div>
        )}
      </div>

      {/* Sub-tabs */}
      <div className="border-b border-gray-700">
        <nav className="flex gap-4" aria-label="Analysis sub-tabs">
          {hasPipelineData && (
            <button
              onClick={() => setActiveSubTab('pipeline')}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeSubTab === 'pipeline'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'
              }`}
            >
              Pipeline
            </button>
          )}
          <button
            onClick={() => setActiveSubTab('workflow')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeSubTab === 'workflow'
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'
            }`}
          >
            Workflow Run
          </button>
          <button
            onClick={() => setActiveSubTab('tasks')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeSubTab === 'tasks'
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'
            }`}
          >
            Task Runs
            {taskRuns.length > 0 && (
              <span className="ml-2 px-2 py-0.5 text-xs bg-gray-700 rounded-full">
                {taskRuns.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveSubTab('artifacts')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeSubTab === 'artifacts'
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'
            }`}
          >
            Artifacts
            {artifacts.length > 0 && (
              <span className="ml-2 px-2 py-0.5 text-xs bg-gray-700 rounded-full">
                {artifacts.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveSubTab('alert-json')}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeSubTab === 'alert-json'
                ? 'border-primary text-primary'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'
            }`}
          >
            Alert JSON
          </button>
        </nav>
      </div>

      {/* Sub-tab Content */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
        {activeSubTab === 'pipeline' && hasPipelineData && analysisProgress && (
          <AnalysisProgressDisplay
            progress={analysisProgress}
            wasWorkflowGenerated={wasWorkflowGenerated}
            analysisId={analysisId}
          />
        )}

        {activeSubTab === 'workflow' && (
          <>
            {loadingWorkflow ? (
              <div className="flex items-center justify-center h-[500px]">
                <ArrowPathIcon className="h-8 w-8 animate-spin text-gray-400" />
              </div>
            ) : workflow && workflowRun && selectedAnalysis?.workflow_run_id ? (
              <div style={{ height: '500px' }}>
                <WorkflowExecutionReaflow
                  workflow={workflow}
                  workflowRunId={selectedAnalysis.workflow_run_id}
                  className="h-full"
                />
              </div>
            ) : (
              <div className="flex items-center justify-center h-[300px] text-gray-400">
                <p>No workflow data available for this analysis run</p>
              </div>
            )}
          </>
        )}

        {activeSubTab === 'tasks' && (
          <TaskRunList taskRuns={taskRuns} loading={loadingTaskRuns} showWorkflowRunId={false} />
        )}

        {activeSubTab === 'artifacts' && (
          <ArtifactList artifacts={artifacts} loading={loadingArtifacts} />
        )}

        {activeSubTab === 'alert-json' && (
          <>
            {alert ? (
              <div className="bg-gray-900 rounded-lg p-4 overflow-auto max-h-[600px]">
                <JSONTree
                  data={alert}
                  theme={{
                    scheme: 'monokai',
                    base00: '#111827', // background
                    base01: '#1f2937',
                    base02: '#374151',
                    base03: '#4b5563',
                    base04: '#6b7280',
                    base05: '#9ca3af',
                    base06: '#d1d5db',
                    base07: '#e5e7eb', // foreground
                    base08: '#ef4444', // null, undefined
                    base09: '#f97316', // numbers
                    base0A: '#eab308', // regex
                    base0B: '#10b981', // strings
                    base0C: '#06b6d4', // escape
                    base0D: '#3b82f6', // keys
                    base0E: '#8b5cf6', // boolean
                    base0F: '#ec4899', // function
                  }}
                  invertTheme={false}
                  hideRoot={false}
                  shouldExpandNodeInitially={(_keyPath, _data, level) => level < 2}
                  labelRenderer={([key]) => <span style={{ fontWeight: 600 }}>{key}:</span>}
                />
              </div>
            ) : (
              <div className="flex items-center justify-center h-[300px] text-gray-400">
                <p>No alert data available</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
