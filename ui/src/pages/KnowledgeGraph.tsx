import React from 'react';

import ErrorBoundary from '../components/common/ErrorBoundary';
import { KnowledgeGraph as KnowledgeGraphComponent } from '../components/settings/KnowledgeGraph';
import { componentStyles } from '../styles/components';

const KnowledgeGraphPage: React.FC = () => {
  return (
    <ErrorBoundary
      component="KnowledgeGraphPage"
      fallback={
        <div className={componentStyles.pageBackground}>
          <div className="py-6 px-4 sm:px-6 md:px-8">
            <div className="p-6 border border-red-700 bg-red-900/30 rounded-md">
              <h2 className="text-xl font-semibold mb-2 text-gray-100">
                Error loading Knowledge Graph
              </h2>
              <p className="text-gray-300 mb-4">
                There was an error rendering the Knowledge Graph page.
              </p>
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
      <div className={componentStyles.pageBackground} data-testid="knowledge-graph-page">
        <div className="py-6 px-4 sm:px-6 md:px-8">
          <div>
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
              Knowledge Dependency Graph
            </h1>
            <p className="mt-1 text-sm text-gray-500">
              Visualize relationships between tasks, knowledge units, and modules
            </p>
          </div>
          <div className="mt-6">
            <KnowledgeGraphComponent hideTitle={true} />
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default KnowledgeGraphPage;
