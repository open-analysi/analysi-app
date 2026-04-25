import {
  ArrowLeftIcon,
  ArrowsRightLeftIcon,
  BoltIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';
import { useSearchParams } from 'react-router';

import ErrorBoundary from '../components/common/ErrorBoundary';
import { AlertRoutingRules } from '../components/settings/AlertRoutingRules';
import { AnalysisGroups } from '../components/settings/AnalysisGroups';
import { ControlEventSection } from '../components/settings/ControlEventSection';
import { useUrlState } from '../hooks/useUrlState';
import { componentStyles } from '../styles/components';

const SECTIONS = [
  {
    id: 'analysis-groups',
    title: 'Analysis Groups',
    description:
      'The set of alert types the system supports. Each entry typically has its own runbook and investigation workflow. Remove an entry to trigger a full re-generation of its workflow the next time an alert of that type arrives.',
    icon: UserGroupIcon,
  },
  {
    id: 'alert-routing',
    title: 'Alert Routing Rules',
    description:
      'Map Analysis Groups to Workflows. Alerts triggered by the same rule will execute the same workflow. Configure which workflow fires for each alert type here.',
    icon: ArrowsRightLeftIcon,
  },
  {
    id: 'control-events',
    title: 'Event Reaction Rules',
    description:
      'Run tasks or workflows automatically when a system event fires. Example: when a disposition is marked ready (disposition:ready), trigger a Slack notification task to alert the team.',
    icon: BoltIcon,
  },
] as const;

type SectionId = (typeof SECTIONS)[number]['id'];

const Settings = () => {
  const [section] = useUrlState<string>('section', '');
  const [, setSearchParams] = useSearchParams();

  const activeSection = SECTIONS.find((s) => s.id === section);

  const handleSelectSection = (id: SectionId) => {
    setSearchParams(
      (prev) => {
        prev.set('section', id);
        prev.delete('tab');
        return prev;
      },
      { replace: true }
    );
  };

  const handleBack = () => {
    setSearchParams(
      (prev) => {
        prev.delete('section');
        prev.delete('tab');
        return prev;
      },
      { replace: true }
    );
  };

  return (
    <ErrorBoundary
      component="SettingsPage"
      fallback={
        <div className={componentStyles.pageBackground}>
          <div className="py-6 px-4 sm:px-6 md:px-8">
            <div className="p-6 border border-red-700 bg-red-900/30 rounded-md">
              <h2 className="text-xl font-semibold mb-2 text-gray-100">Error loading settings</h2>
              <p className="text-gray-300 mb-4">There was an error rendering the settings page.</p>
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
      <div className={componentStyles.pageBackground}>
        <div className="py-6 px-4 sm:px-6 md:px-8">
          {/* Header */}
          {!activeSection ? (
            <div className="mb-6">
              <h1 className="text-2xl font-semibold text-gray-100">Settings</h1>
              <p className="mt-1 text-sm text-gray-500">Manage system configuration</p>
            </div>
          ) : (
            <div className="mb-6">
              <div className="flex items-center gap-2">
                <button
                  onClick={handleBack}
                  className="text-gray-400 hover:text-gray-200 transition-colors"
                  aria-label="Back to Settings"
                >
                  <ArrowLeftIcon className="h-4 w-4" />
                </button>
                <button
                  onClick={handleBack}
                  className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
                >
                  Settings
                </button>
                <span className="text-sm text-gray-600">/</span>
                <span className="text-sm text-gray-200">{activeSection.title}</span>
              </div>
            </div>
          )}

          {/* Content */}
          {!activeSection ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {SECTIONS.map((s) => {
                const Icon = s.icon;
                return (
                  <button
                    key={s.id}
                    onClick={() => handleSelectSection(s.id)}
                    className="text-left p-4 rounded-lg border border-gray-700 bg-dark-800 hover:border-primary hover:bg-dark-700 transition-colors group"
                  >
                    <div className="flex items-start gap-3">
                      <div className="shrink-0 mt-0.5 w-8 h-8 rounded-md bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                        <Icon className="w-4 h-4 text-primary" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-100 group-hover:text-white">
                          {s.title}
                        </div>
                        <div className="text-xs text-gray-500 mt-1 group-hover:text-gray-400">
                          {s.description}
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          ) : (
            <ErrorBoundary
              component={`Setting-${activeSection.title}`}
              fallback={
                <div className="p-4 border border-red-700 bg-red-900/30 rounded-md">
                  <h3 className="text-lg font-medium text-red-400 mb-2">
                    Could not display {activeSection.title}
                  </h3>
                  <p className="text-sm text-gray-300 mb-4">
                    There was an error loading this settings panel.
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
              {section === 'analysis-groups' && <AnalysisGroups />}
              {section === 'alert-routing' && <AlertRoutingRules />}
              {section === 'control-events' && <ControlEventSection />}
            </ErrorBoundary>
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default Settings;
