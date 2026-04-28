import React, { useCallback, useEffect, useState } from 'react';

import { PlusIcon, TrashIcon, ArrowPathIcon } from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import type { AlertRoutingRule, AlertRoutingRuleCreate, AnalysisGroup } from '../../types/settings';
import type { Workflow } from '../../types/workflow';

export const AlertRoutingRules: React.FC = () => {
  const { handleError, runSafe, createContext } = useErrorHandler('AlertRoutingRules');

  const [rules, setRules] = useState<AlertRoutingRule[]>([]);
  const [analysisGroups, setAnalysisGroups] = useState<AnalysisGroup[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [selectedWorkflowId, setSelectedWorkflowId] = useState('');

  const loadData = useCallback(async () => {
    setIsLoading(true);

    // Load rules, analysis groups, and workflows in parallel
    const [rulesResult, rulesError] = await runSafe(
      backendApi.getAlertRoutingRules(),
      'loadAlertRoutingRules',
      createContext('loading alert routing rules')
    );

    const [groupsResult, groupsError] = await runSafe(
      backendApi.getAnalysisGroups(),
      'loadAnalysisGroups',
      createContext('loading analysis groups')
    );

    const [workflowsResult, workflowsError] = await runSafe(
      backendApi.getWorkflows({}),
      'loadWorkflows',
      createContext('loading workflows')
    );

    if (rulesError) {
      handleError(rulesError, createContext('loading alert routing rules'));
    } else if (rulesResult) {
      setRules(rulesResult.rules || []);
    }

    if (groupsError) {
      handleError(groupsError, createContext('loading analysis groups'));
    } else if (groupsResult) {
      setAnalysisGroups(groupsResult.analysis_groups || []);
    }

    if (workflowsError) {
      handleError(workflowsError, createContext('loading workflows'));
    } else if (workflowsResult) {
      setWorkflows(workflowsResult.workflows || []);
    }

    setIsLoading(false);
  }, [runSafe, handleError, createContext]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetch, setState happens after await
    void loadData();
  }, [loadData]);

  const handleCreateRule = async () => {
    if (!selectedGroupId || !selectedWorkflowId) return;

    setIsCreating(true);
    const data: AlertRoutingRuleCreate = {
      analysis_group_id: selectedGroupId,
      workflow_id: selectedWorkflowId,
    };

    const [result, error] = await runSafe(
      backendApi.createAlertRoutingRule(data),
      'createAlertRoutingRule',
      createContext('creating alert routing rule', {
        params: {
          analysis_group_id: selectedGroupId,
          workflow_id: selectedWorkflowId,
        },
      })
    );

    if (error) {
      handleError(
        error,
        createContext('creating alert routing rule', {
          params: {
            analysis_group_id: selectedGroupId,
            workflow_id: selectedWorkflowId,
          },
        })
      );
    } else if (result) {
      setSelectedGroupId('');
      setSelectedWorkflowId('');
      setShowCreateForm(false);
      void loadData();
    }
    setIsCreating(false);
  };

  const handleDeleteRule = async (id: string) => {
    if (!confirm('Are you sure you want to delete this routing rule?')) return;

    const [, error] = await runSafe(
      backendApi.deleteAlertRoutingRule(id),
      'deleteAlertRoutingRule',
      createContext('deleting alert routing rule', { entityId: id })
    );

    if (error) {
      handleError(error, createContext('deleting alert routing rule', { entityId: id }));
    } else {
      void loadData();
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

  const getGroupTitle = (groupId: string) => {
    const group = analysisGroups.find((g) => g.id === groupId);
    return group?.title || 'Unknown Group';
  };

  const getWorkflowName = (workflowId: string) => {
    const workflow = workflows.find((w) => w.id === workflowId);
    return workflow?.name || 'Unknown Workflow';
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-100">Alert Routing Rules</h2>
          <p className="text-sm text-gray-400 mt-1">
            Map analysis groups to workflows for automated alert processing
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => void loadData()}
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
            New Rule
          </button>
        </div>
      </div>

      {/* Create Form */}
      {showCreateForm && (
        <div className="p-4 bg-gray-800/50 border border-gray-700 rounded-lg space-y-4">
          <h3 className="text-lg font-medium text-gray-100">Create New Routing Rule</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label htmlFor="analysisGroup" className="block text-sm font-medium text-gray-300">
                Analysis Group
              </label>
              <select
                id="analysisGroup"
                value={selectedGroupId}
                onChange={(e) => setSelectedGroupId(e.target.value)}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-gray-100 focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
              >
                <option value="">Select an analysis group...</option>
                {analysisGroups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.title}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <label htmlFor="workflow" className="block text-sm font-medium text-gray-300">
                Workflow
              </label>
              <select
                id="workflow"
                value={selectedWorkflowId}
                onChange={(e) => setSelectedWorkflowId(e.target.value)}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-gray-100 focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
              >
                <option value="">Select a workflow...</option>
                {workflows.map((workflow) => (
                  <option key={workflow.id} value={workflow.id}>
                    {workflow.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => {
                setShowCreateForm(false);
                setSelectedGroupId('');
                setSelectedWorkflowId('');
              }}
              className="px-4 py-2 bg-gray-700 text-white rounded-md hover:bg-gray-600"
            >
              Cancel
            </button>
            <button
              onClick={() => void handleCreateRule()}
              disabled={!selectedGroupId || !selectedWorkflowId || isCreating}
              className="px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90 disabled:opacity-50"
            >
              {isCreating ? 'Creating...' : 'Create'}
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-gray-800/30 border border-gray-700 rounded-lg overflow-hidden overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-700 table-fixed">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-2/5">
                Analysis Group
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-2/5">
                Workflow
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-1/6">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-300 uppercase tracking-wider w-16">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {isLoading && rules.length === 0 && (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-gray-400">
                  <ArrowPathIcon className="h-6 w-6 animate-spin mx-auto mb-2" />
                  Loading routing rules...
                </td>
              </tr>
            )}
            {!isLoading && rules.length === 0 && (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-gray-400">
                  No routing rules found. Create one to get started.
                </td>
              </tr>
            )}
            {rules.length > 0 &&
              rules.map((rule) => (
                <tr key={rule.id} className="hover:bg-gray-800/30">
                  <td className="px-6 py-4">
                    <div className="text-sm font-medium text-gray-100 wrap-break-word">
                      {getGroupTitle(rule.analysis_group_id)}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-100 wrap-break-word">
                      {getWorkflowName(rule.workflow_id)}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm text-gray-400">{formatDate(rule.created_at)}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => void handleDeleteRule(rule.id)}
                      className="text-red-400 hover:text-red-300"
                      title="Delete rule"
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
      {!isLoading && rules.length > 0 && (
        <div className="text-sm text-gray-400">
          Showing {rules.length} routing {rules.length === 1 ? 'rule' : 'rules'}
        </div>
      )}
    </div>
  );
};
