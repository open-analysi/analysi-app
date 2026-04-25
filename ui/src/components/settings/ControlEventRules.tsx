import React, { useCallback, useEffect, useState } from 'react';

import {
  ArrowPathIcon,
  PencilIcon,
  PlusIcon,
  TrashIcon,
  BoltIcon,
} from '@heroicons/react/24/outline';
import { Link } from 'react-router';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import type {
  ControlEventChannel,
  ControlEventRule,
  ControlEventRuleCreate,
} from '../../types/controlEvents';
import type { Task } from '../../types/knowledge';
import type { Workflow } from '../../types/workflow';

const EMPTY_FORM = {
  name: '',
  channel: '',
  targetType: 'task' as 'task' | 'workflow',
  targetId: '',
  configJson: '{}',
  enabled: true,
};

function ChannelBadge({
  channel,
  channels,
}: {
  readonly channel: string;
  readonly channels: readonly ControlEventChannel[];
}) {
  const meta = channels.find((c) => c.channel === channel);
  const isSystem = meta?.type === 'system';
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        isSystem ? 'bg-indigo-500/20 text-indigo-300' : 'bg-gray-500/20 text-gray-400'
      }`}
    >
      {channel}
    </span>
  );
}

function EnabledToggle({
  enabled,
  onChange,
}: {
  readonly enabled: boolean;
  readonly onChange: (val: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
        enabled ? 'bg-primary' : 'bg-gray-600'
      }`}
      aria-pressed={enabled}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          enabled ? 'translate-x-4' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

