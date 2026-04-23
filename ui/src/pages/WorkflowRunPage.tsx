import React, { useEffect, useMemo, useState } from 'react';

import { ArrowLeftIcon, ClipboardDocumentIcon, CheckIcon } from '@heroicons/react/24/outline';
import { useNavigate, useParams } from 'react-router';

import WorkflowExecutionReaflow from '../components/workflows/WorkflowExecutionReaflow';
import useErrorHandler from '../hooks/useErrorHandler';
import { backendApi } from '../services/backendApi';
import { Workflow, WorkflowRun } from '../types/workflow';
import { formatDuration } from '../utils/formatUtils';

const WorkflowRunPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { runSafe } = useErrorHandler('WorkflowRunPage');

  const [workflowRun, setWorkflowRun] = useState<WorkflowRun | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCopyRunId = () => {
    if (!runId) return;
    void navigator.clipboard.writeText(runId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  useEffect(() => {
    if (!runId) return;

    const load = async () => {
      setLoading(true);
      setError(null);

      const [run] = await runSafe(backendApi.getWorkflowRun(runId), 'load', {
        action: 'fetching workflow run',
        entityId: runId,
      });

      if (!run) {
        setError('Workflow run not found.');
        setLoading(false);
        return;
      }

      setWorkflowRun(run);

      if (!run.workflow_id) {
        setLoading(false);
        return;
      }

      const [wf] = await runSafe(backendApi.getWorkflow(run.workflow_id), 'load', {
        action: 'fetching workflow definition',
        entityId: run.workflow_id,
      });

      if (wf) setWorkflow(wf);
      setLoading(false);
    };

    void load();
  }, [runId, runSafe]);

  const getStatusColor = (status: WorkflowRun['status']) => {
    switch (status) {
      case 'completed':
        return 'text-green-400';
      case 'running':
        return 'text-blue-400';
      case 'failed':
        return 'text-red-400';
      case 'cancelled':
      case 'paused':
        return 'text-amber-400';
      default:
        return 'text-gray-400';
    }
  };

  const duration = useMemo(() => {
    if (!workflowRun?.started_at) return '-';
    const start = new Date(workflowRun.started_at).getTime();
    const end = workflowRun.completed_at ? new Date(workflowRun.completed_at).getTime() : start; // Show 0s for in-progress runs without an end time
    return formatDuration(end - start);
  }, [workflowRun]);

  return (
    <div className="flex flex-col bg-dark-900 overflow-hidden">
      {/* Header */}
      <div className="flex-none flex items-center gap-4 px-4 py-3 border-b border-gray-700 bg-dark-800">
        <button
          onClick={() => void navigate(-1)}
          className="flex items-center gap-1.5 text-gray-400 hover:text-gray-100 transition-colors text-sm"
        >
          <ArrowLeftIcon className="w-4 h-4" />
          Back
        </button>

        <div className="h-4 w-px bg-gray-600" />

        {loading ? (
          <div className="h-4 w-48 bg-gray-700 rounded-sm animate-pulse" />
        ) : (
          <>
            <h1 className="text-sm font-semibold text-gray-100 truncate">
              {workflow?.name ?? workflowRun?.workflow_name ?? 'Workflow Run'}
            </h1>
            {workflowRun && (
              <>
                <div className="h-4 w-px bg-gray-600" />
                <span
                  className={`text-xs font-medium capitalize ${getStatusColor(workflowRun.status)}`}
                >
                  {workflowRun.status}
                </span>
                <div className="h-4 w-px bg-gray-600" />
                <span className="text-xs text-gray-500">{duration}</span>
                {workflowRun.started_at && (
                  <>
                    <div className="h-4 w-px bg-gray-600" />
                    <span className="text-xs text-gray-500">
                      Started {new Date(workflowRun.started_at).toLocaleString()}
                    </span>
                  </>
                )}
                <div className="h-4 w-px bg-gray-600" />
                <button
                  onClick={handleCopyRunId}
                  className="flex items-center gap-1.5 text-xs text-gray-500 font-mono hover:text-gray-300 transition-colors group"
                  title="Copy full run ID"
                >
                  <span className="truncate max-w-[160px]">{runId}</span>
                  {copied ? (
                    <CheckIcon className="w-3.5 h-3.5 text-green-400 shrink-0" />
                  ) : (
                    <ClipboardDocumentIcon className="w-3.5 h-3.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                  )}
                </button>
              </>
            )}
          </>
        )}
      </div>

      {/* Graph — fills remaining viewport */}
      <div className="flex-1 overflow-hidden">
        {loading && (
          <div className="flex items-center justify-center h-full">
            <div className="flex flex-col items-center gap-3 text-gray-400">
              <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <span className="text-sm">Loading workflow execution...</span>
            </div>
          </div>
        )}
        {!loading && error && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-gray-400">
              <p className="text-lg font-medium mb-2">Unable to load workflow run</p>
              <p className="text-sm">{error}</p>
            </div>
          </div>
        )}
        {!loading && !error && workflow && runId && (
          <WorkflowExecutionReaflow
            workflow={workflow}
            workflowRunId={runId}
            className="workflow-execution-page"
          />
        )}
        {!loading && !error && workflowRun && !workflow && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center text-gray-400">
              <p className="text-lg font-medium mb-2">No workflow graph available for this run.</p>
              <p className="text-sm">This run does not have an associated workflow definition.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default WorkflowRunPage;
