import React, { useCallback, useEffect, useState } from 'react';

import { PlusIcon, TrashIcon, ArrowPathIcon } from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import type { AnalysisGroup, AnalysisGroupCreate } from '../../types/settings';

export const AnalysisGroups: React.FC = () => {
  const { handleError, runSafe, createContext } = useErrorHandler('AnalysisGroups');

  const [analysisGroups, setAnalysisGroups] = useState<AnalysisGroup[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newGroupTitle, setNewGroupTitle] = useState('');

  const loadAnalysisGroups = useCallback(async () => {
    setIsLoading(true);
    const [result, error] = await runSafe(
      backendApi.getAnalysisGroups(),
      'loadAnalysisGroups',
      createContext('loading analysis groups')
    );

    if (error) {
      handleError(error, createContext('loading analysis groups'));
    } else if (result) {
      setAnalysisGroups(result.analysis_groups || []);
    }
    setIsLoading(false);
  }, [runSafe, handleError, createContext]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch, setState happens after await
    void loadAnalysisGroups();
  }, [loadAnalysisGroups]);

  const handleCreateGroup = async () => {
    if (!newGroupTitle.trim()) return;

    setIsCreating(true);
    const data: AnalysisGroupCreate = {
      title: newGroupTitle.trim(),
    };

    const [result, error] = await runSafe(
      backendApi.createAnalysisGroup(data),
      'createAnalysisGroup',
      createContext('creating analysis group', { params: { title: newGroupTitle } })
    );

    if (error) {
      handleError(
        error,
        createContext('creating analysis group', { params: { title: newGroupTitle } })
      );
    } else if (result) {
      setNewGroupTitle('');
      setShowCreateForm(false);
      void loadAnalysisGroups();
    }
    setIsCreating(false);
  };

  const handleDeleteGroup = async (id: string, title: string) => {
    if (!confirm(`Are you sure you want to delete "${title}"?`)) return;

    const [, error] = await runSafe(
      backendApi.deleteAnalysisGroup(id),
      'deleteAnalysisGroup',
      createContext('deleting analysis group', { entityId: id, params: { title } })
    );

    if (error) {
      handleError(
        error,
        createContext('deleting analysis group', { entityId: id, params: { title } })
      );
    } else {
      void loadAnalysisGroups();
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-100">Analysis Groups</h2>
          <p className="text-sm text-gray-400 mt-1">
            Manage analysis groups that categorize alerts by rule name
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => void loadAnalysisGroups()}
            disabled={isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 text-white rounded-md hover:bg-gray-600 disabled:opacity-50"
          >
            <ArrowPathIcon className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={() => setShowCreateForm(!showCreateForm)}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90"
          >
            <PlusIcon className="h-4 w-4" />
            New Group
          </button>
        </div>
      </div>

      {/* Create Form */}
      {showCreateForm && (
        <div className="p-4 bg-gray-800/50 border border-gray-700 rounded-lg space-y-4">
          <h3 className="text-lg font-medium text-gray-100">Create New Analysis Group</h3>
          <div className="space-y-2">
            <label htmlFor="groupTitle" className="block text-sm font-medium text-gray-300">
              Title (Rule Name)
            </label>
            <input
              id="groupTitle"
              type="text"
              value={newGroupTitle}
              onChange={(e) => setNewGroupTitle(e.target.value)}
              placeholder="e.g., SOC170 - LFI Attack"
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-gray-100 placeholder-gray-500 focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleCreateGroup();
              }}
            />
          </div>
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => {
                setShowCreateForm(false);
                setNewGroupTitle('');
              }}
              className="px-4 py-2 bg-gray-700 text-white rounded-md hover:bg-gray-600"
            >
              Cancel
            </button>
            <button
              onClick={() => void handleCreateGroup()}
              disabled={!newGroupTitle.trim() || isCreating}
              className="px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90 disabled:opacity-50"
            >
              {isCreating ? 'Creating...' : 'Create'}
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-gray-800/30 border border-gray-700 rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-700">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
                Title
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {isLoading && analysisGroups.length === 0 && (
              <tr>
                <td colSpan={3} className="px-6 py-8 text-center text-gray-400">
                  <ArrowPathIcon className="h-6 w-6 animate-spin mx-auto mb-2" />
                  Loading analysis groups...
                </td>
              </tr>
            )}
            {!isLoading && analysisGroups.length === 0 && (
              <tr>
                <td colSpan={3} className="px-6 py-8 text-center text-gray-400">
                  No analysis groups found. Create one to get started.
                </td>
              </tr>
            )}
            {analysisGroups.length > 0 &&
              analysisGroups.map((group) => (
                <tr key={group.id} className="hover:bg-gray-800/30">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-100">{group.title}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-gray-400">{formatDate(group.created_at)}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => void handleDeleteGroup(group.id, group.title)}
                      className="text-red-400 hover:text-red-300"
                      title="Delete group"
                    >
                      <TrashIcon className="h-5 w-5" />
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Count */}
      {!isLoading && analysisGroups.length > 0 && (
        <div className="text-sm text-gray-400">
          Showing {analysisGroups.length} analysis{' '}
          {analysisGroups.length === 1 ? 'group' : 'groups'}
        </div>
      )}
    </div>
  );
};
