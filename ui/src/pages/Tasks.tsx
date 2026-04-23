import ErrorBoundary from '../components/common/ErrorBoundary';
import { Tasks as TasksComponent } from '../components/settings/Tasks';
import { usePageTracking } from '../hooks/usePageTracking';
import { componentStyles } from '../styles/components';

const TasksPage = () => {
  // Track page views
  usePageTracking('Tasks', 'TasksPage');
  return (
    <ErrorBoundary
      component="TasksPage"
      fallback={
        <div className={componentStyles.pageBackground}>
          <div className="py-6 px-4 sm:px-6 md:px-8">
            <div className="p-6 border border-red-700 bg-red-900/30 rounded-md">
              <h2 className="text-xl font-semibold mb-2 text-gray-100">Error loading tasks</h2>
              <p className="text-gray-300 mb-4">There was an error rendering the tasks page.</p>
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
      <div className={componentStyles.pageBackground} data-testid="tasks-page">
        <div className="py-6 px-4 sm:px-6 md:px-8">
          <ErrorBoundary
            component="TasksPage-TasksComponent"
            fallback={
              <div className="p-4 border border-red-700 bg-red-900/30 rounded-md">
                <h3 className="text-lg font-medium text-red-400 mb-2">Could not display Tasks</h3>
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
            <TasksComponent />
          </ErrorBoundary>
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default TasksPage;
