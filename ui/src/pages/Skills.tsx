import React from 'react';

import ErrorBoundary from '../components/common/ErrorBoundary';
import { SkillsLayout } from '../components/skills/SkillsLayout';
import { usePageTracking } from '../hooks/usePageTracking';

const SkillsPage: React.FC = () => {
  usePageTracking('Skills', 'SkillsPage');

  return (
    <ErrorBoundary
      component="SkillsPage"
      fallback={
        <div className="flex flex-col h-full bg-dark-900">
          <div className="py-6 px-4 sm:px-6 md:px-8">
            <div className="p-6 border border-red-700 bg-red-900/30 rounded-md">
              <h2 className="text-xl font-semibold mb-2 text-gray-100">Error loading Skills</h2>
              <p className="text-gray-300 mb-4">There was an error rendering the Skills page.</p>
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
      <div className="flex flex-col h-full bg-dark-900" data-testid="skills-page">
        <SkillsLayout />
      </div>
    </ErrorBoundary>
  );
};

export default SkillsPage;
