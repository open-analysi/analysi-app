import React, { useState, useEffect } from 'react';

import { ArrowLeftIcon, PencilSquareIcon } from '@heroicons/react/24/outline';
import { useParams, useNavigate, useLocation } from 'react-router';

import ErrorBoundary from '../components/common/ErrorBoundary';
import { WorkflowBuilder } from '../components/workbench/workflow-builder';
import { WorkflowExecutionDialog } from '../components/workflows/WorkflowExecutionDialog';
import { WorkflowsListSimple } from '../components/workflows/WorkflowsListSimple';
import WorkflowVisualizerReaflow from '../components/workflows/WorkflowVisualizerReaflow';
import { useClickTracking } from '../hooks/useClickTracking';
import useErrorHandler from '../hooks/useErrorHandler';
import { usePageTracking } from '../hooks/usePageTracking';
import { backendApi } from '../services/backendApi';
import { componentStyles } from '../styles/components';
import { Workflow } from '../types/workflow';

const WorkflowsPage: React.FC = () => {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const isEditRoute = location.pathname.endsWith('/edit');
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(false);
  const [showExecutionDialog, setShowExecutionDialog] = useState(false);
  const [isEditing, setIsEditing] = useState(isEditRoute);
  const { runSafe } = useErrorHandler('WorkflowsPage');
  const { trackExecute } = useClickTracking('WorkflowsPage');

  // Track page views
  usePageTracking(workflowId ? 'Workflow Details' : 'Workflows', 'WorkflowsPage');

  // Sync isEditing state with URL
  useEffect(() => {
    setIsEditing(isEditRoute);
  }, [isEditRoute]);

  // Fetch individual workflow when workflowId is provided
  useEffect(() => {
    if (!workflowId) {
      setWorkflow(null);
      return;
    }

    // Reset dialog when switching to a different workflow
    setShowExecutionDialog(false);

    const fetchWorkflow = async () => {
      setLoading(true);
      try {
        const [result] = await runSafe(backendApi.getWorkflow(workflowId), 'fetchWorkflow', {
          action: 'fetching workflow details',
          entityId: workflowId,
        });
        if (result) {
          setWorkflow(result);
          // Track viewing specific workflow details
          trackExecute('view-workflow-details', {
            entityId: result.id,
            entityName: result.name,
          });
        }
      } finally {
        setLoading(false);
      }
    };

    void fetchWorkflow();
  }, [workflowId, runSafe, trackExecute]);

  // Cleanup effect to reset state when component unmounts
  useEffect(() => {
    return () => {
      // Reset all state when navigating away
      setShowExecutionDialog(false);
      setWorkflow(null);
    };
  }, []);

  // Handle node selection in visualizer
  const handleNodeSelect = (nodeId: string) => {
    console.info('Selected node:', nodeId);
    // Future: Show node details in a side panel
  };

  // Handle workflow execution
  const handleExecuteWorkflow = () => {
    if (workflow) {
      setShowExecutionDialog(true);
    }
  };

  // Individual workflow visualizer view
  if (workflowId) {
    // Show workflow builder when editing
    if (isEditing && workflow) {
      const handleCloseEdit = () => {
        setIsEditing(false);
        // Navigate to view route if on /edit route
        if (isEditRoute) {
          void navigate(`/workflows/${workflowId}`);
        }
      };

      return (
        <div className={componentStyles.pageBackground} data-testid="workflow-edit-page">
          <WorkflowBuilder
            workflow={workflow}
            showHeader={true}
            onSave={(updatedWorkflow) => {
              setWorkflow(updatedWorkflow);
              handleCloseEdit();
            }}
            onClose={handleCloseEdit}
            className="h-full"
          />
        </div>
      );
    }

    if (loading) {
      return (
        <div className={componentStyles.pageBackground}>
          <div className="py-6 px-4 sm:px-6 md:px-8">
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
              <span className="ml-3 text-gray-400">Loading workflow...</span>
            </div>
          </div>
        </div>
      );
    }

    if (!workflow) {
      return (
        <div className={componentStyles.pageBackground}>
          <div className="py-6 px-4 sm:px-6 md:px-8">
            <div className="p-6 border border-red-700 bg-red-900/30 rounded-md">
              <h2 className="text-xl font-semibold mb-2 text-gray-100">Workflow not found</h2>
              <p className="text-gray-300 mb-4">The requested workflow could not be found.</p>
              <button
                onClick={() => void navigate('/workflows')}
                className="px-4 py-2 bg-primary rounded-md text-white hover:bg-primary/90"
              >
                Back to Workflows
              </button>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className={componentStyles.pageBackground} data-testid="workflow-visualizer-page">
        {/* Header */}
        <div className="py-4 px-4 sm:px-6 md:px-8 border-b border-gray-700">
          <div className="flex items-center space-x-4 max-w-full overflow-hidden">
            <button
              onClick={() => void navigate('/workflows')}
              className="inline-flex items-center px-3 py-2 border border-gray-600 shadow-xs text-sm leading-4 font-medium rounded-md text-gray-100 bg-dark-800 hover:bg-dark-700 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary shrink-0"
            >
              <ArrowLeftIcon className="h-4 w-4 mr-2" />
              Back to List
            </button>
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-semibold text-white truncate">{workflow.name}</h1>
              <p className="text-sm text-gray-400 wrap-break-word line-clamp-2">
                {workflow.description}
              </p>
            </div>
            <button
              onClick={() => void navigate(`/workflows/${workflowId}/edit`)}
              className="inline-flex items-center px-3 py-2 border border-gray-600 shadow-xs text-sm leading-4 font-medium rounded-md text-gray-100 bg-dark-800 hover:bg-dark-700 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary shrink-0"
            >
              <PencilSquareIcon className="h-4 w-4 mr-2" />
              Edit Workflow
            </button>
          </div>
        </div>

        {/* Visualizer */}
        <div className="flex-1 p-4 sm:p-6 md:p-8">
          <ErrorBoundary
            component="WorkflowVisualizer"
            fallback={
              <div className="p-6 border border-red-700 bg-red-900/30 rounded-md">
                <h3 className="text-lg font-medium text-red-400 mb-2">
                  Could not display workflow visualizer
                </h3>
                <p className="text-sm text-gray-300 mb-4">
                  There was an error loading the workflow visualizer.
                </p>
                <button
                  onClick={() => window.location.reload()}
                  className="px-4 py-2 bg-primary rounded-md text-white hover:bg-primary/90"
                >
                  Reload page
                </button>
              </div>
            }
          >
            <WorkflowVisualizerReaflow
              workflow={workflow}
              onNodeSelect={handleNodeSelect}
              onExecuteWorkflow={handleExecuteWorkflow}
              className="h-full"
            />
          </ErrorBoundary>
        </div>

        {/* Execution Dialog */}
        {workflow && (
          <WorkflowExecutionDialog
            workflow={workflow}
            isOpen={showExecutionDialog}
            loading={false}
            onClose={() => setShowExecutionDialog(false)}
            onExecute={(inputData) =>
              void (async () => {
                try {
                  // Track workflow execution
                  trackExecute('workflow', {
                    entityId: workflow.id,
                    entityName: workflow.name,
                  });

                  const [result] = await runSafe(
                    backendApi.executeWorkflow(workflow.id, { input_data: inputData }),
                    'executeWorkflow',
                    { action: 'executing workflow', entityId: workflow.id, params: inputData }
                  );

                  if (result) {
                    setShowExecutionDialog(false);
                    // Navigate to the dedicated workflow run page
                    void navigate(`/workflow-runs/${result.workflow_run_id}`);
                  }
                } catch (error) {
                  console.error('Failed to execute workflow:', error);
                }
              })()
            }
          />
        )}
      </div>
    );
  }

  // Default list view
  return (
    <ErrorBoundary
      component="WorkflowsPage"
      fallback={
        <div className={componentStyles.pageBackground}>
          <div className="py-6 px-4 sm:px-6 md:px-8">
            <div className="p-6 border border-red-700 bg-red-900/30 rounded-md">
              <h2 className="text-xl font-semibold mb-2 text-gray-100">Error loading workflows</h2>
              <p className="text-gray-300 mb-4">There was an error rendering the workflows page.</p>
              <button
                onClick={() => window.location.reload()}
                className="px-4 py-2 bg-primary rounded-md text-white hover:bg-primary/90"
              >
                Reload page
              </button>
            </div>
          </div>
        </div>
      }
    >
      <div className={componentStyles.pageBackground} data-testid="workflows-page">
        <div className="py-6 px-4 sm:px-6 md:px-8">
          <ErrorBoundary
            component="WorkflowsList"
            fallback={
              <div className="p-4 border border-red-700 bg-red-900/30 rounded-md">
                <h3 className="text-lg font-medium text-red-400 mb-2">
                  Could not display workflows list
                </h3>
                <p className="text-sm text-gray-300 mb-4">
                  There was an error loading the workflows list.
                </p>
                <button
                  onClick={() => window.location.reload()}
                  className="px-4 py-2 bg-primary rounded-md text-white hover:bg-primary/90"
                >
                  Reload page
                </button>
              </div>
            }
          >
            <WorkflowsListSimple />
          </ErrorBoundary>
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default WorkflowsPage;
