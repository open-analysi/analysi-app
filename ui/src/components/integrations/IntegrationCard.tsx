import React, { useState } from 'react';

import { useNavigate } from 'react-router';

import useErrorHandler from '../../hooks/useErrorHandler';
import { componentStyles } from '../../styles/components';
import { Integration, IntegrationStatus } from '../../types/integration';
import ErrorBoundary from '../common/ErrorBoundary';

interface IntegrationCardProps {
  integration: Integration;
}

export const IntegrationCard: React.FC<IntegrationCardProps> = ({ integration }) => {
  const [isConfiguring, setIsConfiguring] = useState(false);
  const { error, clearError, runSafe } = useErrorHandler('IntegrationCard');
  const navigate = useNavigate();

  // Simulate configuration update
  const handleConfigure = async () => {
    setIsConfiguring(true);

    // Use runSafe to handle potential errors during configuration
    const [,] = await runSafe(
      // Simulate API call with potential error
      new Promise<boolean>((resolve) => {
        setTimeout(() => {
          // Simulate successful configuration
          resolve(true);
        }, 1000);
      }),
      'handleConfigure',
      {
        action: 'configuring integration',
        entityId: integration.id,
        entityType: 'integration',
      }
    );

    setIsConfiguring(false);
  };

  const testConnection = async (integrationId: string) => {
    try {
      setIsConfiguring(true);
      // Simulate API call to test connection
      await new Promise<void>((resolve) => {
        setTimeout(() => {
          resolve();
        }, 2000);
      });
    } catch (error_) {
      console.error(`Error testing connection for ${integrationId}:`, error_);
    } finally {
      setIsConfiguring(false);
    }
  };

  const handleTestClick = (e: React.MouseEvent) => {
    // Prevent the click from bubbling up to the parent card
    e.stopPropagation();
    e.preventDefault();

    // Prevent clicking if already testing
    if (isConfiguring) return;

    void testConnection(integration.id);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Handle keyboard navigation
    if (e.key === 'Enter' || e.key === ' ') {
      void navigate(`/integrations/${integration.id}`);
    }
  };

  return (
    <ErrorBoundary
      component={`IntegrationCard-${integration.id}`}
      fallback={
        <div className="p-3 border border-red-700 bg-red-900/30 rounded-md">
          <p className="text-sm text-red-400">Error displaying integration {integration.name}</p>
        </div>
      }
    >
      <div
        className={`border border-dark-600 rounded-lg p-4 bg-dark-800 hover:bg-dark-700 cursor-pointer transition-colors ${componentStyles.card}`}
        onClick={() => {
          if (!isConfiguring) {
            void navigate(`/integrations/${integration.id}`);
          }
        }}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
      >
        <div className="flex flex-col p-4 bg-dark-800 rounded-lg">
          {error.hasError && (
            <div className="mb-3 p-2 bg-red-900/30 border border-red-700 rounded-sm text-sm">
              <div className="flex justify-between items-center">
                <span className="text-red-400">{error.message}</span>
                <button onClick={clearError} className="text-gray-400 hover:text-gray-200 text-xs">
                  Dismiss
                </button>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-300">{integration.name}</span>
            <div className="flex items-center space-x-3">
              <span
                className={
                  integration.status === IntegrationStatus.Connected
                    ? 'text-green-500'
                    : 'text-red-500'
                }
              >
                {integration.status}
              </span>
              <button
                className={`${componentStyles.primaryButton} ${isConfiguring ? 'opacity-75' : ''}`}
                onClick={() => void handleConfigure()}
                disabled={isConfiguring}
              >
                {isConfiguring ? 'Configuring...' : 'Configure'}
              </button>
            </div>
          </div>
          {integration.description && (
            <p className="text-sm text-gray-400">{integration.description}</p>
          )}
          <div className="mt-3 pt-3 border-t border-dark-600">
            <button
              onClick={handleTestClick}
              className="text-sm px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-gray-200 hover:text-white"
              disabled={isConfiguring}
            >
              {isConfiguring ? 'Testing...' : 'Test Connection'}
            </button>
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
};

export default IntegrationCard;
