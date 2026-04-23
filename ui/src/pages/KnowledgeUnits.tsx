import React from 'react';

import ErrorBoundary from '../components/common/ErrorBoundary';
import { KnowledgeUnits as KnowledgeUnitsComponent } from '../components/settings/KnowledgeUnits';
import { usePageTracking } from '../hooks/usePageTracking';
import { componentStyles } from '../styles/components';

const KnowledgeUnitsPage: React.FC = () => {
  // Track page views
  usePageTracking('Knowledge Units', 'KnowledgeUnitsPage');
  return (
    <ErrorBoundary
      component="KnowledgeUnitsPage"
      fallback={
        <div className={componentStyles.pageBackground}>
          <div className="py-6 px-4 sm:px-6 md:px-8">
            <div className="p-6 border border-red-700 bg-red-900/30 rounded-md">
              <h2 className="text-xl font-semibold mb-2 text-gray-100">
                Error loading Knowledge Units
              </h2>
              <p className="text-gray-300 mb-4">
                There was an error rendering the Knowledge Units page.
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
      <div className={componentStyles.pageBackground} data-testid="knowledge-units-page">
        <div className="py-6 px-4 sm:px-6 md:px-8">
          <KnowledgeUnitsComponent />
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default KnowledgeUnitsPage;
