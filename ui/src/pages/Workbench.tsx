import React, { useCallback, useEffect } from 'react';

import { useLocation, useNavigate, useSearchParams } from 'react-router';

import ErrorBoundary from '../components/common/ErrorBoundary';
import { WorkbenchModern as WorkbenchComponent, WorkflowBuilder } from '../components/workbench';
import { usePageTracking } from '../hooks/usePageTracking';
import { useUrlState } from '../hooks/useUrlState';
import { componentStyles } from '../styles/components';

type WorkbenchTab = 'execute' | 'builder';

const WorkbenchPage = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Tab state from URL
  const [activeTab, setActiveTab] = useUrlState<WorkbenchTab>('tab', 'execute');

  // Track page views
  usePageTracking(activeTab === 'builder' ? 'Workflow Builder' : 'Workbench', 'WorkbenchPage');

  const navigationState = location.state as
    | {
        taskId?: string;
        inputData?: unknown;
        taskName?: string;
        taskRunId?: string;
        cyScript?: string;
        isAdHoc?: boolean;
      }
    | undefined;

  // On mount: promote navigation state into URL params so the view is bookmarkable
  useEffect(() => {
    if (navigationState) {
      const url = new URL(window.location.href);
      if (navigationState.taskId) url.searchParams.set('taskId', navigationState.taskId);
      if (navigationState.taskRunId) url.searchParams.set('taskRunId', navigationState.taskRunId);
      // Replace state: clears nav state AND updates URL atomically
      window.history.replaceState({}, document.title, url.pathname + url.search);
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Compute workbench props from URL parameters or navigation state
  // This avoids setState in useEffect
  const workbenchProps = React.useMemo(() => {
    // Check URL parameters first (for deep linking / new tabs)
    const taskIdFromUrl = searchParams.get('taskId');
    const taskRunIdFromUrl = searchParams.get('taskRunId');

    if (taskIdFromUrl || taskRunIdFromUrl) {
      // Merge: URL params are source of truth for IDs, but nav state may carry inputData
      return {
        taskId: taskIdFromUrl || navigationState?.taskId || undefined,
        taskRunId: taskRunIdFromUrl || undefined,
        inputData: navigationState?.inputData as string | undefined,
        cyScript: navigationState?.cyScript,
        isAdHoc: navigationState?.isAdHoc ?? false,
      };
    }

    // Fall back to navigation state (for programmatic navigation)
    if (navigationState) {
      return {
        taskId: navigationState.taskId,
        inputData: navigationState.inputData as string | undefined,
        taskName: navigationState.taskName,
        taskRunId: navigationState.taskRunId,
        cyScript: navigationState.cyScript,
        isAdHoc: navigationState.isAdHoc,
      };
    }

    return undefined;
  }, [searchParams, navigationState]);

  // Callback to clear taskRunId from URL when the user exits the task run view
  const clearTaskRunId = useCallback(() => {
    setSearchParams(
      (prev) => {
        prev.delete('taskRunId');
        return prev;
      },
      { replace: true }
    );
  }, [setSearchParams]);

  // Callback to clear taskId from URL (e.g., when the task is not found)
  const clearTaskId = useCallback(() => {
    setSearchParams(
      (prev) => {
        prev.delete('taskId');
        prev.delete('taskRunId');
        return prev;
      },
      { replace: true }
    );
  }, [setSearchParams]);

  return (
    <ErrorBoundary
      component="WorkbenchPage"
      fallback={
        <div className={componentStyles.pageBackground}>
          <div className="py-6 px-4 sm:px-6 md:px-8">
            <div className="p-6 border border-red-700 bg-red-900/30 rounded-md">
              <h2 className="text-xl font-semibold mb-2 text-gray-100">Error loading workbench</h2>
              <p className="text-gray-300 mb-4">There was an error rendering the workbench page.</p>
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
      <div
        className={`${componentStyles.pageBackground} ${activeTab === 'builder' ? 'max-h-screen overflow-hidden' : ''}`}
        data-testid="workbench-page"
      >
        <div className="flex flex-col h-full">
          {/* Tab Navigation */}
          <div className="border-b border-gray-700 px-4 sm:px-6 md:px-8 pt-4">
            <nav className="-mb-px flex space-x-8">
              <button
                onClick={() => setActiveTab('execute')}
                className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === 'execute'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'
                }`}
              >
                Tasks
              </button>
              <button
                onClick={() => setActiveTab('builder')}
                className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors ${
                  activeTab === 'builder'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-gray-400 hover:text-gray-200 hover:border-gray-500'
                }`}
              >
                Workflows
              </button>
            </nav>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-hidden">
            {activeTab === 'execute' ? (
              <div className="py-6 px-4 sm:px-6 md:px-8 h-full">
                <ErrorBoundary
                  component="WorkbenchPage-WorkbenchComponent"
                  fallback={
                    <div className="p-4 border border-red-700 bg-red-900/30 rounded-md">
                      <h3 className="text-lg font-medium text-red-400 mb-2">
                        Could not display Workbench
                      </h3>
                      <p className="text-sm text-gray-300 mb-4">
                        There was an error loading this section.
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
                  <WorkbenchComponent
                    {...(workbenchProps ?? {})}
                    onClearTaskRunId={clearTaskRunId}
                    onClearTaskId={clearTaskId}
                  />
                </ErrorBoundary>
              </div>
            ) : (
              <ErrorBoundary
                component="WorkbenchPage-WorkflowBuilder"
                fallback={
                  <div className="p-6 m-4 border border-red-700 bg-red-900/30 rounded-md">
                    <h3 className="text-lg font-medium text-red-400 mb-2">
                      Could not display Workflow Builder
                    </h3>
                    <p className="text-sm text-gray-300 mb-4">
                      There was an error loading the workflow builder.
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
                <WorkflowBuilder
                  showHeader={true}
                  onSave={(wf) => void navigate(`/workflows/${wf.id}`)}
                  className="h-full"
                />
              </ErrorBoundary>
            )}
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default WorkbenchPage;
