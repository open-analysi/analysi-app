/* eslint-disable sonarjs/cognitive-complexity, sonarjs/no-nested-conditional, sonarjs/no-duplicate-string, sonarjs/no-nested-functions, @typescript-eslint/no-redundant-type-constituents, @typescript-eslint/no-floating-promises, @typescript-eslint/no-misused-promises, jsx-a11y/label-has-associated-control */
import React, { useCallback, useEffect, useState, useRef } from 'react';

import {
  ChevronDownIcon,
  ChevronUpIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  FunnelIcon,
} from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router';

import ErrorBoundary from '../components/common/ErrorBoundary';
import useErrorHandler from '../hooks/useErrorHandler';
import { usePageTracking } from '../hooks/usePageTracking';
import { useAlertStore } from '../store/alertStore';
import { componentStyles } from '../styles/components';
import type { AlertSeverity, AlertStatus, Disposition } from '../types/alert';

// Severity badge component
const SeverityBadge: React.FC<{ severity: AlertSeverity }> = ({ severity }) => {
  const colorClasses = {
    critical: 'bg-red-900 text-red-300 border-red-700',
    high: 'bg-orange-900 text-orange-300 border-orange-700',
    medium: 'bg-yellow-900 text-yellow-300 border-yellow-700',
    low: 'bg-blue-900 text-blue-300 border-blue-700',
    info: 'bg-gray-700 text-gray-300 border-gray-600',
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-md border ${colorClasses[severity]}`}>
      {severity.toUpperCase()}
    </span>
  );
};

// Analysis status badge component
const AnalysisStatusBadge: React.FC<{ status: AlertStatus | string }> = ({ status }) => {
  // Complete status mapping based on docs/AlertAnalysisExecutionFlow.md
  const statusConfig: Record<string, { label: string; class: string }> = {
    // Not analyzed states
    not_analyzed: { label: 'Not Analyzed', class: 'bg-gray-700 text-gray-300 border-gray-600' },
    new: { label: 'Not Analyzed', class: 'bg-gray-700 text-gray-300 border-gray-600' }, // Alias

    // In-progress states
    analyzing: {
      label: 'Analyzing',
      class: 'bg-blue-900 text-blue-300 border-blue-700 animate-pulse',
    },
    in_progress: {
      label: 'Analyzing',
      class: 'bg-blue-900 text-blue-300 border-blue-700 animate-pulse',
    }, // Alias

    // Completed states
    analyzed: { label: 'Analyzed', class: 'bg-green-900 text-green-300 border-green-700' },
    completed: { label: 'Analyzed', class: 'bg-green-900 text-green-300 border-green-700' }, // Alias

    // Failed states
    analysis_failed: { label: 'Analysis Failed', class: 'bg-red-900 text-red-300 border-red-700' },
    failed: { label: 'Analysis Failed', class: 'bg-red-900 text-red-300 border-red-700' }, // Alias

    // Cancelled state
    cancelled: { label: 'Cancelled', class: 'bg-yellow-900 text-yellow-300 border-yellow-700' },
  };

  const config = statusConfig[status] || statusConfig.not_analyzed;
  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-md border ${config.class}`}>
      {config.label}
    </span>
  );
};

// Disposition badge component with actual database colors
const DispositionBadge: React.FC<{
  category?: string;
  displayName?: string;
  confidence?: number;
  disposition?: Disposition;
}> = ({ displayName, confidence, disposition }) => {
  if (!displayName) return null;

  // Map database colors to Tailwind classes for better contrast
  const getColorClass = () => {
    if (!disposition?.color_name) {
      return 'bg-gray-700 text-gray-300 border-gray-600';
    }

    // Use the color_name from database to map to high-contrast Tailwind classes
    const colorMap: Record<string, string> = {
      red: 'bg-red-900 text-red-300 border-red-700',
      orange: 'bg-orange-900 text-orange-300 border-orange-700',
      purple: 'bg-purple-900 text-purple-300 border-purple-700',
      yellow: 'bg-yellow-900 text-yellow-300 border-yellow-700',
      blue: 'bg-blue-900 text-blue-300 border-blue-700',
      green: 'bg-green-900 text-green-300 border-green-700',
      gray: 'bg-gray-700 text-gray-300 border-gray-600',
    };

    return colorMap[disposition.color_name] || 'bg-gray-700 text-gray-300 border-gray-600';
  };

  return (
    <div className="flex items-center gap-2">
      <span className={`px-2 py-1 text-xs font-medium rounded-md border ${getColorClass()}`}>
        {displayName}
      </span>
      {confidence != null && <span className="text-xs text-gray-400">{confidence}%</span>}
    </div>
  );
};