export const ControlEventRules: React.FC = () => {
  const { handleError, runSafe, createContext } = useErrorHandler('ControlEventRules');

  const [rules, setRules] = useState<ControlEventRule[]>([]);
  const [channels, setChannels] = useState<ControlEventChannel[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [configError, setConfigError] = useState('');

  const [form, setForm] = useState(EMPTY_FORM);

  const loadData = useCallback(async () => {
    const [rulesResult] = await runSafe(
      backendApi.getControlEventRules() as Promise<{ rules: ControlEventRule[] }>,
      'loadRules',
      createContext('loading rules')
    );
    const [channelsResult] = await runSafe(
      backendApi.getControlEventChannels() as Promise<{ channels: ControlEventChannel[] }>,
      'loadChannels',
      createContext('loading channels')
    );
    const [tasksResult] = await runSafe(
      backendApi.getTasks({ limit: 100 }) as Promise<{ tasks: Task[]; total: number }>,
      'loadTasks',
      createContext('loading tasks')
    );
    const [workflowsResult] = await runSafe(
      backendApi.getWorkflows({}) as Promise<{ workflows: Workflow[] }>,
      'loadWorkflows',
      createContext('loading workflows')
    );

    if (rulesResult) setRules(rulesResult.rules || []);
    if (channelsResult) setChannels(channelsResult.channels || []);
    if (tasksResult) setTasks(tasksResult.tasks || []);
    if (workflowsResult) setWorkflows(workflowsResult.workflows || []);
    setIsLoading(false);
  }, [runSafe, createContext]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadData();
  }, [loadData]);

  const openCreateForm = () => {
    setForm(EMPTY_FORM);
    setEditingRuleId(null);
    setConfigError('');
    setShowForm(true);
  };

  const openEditForm = (rule: ControlEventRule) => {
    setForm({
      name: rule.name,
      channel: rule.channel,
      targetType: rule.target_type as 'task' | 'workflow',
      targetId: rule.target_id,
      configJson: JSON.stringify(rule.config, null, 2),
      enabled: rule.enabled,
    });
    setEditingRuleId(rule.id);
    setConfigError('');
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingRuleId(null);
    setForm(EMPTY_FORM);
    setConfigError('');
  };

  const handleSave = async () => {
    if (!form.name.trim() || !form.channel || !form.targetId) return;

    let config: Record<string, unknown> = {};
    if (form.configJson.trim() && form.configJson.trim() !== '{}') {
      try {
        config = JSON.parse(form.configJson) as Record<string, unknown>;
      } catch {
        setConfigError('Invalid JSON — please fix before saving');
        return;
      }
    }
    setConfigError('');
    setIsSaving(true);

    const payload: ControlEventRuleCreate = {
      name: form.name.trim(),
      channel: form.channel,
      target_type: form.targetType,
      target_id: form.targetId,
      enabled: form.enabled,
      config,
    };

    const apiCall = editingRuleId
      ? backendApi.updateControlEventRule(editingRuleId, payload)
      : backendApi.createControlEventRule(payload);

    const [, error] = await runSafe(
      apiCall,
      editingRuleId ? 'updateRule' : 'createRule',
      createContext(editingRuleId ? 'updating rule' : 'creating rule')
    );

    if (error) {
      handleError(error, createContext(editingRuleId ? 'updating rule' : 'creating rule'));
    } else {
      closeForm();
      setIsLoading(true);
      void loadData();
    }
    setIsSaving(false);
  };

  const handleToggleEnabled = async (rule: ControlEventRule) => {
    // Optimistic update
    setRules((prev) => prev.map((r) => (r.id === rule.id ? { ...r, enabled: !r.enabled } : r)));
    const [, error] = await runSafe(
      backendApi.updateControlEventRule(rule.id, { enabled: !rule.enabled }),
      'toggleEnabled',
      createContext('toggling rule enabled', { entityId: rule.id })
    );
    if (error) {
      // Revert
      setRules((prev) => prev.map((r) => (r.id === rule.id ? { ...r, enabled: rule.enabled } : r)));
      handleError(error, createContext('toggling rule enabled'));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this rule?')) return;
    const [, error] = await runSafe(
      backendApi.deleteControlEventRule(id),
      'deleteRule',
      createContext('deleting rule', { entityId: id })
    );
    if (error) {
      handleError(error, createContext('deleting rule'));
    } else {
      setIsLoading(true);
      void loadData();
    }
  };

  const targetOptions = form.targetType === 'task' ? tasks : workflows;
  const getTargetName = (rule: ControlEventRule) => {
    if (rule.target_type === 'task') {
      return tasks.find((t) => t.id === rule.target_id)?.name ?? rule.target_id;
    }
    return workflows.find((w) => w.id === rule.target_id)?.name ?? rule.target_id;
  };

  const getTargetHref = (rule: ControlEventRule) => {
    if (rule.target_type === 'task') return `/workbench?taskId=${rule.target_id}`;
    return `/workflows/${rule.target_id}`;
  };

  const canSave = form.name.trim() && form.channel && form.targetId && !isSaving;
  let saveButtonLabel = 'Create Rule';
  if (isSaving) saveButtonLabel = 'Saving…';
  else if (editingRuleId) saveButtonLabel = 'Save Changes';

  const renderTableRows = (): React.JSX.Element => {
    if (isLoading && rules.length === 0) {
      return (
        <tr>
          <td colSpan={6} className="px-5 py-8 text-center text-gray-400">
            <ArrowPathIcon className="h-5 w-5 animate-spin mx-auto mb-2" />
            Loading rules…
          </td>
        </tr>
      );
    }
    if (rules.length === 0) {
      return (
        <tr>
          <td colSpan={6} className="px-5 py-12 text-center">
            <BoltIcon className="h-8 w-8 text-gray-600 mx-auto mb-2" />
            <p className="text-gray-400 text-sm">No reaction rules yet.</p>
            <p className="text-gray-500 text-xs mt-1">
              Create a rule to run a task or workflow when a system event fires.
            </p>
          </td>
        </tr>
      );
    }
    return (
      <>
        {rules.map((rule) => (
          <tr key={rule.id} className="hover:bg-gray-800/30">
            <td className="px-5 py-3">
              <span className="text-sm text-gray-100 wrap-break-word">{rule.name}</span>
            </td>
            <td className="px-5 py-3">
              <ChannelBadge channel={rule.channel} channels={channels} />
            </td>
            <td className="px-5 py-3">
              <span className="text-xs text-gray-400 capitalize">{rule.target_type}</span>
            </td>
            <td className="px-5 py-3">
              <Link
                to={getTargetHref(rule)}
                className="text-sm text-gray-300 hover:text-primary wrap-break-word transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                {getTargetName(rule)}
              </Link>
            </td>
            <td className="px-5 py-3 text-center">
              <EnabledToggle
                enabled={rule.enabled}
                onChange={() => void handleToggleEnabled(rule)}
              />
            </td>
            <td className="px-5 py-3 text-right">
              <div className="flex items-center justify-end gap-2">
                <button
                  onClick={() => openEditForm(rule)}
                  className="text-gray-400 hover:text-gray-200"
                  title="Edit rule"
                >
                  <PencilIcon className="h-4 w-4" />
                </button>
                <button
                  onClick={() => void handleDelete(rule.id)}
                  className="text-red-500 hover:text-red-400"
                  title="Delete rule"
                >
                  <TrashIcon className="h-4 w-4" />
                </button>
              </div>
            </td>
          </tr>
        ))}
      </>
    );
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-100">Event Reaction Rules</h2>
          <p className="text-sm text-gray-400 mt-1">
            Tasks and workflows that run automatically when system events fire
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              setIsLoading(true);
              void loadData();
            }}
            disabled={isLoading}
            className="flex items-center gap-2 px-4 py-2 bg-gray-700 text-white rounded-md hover:bg-gray-600 disabled:opacity-50"
          >
            <ArrowPathIcon className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button
            onClick={openCreateForm}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90"
          >
            <PlusIcon className="h-4 w-4" />
            New Rule
          </button>
        </div>
      </div>

      {/* Form */}
      {showForm && (
        <div className="p-5 bg-gray-800/50 border border-gray-700 rounded-lg space-y-4">
          <h3 className="text-base font-medium text-gray-100">
            {editingRuleId ? 'Edit Rule' : 'Create New Rule'}
          </h3>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Name */}
            <div className="md:col-span-2 space-y-1.5">
              <label htmlFor="rule-name" className="block text-sm font-medium text-gray-300">
                Name
              </label>
              <input
                id="rule-name"
                type="text"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Slack: Notify on Disposition"
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>

            {/* Channel */}
            <div className="space-y-1.5">
              <label htmlFor="rule-channel" className="block text-sm font-medium text-gray-300">
                Channel
              </label>
              <select
                id="rule-channel"
                value={form.channel}
                onChange={(e) => setForm((f) => ({ ...f, channel: e.target.value }))}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              >
                <option value="">Select a channel…</option>
                {channels.map((c) => (
                  <option key={c.channel} value={c.channel}>
                    {c.channel}
                    {c.type === 'system' ? ' (system)' : ''}
                  </option>
                ))}
              </select>
              {form.channel && channels.find((c) => c.channel === form.channel)?.description && (
                <p className="text-xs text-gray-500">
                  {channels.find((c) => c.channel === form.channel)!.description}
                </p>
              )}
            </div>

            {/* Target type */}
            <div className="space-y-1.5">
              <span className="block text-sm font-medium text-gray-300">Target Type</span>
              <div className="flex gap-4 mt-2">
                {(['task', 'workflow'] as const).map((t) => (
                  <label key={t} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="targetType"
                      value={t}
                      checked={form.targetType === t}
                      onChange={() => setForm((f) => ({ ...f, targetType: t, targetId: '' }))}
                      className="accent-primary"
                    />
                    <span className="text-sm text-gray-300 capitalize">{t}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Target */}
            <div className="space-y-1.5">
              <label htmlFor="rule-target" className="block text-sm font-medium text-gray-300">
                Target {form.targetType === 'task' ? 'Task' : 'Workflow'}
              </label>
              <select
                id="rule-target"
                value={form.targetId}
                onChange={(e) => setForm((f) => ({ ...f, targetId: e.target.value }))}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-gray-100 text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
              >
                <option value="">
                  Select a {form.targetType === 'task' ? 'task' : 'workflow'}…
                </option>
                {targetOptions.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Enabled */}
            <div className="flex items-center gap-3 self-end pb-1">
              <span className="text-sm font-medium text-gray-300">Enabled</span>
              <EnabledToggle
                enabled={form.enabled}
                onChange={(val) => setForm((f) => ({ ...f, enabled: val }))}
              />
            </div>

            {/* Config JSON */}
            <div className="md:col-span-2 space-y-1.5">
              <label htmlFor="rule-config" className="block text-sm font-medium text-gray-300">
                Config{' '}
                <span className="text-gray-500 font-normal">
                  (JSON — optional extra parameters passed to the target)
                </span>
              </label>
              <textarea
                id="rule-config"
                value={form.configJson}
                onChange={(e) => {
                  setForm((f) => ({ ...f, configJson: e.target.value }));
                  setConfigError('');
                }}
                rows={4}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-gray-100 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="{}"
              />
              {configError && <p className="text-xs text-red-400">{configError}</p>}
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              onClick={closeForm}
              className="px-4 py-2 bg-gray-700 text-white rounded-md hover:bg-gray-600 text-sm"
            >
              Cancel
            </button>
            <button
              onClick={() => void handleSave()}
              disabled={!canSave}
              className="px-4 py-2 bg-primary text-white rounded-md hover:bg-primary/90 disabled:opacity-50 text-sm"
            >
              {saveButtonLabel}
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-gray-800/30 border border-gray-700 rounded-lg overflow-hidden overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-700 table-fixed">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="px-5 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-1/4">
                Name
              </th>
              <th className="px-5 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-1/4">
                Channel
              </th>
              <th className="px-5 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-1/6">
                Type
              </th>
              <th className="px-5 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider w-1/5">
                Target
              </th>
              <th className="px-5 py-3 text-center text-xs font-medium text-gray-300 uppercase tracking-wider w-20">
                Enabled
              </th>
              <th className="px-5 py-3 text-right text-xs font-medium text-gray-300 uppercase tracking-wider w-20">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">{renderTableRows()}</tbody>
        </table>
      </div>

      {!isLoading && rules.length > 0 && (
        <p className="text-xs text-gray-500">
          {rules.length} {rules.length === 1 ? 'rule' : 'rules'}
        </p>
      )}
    </div>
  );
};
