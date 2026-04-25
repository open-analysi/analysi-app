/* eslint-disable @typescript-eslint/no-misused-promises */
import React, { useEffect, useState, useRef } from 'react';

import {
  ArrowLeftIcon,
  ArrowPathIcon,
  ArrowDownTrayIcon,
  ClipboardDocumentIcon,
  CheckIcon,
  PlayIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import ReactMarkdown from 'react-markdown';
import { useParams, useNavigate, useSearchParams } from 'react-router';

import { AnalysisDetailsTab } from '../components/alerts/AnalysisDetailsTab';
import { AnalysisProgressDisplay } from '../components/alerts/AnalysisProgressDisplay';
import { DecisionBanner } from '../components/alerts/DecisionBanner';
import { FindingsTab } from '../components/alerts/FindingsTab';
import { reportMarkdownComponents } from '../components/alerts/markdownComponents';
import { OverviewTab } from '../components/alerts/OverviewTab';
import { ConfirmDialog } from '../components/common/ConfirmDialog';
import ErrorBoundary from '../components/common/ErrorBoundary';
import useErrorHandler from '../hooks/useErrorHandler';
import { usePageTracking } from '../hooks/usePageTracking';
import { useUrlState } from '../hooks/useUrlState';
import { backendApi } from '../services/backendApi';
import { useAlertStore } from '../store/alertStore';
import { componentStyles } from '../styles/components';
import type { Alert, Disposition } from '../types/alert';
import { TaskRun } from '../types/taskRun';

// ─── Report Tab with Export ─────────────────────────────────────────

const ReportTab: React.FC<{ alert: Alert; markdown: string }> = ({ alert, markdown }) => {
  const [copied, setCopied] = React.useState(false);

  const handleCopyMarkdown = async () => {
    await navigator.clipboard.writeText(markdown);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    const slug = (alert.human_readable_id ?? alert.alert_id).replace(/[^a-zA-Z0-9-_]/g, '_');
    const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report-${slug}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-medium text-gray-200">AI Generated Analysis Summary</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => void handleCopyMarkdown()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-300 bg-dark-700 hover:bg-dark-600 border border-gray-600 rounded-sm transition-colors"
            title="Copy report as Markdown"
          >
            {copied ? (
              <CheckIcon className="h-3.5 w-3.5 text-green-400" />
            ) : (
              <ClipboardDocumentIcon className="h-3.5 w-3.5" />
            )}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <button
            onClick={handleDownloadMarkdown}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-primary hover:bg-primary/90 rounded-sm transition-colors"
            title="Download report as Markdown file"
          >
            <ArrowDownTrayIcon className="h-3.5 w-3.5" />
            Export
          </button>
        </div>
      </div>
      <div className="prose prose-invert prose-sm max-w-none">
        <ReactMarkdown components={reportMarkdownComponents}>{markdown}</ReactMarkdown>
      </div>
    </div>
  );
};

// ─── Alert Details Page ─────────────────────────────────────────────

export const AlertDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { error: errorHandler, clearError } = useErrorHandler('AlertDetailsPage');

  usePageTracking('Alert Details', 'AlertDetailsPage');

  const {
    selectedAlert,
    dispositions,
    analysisProgress,
    alertAnalyses,
    isLoadingAlert,
    isAnalyzing,
    error,
    fetchAlert,
    fetchDispositions,
    startAnalysis,
    fetchAnalysisProgress,
    fetchAlertAnalyses,
    setSelectedAlert,
    clearError: clearStoreError,
    clearAnalysisProgress,
  } = useAlertStore();

  const [activeTab, setActiveTab] = useUrlState<'details' | 'findings' | 'summary' | 'analysis'>(
    'tab',
    'details'
  );
  const [, setSearchParams] = useSearchParams();
  const [hasClosedProgress, setHasClosedProgress] = useState(false);
  const [showReanalyzeModal, setShowReanalyzeModal] = useState(false);
  const [wasWorkflowGenerated, setWasWorkflowGenerated] = useState(false);
  const [taskRuns, setTaskRuns] = useState<TaskRun[]>([]);
  const [loadingTaskRuns, setLoadingTaskRuns] = useState(false);
  const pollingStartedRef = useRef(false);

  // Load alert details
  useEffect(() => {
    if (id) {
      setHasClosedProgress(false);
      pollingStartedRef.current = false;
      void fetchAlert(id);
      void fetchDispositions();
      void fetchAlertAnalyses(id);
    }
    return () => {
      setSelectedAlert(undefined);
    };
  }, [id, fetchAlert, fetchDispositions, fetchAlertAnalyses, setSelectedAlert]);

  // Fetch analysis progress once for completed/failed analyses
  useEffect(() => {
    if (
      id &&
      selectedAlert &&
      (selectedAlert.analysis_status === 'completed' ||
        selectedAlert.analysis_status === 'failed') &&
      !analysisProgress
    ) {
      void fetchAnalysisProgress(id);
    }
  }, [id, selectedAlert?.analysis_status, analysisProgress, fetchAnalysisProgress]);

  // Fetch workflow generation data
  useEffect(() => {
    const fetchWorkflowGeneration = async () => {
      if (!selectedAlert?.current_analysis_id) {
        setWasWorkflowGenerated(false);
        return;
      }
      try {
        const response = await backendApi.listWorkflowGenerations({
          triggering_alert_analysis_id: selectedAlert.current_analysis_id,
        });
        setWasWorkflowGenerated(
          response.workflow_generations && response.workflow_generations.length > 0
        );
      } catch {
        setWasWorkflowGenerated(false);
      }
    };
    void fetchWorkflowGeneration();
  }, [selectedAlert?.current_analysis_id]);

  // Fetch task runs when current analysis has a workflow run
  useEffect(() => {
    const fetchTaskRuns = async () => {
      const workflowRunId = selectedAlert?.current_analysis?.workflow_run_id;
      if (!workflowRunId) {
        setTaskRuns([]);
        return;
      }
      setLoadingTaskRuns(true);
      try {
        const response = await backendApi.getTaskRuns({ workflow_run_id: workflowRunId });
        if (response?.task_runs) {
          setTaskRuns(response.task_runs);
        }
      } catch {
        setTaskRuns([]);
      } finally {
        setLoadingTaskRuns(false);
      }
    };
    void fetchTaskRuns();
  }, [selectedAlert?.current_analysis?.workflow_run_id]);

  // Start polling for analysis progress if alert is analyzing
  useEffect(() => {
    if (selectedAlert?.analysis_status === 'in_progress' && id) {
      if (
        analysisProgress &&
        (analysisProgress.status === 'completed' || analysisProgress.status === 'failed')
      ) {
        pollingStartedRef.current = false;
        return;
      }
      if (!pollingStartedRef.current) {
        pollingStartedRef.current = true;
        void fetchAnalysisProgress(id);
      }
    } else {
      pollingStartedRef.current = false;
    }
  }, [
    selectedAlert?.analysis_status,
    id,
    fetchAnalysisProgress,
    hasClosedProgress,
    analysisProgress,
  ]);

  const handleStartAnalysis = async (isReanalyze: boolean = false) => {
    if (!id) return;
    if (isReanalyze && selectedAlert?.analysis_status === 'completed') {
      setShowReanalyzeModal(true);
      return;
    }
    pollingStartedRef.current = false;
    setHasClosedProgress(false);
    clearAnalysisProgress();
    await startAnalysis(id);
  };

  const handleConfirmReanalyze = async () => {
    if (!id) return;
    setShowReanalyzeModal(false);
    pollingStartedRef.current = false;
    setHasClosedProgress(false);
    clearAnalysisProgress();
    await startAnalysis(id);
  };

  const getDispositionDetails = (alert: Alert): Disposition | undefined => {
    if (dispositions.length === 0) return undefined;
    if (alert.current_disposition_display_name) {
      return dispositions.find((d) => d.display_name === alert.current_disposition_display_name);
    }
    return undefined;
  };

  const renderError = () => {
    const errorMessage = error || errorHandler?.message;
    if (!errorMessage) return null;
    return (
      <div className="mb-6 bg-red-900/30 border border-red-700 p-4 rounded-md">
        <div className="flex items-center">
          <ExclamationTriangleIcon className="h-5 w-5 text-red-500 mr-2" />
          <div className="flex-1">
            <p className="text-gray-200">{errorMessage}</p>
          </div>
          <button
            onClick={() => {
              clearStoreError();
              clearError();
            }}
            className="text-gray-400 hover:text-gray-200 text-sm"
          >
            Dismiss
          </button>
        </div>
      </div>
    );
  };

  if (isLoadingAlert) {
    return (
      <div className={componentStyles.pageBackground}>
        <div className="py-6 px-4 sm:px-6 md:px-8">
          <div className="flex items-center justify-center h-64">
            <ArrowPathIcon className="h-8 w-8 animate-spin text-gray-400" />
          </div>
        </div>
      </div>
    );
  }

  if (!selectedAlert) {
    return (
      <div className={componentStyles.pageBackground}>
        <div className="py-6 px-4 sm:px-6 md:px-8">
          <div className="text-center">
            <p className="text-gray-400">Alert not found</p>
            <button
              onClick={() => navigate('/alerts')}
              className="mt-4 px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90"
            >
              Back to Alerts
            </button>
          </div>
        </div>
      </div>
    );
  }

  const disposition = getDispositionDetails(selectedAlert);

  return (
    <ErrorBoundary component="AlertDetailsPage">
      <div className={componentStyles.pageBackground}>
        <div className="py-6 px-4 sm:px-6 md:px-8">
          {/* Header */}
          <div className="mb-6">
            <button
              onClick={() => navigate('/alerts')}
              className="flex items-center text-sm text-gray-400 hover:text-gray-200 mb-4"
            >
              <ArrowLeftIcon className="h-4 w-4 mr-1" />
              Back to Alerts
            </button>

            <div className="flex items-start justify-between mb-4">
              <div className="flex-1">
                <h1 className="text-2xl font-semibold text-gray-100">
                  {selectedAlert.human_readable_id}: {selectedAlert.title}
                </h1>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => window.location.reload()}
                  className="flex items-center px-3 py-1.5 text-sm text-gray-400 hover:text-gray-200 hover:bg-gray-700 rounded-sm transition-colors"
                  title="Refresh"
                >
                  <ArrowPathIcon className="h-4 w-4 mr-1.5" />
                  Refresh
                </button>

                {selectedAlert.analysis_status === 'new' && (
                  <button
                    onClick={() => handleStartAnalysis(false)}
                    disabled={isAnalyzing}
                    className="flex items-center px-3 py-1.5 text-sm bg-primary text-white rounded-md hover:bg-primary/90 disabled:opacity-50"
                  >
                    <PlayIcon className="h-4 w-4 mr-1.5" />
                    Analyze
                  </button>
                )}
                {selectedAlert.analysis_status === 'in_progress' && (
                  <button
                    disabled
                    className="flex items-center px-3 py-1.5 text-sm bg-blue-900 text-blue-300 rounded-md opacity-75"
                  >
                    <ArrowPathIcon className="h-4 w-4 mr-1.5 animate-spin" />
                    Analyzing
                  </button>
                )}
                {selectedAlert.analysis_status === 'completed' && (
                  <button
                    onClick={() => handleStartAnalysis(true)}
                    disabled={isAnalyzing}
                    className="flex items-center px-3 py-1.5 text-sm bg-gray-700 text-gray-200 rounded-md hover:bg-gray-600 disabled:opacity-50"
                  >
                    <ArrowPathIcon className="h-4 w-4 mr-1.5" />
                    Re-analyze
                  </button>
                )}
                {selectedAlert.analysis_status === 'failed' && (
                  <button
                    onClick={() => handleStartAnalysis(false)}
                    disabled={isAnalyzing}
                    className="flex items-center px-3 py-1.5 text-sm bg-red-900/50 text-red-300 rounded-md hover:bg-red-900/70 disabled:opacity-50 border border-red-700"
                    title="Retry the failed analysis"
                  >
                    <ArrowPathIcon className="h-4 w-4 mr-1.5" />
                    Retry Analysis
                  </button>
                )}
                {selectedAlert.analysis_status === 'cancelled' && (
                  <button
                    onClick={() => handleStartAnalysis(false)}
                    disabled={isAnalyzing}
                    className="flex items-center px-3 py-1.5 text-sm bg-yellow-900/50 text-yellow-300 rounded-md hover:bg-yellow-900/70 disabled:opacity-50 border border-yellow-700"
                    title="Restart the cancelled analysis"
                  >
                    <ArrowPathIcon className="h-4 w-4 mr-1.5" />
                    Restart Analysis
                  </button>
                )}
              </div>
            </div>

            {/* Decision Banner */}
            <DecisionBanner alert={selectedAlert} disposition={disposition} />

            {/* Show error message for failed analyses */}
            {selectedAlert.analysis_status === 'failed' && (
              <div className="flex items-start gap-2 p-3 mt-4 bg-red-900/20 border border-red-700/50 rounded-md">
                <ExclamationTriangleIcon className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-red-300">Analysis Failed</p>
                  <p className="text-sm text-red-200/80 mt-1">
                    {selectedAlert.current_analysis?.error_message ||
                      'The analysis workflow encountered an error. Please retry the analysis or contact support if the issue persists.'}
                  </p>
                  {selectedAlert.current_analysis?.workflow_run_id && (
                    <p className="text-xs text-red-200/60 mt-2">
                      Workflow Run ID: {selectedAlert.current_analysis.workflow_run_id}
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>

          {renderError()}

          {/* Tabs — Order: Overview, Report, Task Results, Runs & Data */}
          <div className="border-b border-gray-700 mb-6">
            <nav className="-mb-px flex space-x-8">
              <button
                onClick={() => setActiveTab('details')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'details'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-gray-400 hover:text-gray-200'
                }`}
              >
                Overview
              </button>
              {selectedAlert?.current_analysis?.long_summary && (
                <button
                  onClick={() => setActiveTab('summary')}
                  className={`py-2 px-1 border-b-2 font-medium text-sm ${
                    activeTab === 'summary'
                      ? 'border-primary text-primary'
                      : 'border-transparent text-gray-400 hover:text-gray-200'
                  }`}
                >
                  Report
                </button>
              )}
              {selectedAlert?.current_analysis?.workflow_run_id && (
                <button
                  onClick={() => setActiveTab('findings')}
                  className={`py-2 px-1 border-b-2 font-medium text-sm ${
                    activeTab === 'findings'
                      ? 'border-primary text-primary'
                      : 'border-transparent text-gray-400 hover:text-gray-200'
                  }`}
                >
                  Task Results
                  {taskRuns.length > 0 && (
                    <span className="ml-2 px-2 py-0.5 text-xs bg-gray-700 text-gray-300 rounded-full">
                      {taskRuns.length}
                    </span>
                  )}
                </button>
              )}
              <button
                onClick={() => setActiveTab('analysis')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  activeTab === 'analysis'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-gray-400 hover:text-gray-200'
                }`}
              >
                Runs & Data
                {alertAnalyses.length > 0 && (
                  <span className="ml-2 px-2 py-0.5 text-xs bg-gray-700 text-gray-300 rounded-full">
                    {alertAnalyses.length}
                  </span>
                )}
              </button>
            </nav>
          </div>

          {/* Content — always full-width, no sidebar */}
          <div>
            {activeTab === 'details' && (
              <div className="space-y-6">
                {/* Analysis Progress - Show prominently while running */}
                {analysisProgress &&
                  (analysisProgress.status === 'running' ||
                    analysisProgress.status === 'paused') && (
                    <AnalysisProgressDisplay
                      progress={analysisProgress}
                      wasWorkflowGenerated={wasWorkflowGenerated}
                      analysisId={selectedAlert?.current_analysis_id ?? undefined}
                    />
                  )}

                <OverviewTab
                  alert={selectedAlert}
                  taskRuns={taskRuns}
                  onNavigateToTab={(tab, subtab) => {
                    setSearchParams(
                      (prev) => {
                        prev.set('tab', tab);
                        if (subtab) {
                          prev.set('subtab', subtab);
                        }
                        return prev;
                      },
                      { replace: true }
                    );
                  }}
                />
              </div>
            )}

            {activeTab === 'summary' && selectedAlert?.current_analysis?.long_summary && (
              <ReportTab
                alert={selectedAlert}
                markdown={selectedAlert.current_analysis.long_summary}
              />
            )}

            {activeTab === 'findings' && (
              <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
                <h3 className="text-lg font-medium text-gray-200 mb-4">Analysis Findings</h3>
                <FindingsTab taskRuns={taskRuns} loading={loadingTaskRuns} />
              </div>
            )}

            {activeTab === 'analysis' && id && (
              <AnalysisDetailsTab
                alertId={id}
                alertAnalyses={alertAnalyses}
                currentAnalysis={selectedAlert?.current_analysis}
                alert={selectedAlert}
                onAnalyze={() => void handleStartAnalysis(false)}
                analysisProgress={analysisProgress}
                wasWorkflowGenerated={wasWorkflowGenerated}
                analysisId={selectedAlert?.current_analysis_id ?? undefined}
              />
            )}
          </div>

          {/* Re-analyze Confirmation Modal */}
          <ConfirmDialog
            isOpen={showReanalyzeModal}
            onClose={() => setShowReanalyzeModal(false)}
            onConfirm={() => void handleConfirmReanalyze()}
            title="Re-analyze Alert?"
            message="This will re-run the entire analysis workflow from scratch. The process may take several minutes to complete. Previous analysis results will be preserved in the history."
            confirmLabel="Re-analyze"
            cancelLabel="Cancel"
            variant="warning"
          />
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default AlertDetailsPage;
