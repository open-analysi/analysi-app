import React from 'react';

import { componentStyles } from '../../styles/components';
import { IntegrationGroup as IIntegrationGroup } from '../../types/integration';
import ErrorBoundary from '../common/ErrorBoundary';

import IntegrationCard from './IntegrationCard';

interface IntegrationGroupProps {
  group: IIntegrationGroup;
}

export const IntegrationGroup: React.FC<IntegrationGroupProps> = ({ group }) => {
  return (
    <ErrorBoundary
      component={`IntegrationGroup-${group.type}`}
      fallback={
        <div className={componentStyles.card}>
          <div className="p-4 border border-red-700 bg-red-900/30 rounded-md">
            <h3 className="text-lg font-medium text-red-400">
              Could not display {group.type} integrations
            </h3>
          </div>
        </div>
      }
    >
      <div className={componentStyles.card}>
        <div className="mb-4">
          <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100">{group.type}</h2>
          {group.description && <p className="mt-1 text-sm text-gray-500">{group.description}</p>}
        </div>
        <div className="space-y-3">
          {group.integrations.map((integration) => (
            <IntegrationCard key={integration.id} integration={integration} />
          ))}
        </div>
      </div>
    </ErrorBoundary>
  );
};
