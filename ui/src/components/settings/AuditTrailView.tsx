import React, { useCallback, useEffect, useState } from 'react';

import { ArrowPathIcon, ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline';
import { Link } from 'react-router';

import useErrorHandler from '../../hooks/useErrorHandler';
import { useSettingsStore } from '../../store/settingsStore';
import type { AuditActionType } from '../../types/audit';
import { Pagination } from '../common/Pagination';
import UserDisplayName from '../common/UserDisplayName';

export const AuditTrailView: React.FC<{ hideTitle?: boolean }> = () => {
  const { handleError, runSafe, createContext } = useErrorHandler('AuditTrailView');
  const {
    auditLogs,
    auditLogsTotalCount,
    auditLogsCurrentPage,
    auditLogsPageSize,
    auditLogsTotalPages,
    isLoading,
    fetchAuditLogs,
    setAuditLogsPage,
    setAuditLogsPageSize,
  } = useSettingsStore();
  const [filters] = useState<{
    actionType?: AuditActionType;
    search?: string;
  }>({});

  // Load audit logs on mount
  useEffect(() => {
    void loadAuditLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadAuditLogs = useCallback(async () => {
    const [, error] = await runSafe(
      fetchAuditLogs(filters),
      'loadAuditLogs',
      createContext('loading audit logs')
    );

    if (error) {
      handleError(error, createContext('loading audit logs'));
    }
  }, [filters, fetchAuditLogs, runSafe, handleError, createContext]);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const getSourceBadgeClasses = (source: string) => {
    const base = 'px-2 py-0.5 rounded text-xs font-medium uppercase';
    switch (source) {
      case 'ui':
        return `${base} bg-blue-900/30 text-blue-400 border border-blue-700`;
      case 'rest_api':
        return `${base} bg-purple-900/30 text-purple-400 border border-purple-700`;
      case 'mcp':
        return `${base} bg-green-900/30 text-green-400 border border-green-700`;
      default:
        return `${base} bg-gray-700 text-gray-300 border border-gray-600`;
    }
  };

  const getActionTypeBadge = (actionType: AuditActionType, result?: 'success' | 'error') => {
    const baseClasses = 'px-2 py-1 rounded-full text-xs font-medium';

    if (result === 'error') {
      return `${baseClasses} bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400`;
    }

    switch (actionType) {
      case 'create':
        return `${baseClasses} bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400`;
      case 'update':
        return `${baseClasses} bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400`;
      case 'delete':
        return `${baseClasses} bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400`;
      case 'execute':
        return `${baseClasses} bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400`;
      case 'navigate':
        return `${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300`;
      default:
        return `${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300`;
    }
  };

  const getResultBadge = (result?: 'success' | 'error') => {
    if (!result) return null;

    const baseClasses = 'px-2 py-1 rounded-full text-xs font-medium';

    if (result === 'success') {
      return (
        <span
          className={`${baseClasses} bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400`}
        >
          Success
        </span>
      );
    }

    return (
      <span
        className={`${baseClasses} bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400`}
      >
        Error
      </span>
    );
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-100">System Audit Trail</h2>
          <p className="text-sm text-gray-400 mt-1">Track all user actions and system changes</p>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="audit-page-size" className="text-sm text-gray-400">
            Show:
          </label>
          <select
            id="audit-page-size"
            value={auditLogsPageSize}
            onChange={(e) => setAuditLogsPageSize(Number(e.target.value))}
            className="bg-dark-700 border border-gray-600 text-gray-100 text-sm rounded-md px-2 py-1 focus:ring-primary focus:border-primary"
          >
            <option value="10">10</option>
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
          <span className="text-sm text-gray-400">per page</span>
        </div>
      </div>

      {/* Top Pagination */}
      {auditLogsTotalCount > 0 && (
        <Pagination
          currentPage={auditLogsCurrentPage}
          totalPages={auditLogsTotalPages}
          totalItems={auditLogsTotalCount}
          itemsPerPage={auditLogsPageSize}
          onPageChange={setAuditLogsPage}
        />
      )}

      {/* Table */}
      <div className="bg-gray-800/30 border border-gray-700 rounded-lg overflow-hidden overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-700">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
                Timestamp
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
                User
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
                Action
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
                Details
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
                Context
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {isLoading && auditLogs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-400">
                  <ArrowPathIcon className="h-6 w-6 animate-spin mx-auto mb-2" />
                  Loading audit logs...
                </td>
              </tr>
            )}
            {!isLoading && auditLogs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-400">
                  No audit logs found.
                </td>
              </tr>
            )}
            {auditLogs.length > 0 &&
              auditLogs.map((log) => (
                <tr key={log.id} className="hover:bg-gray-800/30">
                  {/* Timestamp */}
                  <td className="px-6 py-4 whitespace-nowrap align-top">
                    <div className="text-sm text-gray-400">{formatDate(log.timestamp)}</div>
                    {log.session_id && (
                      <div
                        className="text-xs text-gray-500 mt-1"
                        title={`Session: ${log.session_id}`}
                      >
                        Session
                      </div>
                    )}
                  </td>

                  {/* User */}
                  <td className="px-6 py-4 whitespace-nowrap align-top">
                    <div className="text-sm font-medium text-gray-100">
                      <UserDisplayName userId={log.user_id} />
                    </div>
                    {log.ip_address && (
                      <div className="text-xs text-gray-500 mt-1" title={log.ip_address}>
                        {log.ip_address}
                      </div>
                    )}
                  </td>

                  {/* Action */}
                  <td className="px-6 py-4 whitespace-nowrap align-top">
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <span className={getActionTypeBadge(log.action_type, log.result)}>
                          {log.action_type}
                        </span>
                        {getResultBadge(log.result)}
                      </div>
                      <div className="text-sm text-gray-100 font-medium">{log.action}</div>
                      {log.method && (
                        <div className="text-xs text-gray-400">
                          <span className="font-mono bg-gray-800 px-1 rounded-sm">
                            {log.method}
                          </span>
                        </div>
                      )}
                    </div>
                  </td>

                  {/* Details */}
                  <td className="px-6 py-4 align-top">
                    <div className="text-sm space-y-1">
                      {log.page_title && log.route && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-400 uppercase">PAGE:</span>
                          <Link
                            to={log.route}
                            className="text-primary hover:text-primary/80 font-medium flex items-center gap-1"
                            title={`Visit ${log.route}`}
                          >
                            {log.page_title}
                            <ArrowTopRightOnSquareIcon className="h-3 w-3" />
                          </Link>
                        </div>
                      )}
                      {log.page_title && !log.route && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-400 uppercase">PAGE:</span>
                          <span className="text-gray-100 font-medium">{log.page_title}</span>
                        </div>
                      )}
                      {log.duration_ms !== undefined && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-400 uppercase">DURATION:</span>
                          <span className="text-gray-100">
                            {(log.duration_ms / 1000).toFixed(1)}s
                          </span>
                        </div>
                      )}
                      {log.entity_type && log.entity_name && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-400 uppercase">
                            {log.entity_type}:
                          </span>
                          <span className="text-gray-100 font-medium">{log.entity_name}</span>
                        </div>
                      )}
                      {log.entity_type && log.entity_id && !log.entity_name && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-gray-400 uppercase">
                            {log.entity_type}:
                          </span>
                          <span
                            className="text-xs text-gray-500 font-mono truncate max-w-xs"
                            title={log.entity_id}
                          >
                            {log.entity_id}
                          </span>
                        </div>
                      )}
                      {log.params && Object.keys(log.params).length > 0 && (
                        <div className="text-xs text-gray-500">
                          <details className="cursor-pointer">
                            <summary className="hover:text-gray-400">
                              Parameters ({Object.keys(log.params).length})
                            </summary>
                            <pre className="mt-1 p-2 bg-gray-900/50 rounded-sm text-xs overflow-x-auto max-w-md">
                              {JSON.stringify(log.params, null, 2)}
                            </pre>
                          </details>
                        </div>
                      )}
                      {log.error_message && (
                        <div className="text-xs text-red-400 mt-1" title={log.error_message}>
                          Error: {log.error_message}
                        </div>
                      )}
                    </div>
                  </td>

                  {/* Context */}
                  <td className="px-6 py-4 whitespace-nowrap align-top">
                    <div className="text-sm space-y-1">
                      {log.source && (
                        <div>
                          <span className={getSourceBadgeClasses(log.source)}>
                            {log.source.replace('_', ' ')}
                          </span>
                        </div>
                      )}
                      {log.component && <div className="text-gray-100">{log.component}</div>}
                      {log.route && (
                        <div className="text-xs text-gray-400 font-mono">{log.route}</div>
                      )}
                      {log.user_agent && (
                        <details className="text-xs text-gray-500 cursor-pointer">
                          <summary className="hover:text-gray-400">User Agent</summary>
                          <div className="mt-1 max-w-xs wrap-break-word">{log.user_agent}</div>
                        </details>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {auditLogsTotalCount > 0 && (
        <Pagination
          currentPage={auditLogsCurrentPage}
          totalPages={auditLogsTotalPages}
          totalItems={auditLogsTotalCount}
          itemsPerPage={auditLogsPageSize}
          onPageChange={setAuditLogsPage}
        />
      )}
    </div>
  );
};