export const AlertsPage: React.FC = () => {
  const navigate = useNavigate();
  const { error: errorHandler, clearError } = useErrorHandler('AlertsPage');

  // Track page views
  usePageTracking('Alert Listing', 'AlertsPage');

  // Store state and actions
  const {
    alerts,
    dispositions,
    total,
    limit,
    offset,
    sortBy,
    sortOrder,
    isLoadingAlerts,
    error,
    fetchAlerts,
    fetchAlertsSilent,
    fetchDispositions,
    setFilters,
    setSorting,
    setPagination,
    clearError: clearStoreError,
  } = useAlertStore();

  // Local state
  const [showFilters, setShowFilters] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSeverities, setSelectedSeverities] = useState<AlertSeverity[]>([]);
  const [selectedStatus, setSelectedStatus] = useState<AlertStatus | ''>('');
  const [minConfidence, setMinConfidence] = useState<number | undefined>();
  const [maxConfidence, setMaxConfidence] = useState<number | undefined>();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const refreshIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasLoadedData = useRef(false); // Prevent double-loading in React Strict Mode
  const autoRefreshStarted = useRef(false); // Track if auto-refresh has been started

  // Load initial data
  useEffect(() => {
    // Prevent double-loading in React Strict Mode (development)
    if (hasLoadedData.current) {
      return;
    }
    hasLoadedData.current = true;

    void fetchAlerts();
    void fetchDispositions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only fetch once on mount - Zustand functions are stable

  // Auto-refresh effect with silent updates - starts 30 seconds after initial load
  useEffect(() => {
    const startAutoRefresh = () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
      }

      if (autoRefresh) {
        // Start auto-refresh 30 seconds after the initial load
        const startDelay = autoRefreshStarted.current ? 0 : 30000;
        autoRefreshStarted.current = true;

        setTimeout(() => {
          refreshIntervalRef.current = setInterval(() => {
            void fetchAlertsSilent();
          }, 30000); // Refresh every 30 seconds silently
        }, startDelay);
      }
    };

    startAutoRefresh();

    // Cleanup interval on unmount or when conditions change
    return () => {
      if (refreshIntervalRef.current) {
        clearInterval(refreshIntervalRef.current);
        refreshIntervalRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh]); // Only depend on autoRefresh toggle - Zustand functions are stable

  // Apply filters
  const handleApplyFilters = useCallback(() => {
    setFilters({
      search: searchTerm || undefined,
      severity: selectedSeverities.length > 0 ? selectedSeverities : undefined,
      analysis_status: selectedStatus || undefined,
      min_confidence: minConfidence,
      max_confidence: maxConfidence,
    });
  }, [searchTerm, selectedSeverities, selectedStatus, minConfidence, maxConfidence, setFilters]);

  // Clear filters
  const handleClearFilters = () => {
    setSearchTerm('');
    setSelectedSeverities([]);
    setSelectedStatus('');
    setMinConfidence(undefined);
    setMaxConfidence(undefined);
    setFilters({});
  };

  // Handle sorting
  const handleSort = (column: 'severity' | 'created_at' | 'confidence' | 'analyzed_at') => {
    if (sortBy === column) {
      setSorting(column, sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSorting(column, 'desc');
    }
  };

  // Handle pagination
  const handlePageChange = (newPage: number) => {
    setPagination(newPage * limit, limit);
  };

  // Navigate to alert details
  const handleAlertClick = (alertId: string) => {
    navigate(`/alerts/${alertId}`);
  };

  // Format date
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Calculate current page
  const currentPage = Math.floor(offset / limit);
  const totalPages = Math.ceil(total / limit);

  // Error display
  const renderError = () => {
    const errorMessage = error || errorHandler.message;
    if (!errorMessage) return null;

    return (
      <div className="mb-6 bg-red-900/30 border border-red-700 p-4 rounded-md">
        <div className="flex items-center">
          <ExclamationTriangleIcon className="h-5 w-5 text-red-500 mr-2" />
          <div className="flex-1">
            <p className="text-gray-100">{errorMessage}</p>
          </div>
          <button
            onClick={() => {
              clearStoreError();
              clearError();
            }}
            className="text-gray-400 hover:text-gray-100 text-sm"
          >
            Dismiss
          </button>
        </div>
      </div>
    );
  };

  return (
    <ErrorBoundary component="AlertsPage">
      <div className={componentStyles.pageBackground}>
        <div className="py-6 px-4 sm:px-6 md:px-8">
          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
            <div>
              <h1 className="text-2xl font-semibold text-white">Alert Analysis Queue</h1>
              <p className="mt-1 text-sm text-gray-400">
                Alerts pending analysis and those already analyzed
              </p>
            </div>
            <div className="mt-4 md:mt-0 flex items-center gap-3">
              {/* Auto-refresh controls */}
              <label className="flex items-center gap-2 text-sm text-gray-300">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  className="rounded-sm border-gray-600 text-primary focus:ring-primary bg-gray-700"
                />
                Auto-refresh
              </label>
              {autoRefresh && (
                <div className="flex items-center gap-1 text-xs text-blue-400">
                  <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-blue-400"></div>
                  Live
                </div>
              )}
              <button
                onClick={() => fetchAlerts()}
                disabled={isLoadingAlerts}
                className="flex items-center px-3 py-2 text-sm bg-dark-700 text-gray-100 rounded-md hover:bg-dark-600 disabled:opacity-50"
              >
                <ArrowPathIcon
                  className={`h-4 w-4 mr-2 ${isLoadingAlerts ? 'animate-spin' : ''}`}
                />
                Refresh
              </button>
              <button
                onClick={() => setShowFilters(!showFilters)}
                className="flex items-center px-3 py-2 text-sm bg-dark-700 text-gray-100 rounded-md hover:bg-dark-600"
              >
                <FunnelIcon className="h-4 w-4 mr-2" />
                Filters
                {showFilters ? (
                  <ChevronUpIcon className="ml-2 h-4 w-4" />
                ) : (
                  <ChevronDownIcon className="ml-2 h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          {renderError()}

          {/* Filters */}
          {showFilters && (
            <div className="mb-6 p-4 bg-dark-800 border border-gray-700 rounded-lg">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Search */}
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1">Search</label>
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Search alerts..."
                    className="w-full px-3 py-2 bg-dark-900 border border-gray-700 rounded-md text-gray-100 placeholder-gray-500 focus:outline-hidden focus:ring-2 focus:ring-primary"
                  />
                </div>

                {/* Severity */}
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1">Severity</label>
                  <select
                    multiple
                    value={selectedSeverities}
                    onChange={(e) => {
                      const selected = Array.from(
                        e.target.selectedOptions,
                        (option) => option.value as AlertSeverity
                      );
                      setSelectedSeverities(selected);
                    }}
                    className="w-full px-3 py-2 bg-dark-900 border border-gray-700 rounded-md text-gray-100 focus:outline-hidden focus:ring-2 focus:ring-primary"
                  >
                    <option value="critical">Critical</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                    <option value="info">Info</option>
                  </select>
                </div>

                {/* Analysis Status */}
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1">
                    Analysis Status
                  </label>
                  <select
                    value={selectedStatus}
                    onChange={(e) => setSelectedStatus(e.target.value as AlertStatus | '')}
                    className="w-full px-3 py-2 bg-dark-900 border border-gray-700 rounded-md text-gray-100 focus:outline-hidden focus:ring-2 focus:ring-primary"
                  >
                    <option value="">All</option>
                    <option value="not_analyzed">Not Analyzed</option>
                    <option value="analyzing">Analyzing</option>
                    <option value="analyzed">Analyzed</option>
                  </select>
                </div>

                {/* Confidence Range */}
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1">
                    Confidence Range
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      value={minConfidence || ''}
                      onChange={(e) =>
                        setMinConfidence(e.target.value ? Number(e.target.value) : undefined)
                      }
                      placeholder="Min"
                      min="0"
                      max="100"
                      className="w-1/2 px-3 py-2 bg-dark-900 border border-gray-700 rounded-md text-gray-100 placeholder-gray-500 focus:outline-hidden focus:ring-2 focus:ring-primary"
                    />
                    <input
                      type="number"
                      value={maxConfidence || ''}
                      onChange={(e) =>
                        setMaxConfidence(e.target.value ? Number(e.target.value) : undefined)
                      }
                      placeholder="Max"
                      min="0"
                      max="100"
                      className="w-1/2 px-3 py-2 bg-dark-900 border border-gray-700 rounded-md text-gray-100 placeholder-gray-500 focus:outline-hidden focus:ring-2 focus:ring-primary"
                    />
                  </div>
                </div>
              </div>

              <div className="mt-4 flex justify-end gap-3">
                <button
                  onClick={handleClearFilters}
                  className="px-4 py-2 text-sm text-gray-300 hover:text-gray-100"
                >
                  Clear
                </button>
                <button
                  onClick={handleApplyFilters}
                  className="px-4 py-2 text-sm bg-primary text-white rounded-md hover:bg-primary/90"
                >
                  Apply Filters
                </button>
              </div>
            </div>
          )}

          {/* Results summary */}
          <div className="mb-4 text-sm text-gray-400">
            Showing {offset + 1}-{Math.min(offset + limit, total)} of {total} alerts
          </div>

          {/* Table */}
          <div className="bg-dark-800 border border-gray-700/30 rounded-lg overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-700">
                <thead className="bg-dark-700">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                      ID
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                      Title
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                      Summary
                    </th>
                    <th
                      className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-100 select-none"
                      onClick={() => handleSort('severity')}
                      title="Click to sort by severity"
                    >
                      <div className="flex items-center gap-1">
                        Severity
                        <span className="text-gray-500">
                          {sortBy === 'severity' ? (sortOrder === 'asc' ? '↑' : '↓') : '↕'}
                        </span>
                      </div>
                    </th>
                    <th
                      className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-100 select-none"
                      onClick={() => handleSort('analyzed_at')}
                      title="Click to sort by analysis time"
                    >
                      <div className="flex items-center gap-1">
                        Status
                        <span className="text-gray-500">
                          {sortBy === 'analyzed_at' ? (sortOrder === 'asc' ? '↑' : '↓') : '↕'}
                        </span>
                      </div>
                    </th>
                    <th
                      className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-100 select-none"
                      onClick={() => handleSort('confidence')}
                      title="Click to sort by confidence"
                    >
                      <div className="flex items-center gap-1">
                        Disposition
                        <span className="text-gray-500">
                          {sortBy === 'confidence' ? (sortOrder === 'asc' ? '↑' : '↓') : '↕'}
                        </span>
                      </div>
                    </th>
                    <th
                      className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-100 select-none"
                      onClick={() => handleSort('created_at')}
                      title="Click to sort by creation time"
                    >
                      <div className="flex items-center gap-1">
                        Created
                        <span className="text-gray-500">
                          {sortBy === 'created_at' ? (sortOrder === 'asc' ? '↑' : '↓') : '↕'}
                        </span>
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-dark-900 divide-y divide-gray-700/50">
                  {isLoadingAlerts ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                        <ArrowPathIcon className="h-6 w-6 animate-spin mx-auto mb-2" />
                        Loading alerts...
                      </td>
                    </tr>
                  ) : alerts.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                        No alerts found
                      </td>
                    </tr>
                  ) : (
                    alerts.map((alert) => (
                      <tr
                        key={alert.alert_id}
                        onClick={() => handleAlertClick(alert.alert_id)}
                        className="hover:bg-dark-700 cursor-pointer transition-colors"
                      >
                        <td className="px-4 py-3 text-sm text-gray-100">
                          {alert.human_readable_id}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-100 font-medium">
                          {alert.title}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-400 max-w-md">
                          <div className="line-clamp-2">{alert.short_summary || '-'}</div>
                        </td>
                        <td className="px-4 py-3">
                          <SeverityBadge severity={alert.severity} />
                        </td>
                        <td className="px-4 py-3">
                          <AnalysisStatusBadge status={alert.analysis_status} />
                        </td>
                        <td className="px-4 py-3">
                          <DispositionBadge
                            category={alert.current_disposition_category ?? undefined}
                            displayName={alert.current_disposition_display_name ?? undefined}
                            confidence={alert.current_disposition_confidence ?? undefined}
                            disposition={dispositions.find(
                              (d) => d.display_name === alert.current_disposition_display_name
                            )}
                          />
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-400">
                          {formatDate(alert.created_at)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="bg-dark-900 px-4 py-3 flex items-center justify-between border-t border-gray-700">
                <div className="flex gap-2">
                  <button
                    onClick={() => handlePageChange(currentPage - 1)}
                    disabled={currentPage === 0}
                    className="px-3 py-1 text-sm bg-dark-700 text-gray-100 rounded-md hover:bg-dark-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <span className="px-3 py-1 text-sm text-gray-400">
                    Page {currentPage + 1} of {totalPages}
                  </span>
                  <button
                    onClick={() => handlePageChange(currentPage + 1)}
                    disabled={currentPage >= totalPages - 1}
                    className="px-3 py-1 text-sm bg-dark-700 text-gray-100 rounded-md hover:bg-dark-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
};
