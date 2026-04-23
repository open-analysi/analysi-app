/* eslint-disable react-hooks/preserve-manual-memoization, sonarjs/function-return-type */
import React, { useEffect, useState } from 'react';

import {
  DocumentMagnifyingGlassIcon,
  DocumentIcon,
  ClockIcon,
  ShieldExclamationIcon,
  GlobeAltIcon,
  ServerIcon,
  ChevronRightIcon,
  CheckCircleIcon,
  XCircleIcon,
  PhotoIcon,
  CodeBracketIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';
import { Link } from 'react-router';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import type { Alert } from '../../types/alert';
import { Artifact } from '../../types/artifact';
import { TaskRun } from '../../types/taskRun';

interface OverviewTabProps {
  alert: Alert;
  taskRuns: TaskRun[];
  onNavigateToTab: (tab: 'findings' | 'raw' | 'analysis', subtab?: string) => void;
}

// ── OCSF helpers ─────────────────────────────────────────
// OCSF endpoints/actors are typed as Record<string, unknown> in the generated
// schema, so we read individual fields through these small accessors.
const readString = (obj: unknown, key: string): string | null => {
  if (obj && typeof obj === 'object' && key in obj) {
    const v = (obj as Record<string, unknown>)[key];
    if (typeof v === 'string' && v.length > 0) return v;
    if (typeof v === 'number') return String(v);
  }
  return null;
};

// Primary risk entity — derived from OCSF actor.user (preferred) or device.
const getPrimaryRiskEntity = (alert: Alert): { type: string; value: string } | null => {
  const userName = readString(alert.actor?.user, 'name') || readString(alert.actor?.user, 'uid');
  if (userName) return { type: 'User', value: userName };
  const hostname = alert.device?.hostname || alert.device?.name || alert.device?.ip;
  if (hostname) return { type: 'Device', value: hostname };
  return null;
};

// Primary IOC — first observable.
const getPrimaryObservable = (alert: Alert): { type: string; value: string } | null => {
  const first = alert.observables?.[0];
  if (!first) return null;
  return {
    type: first.type || `type_id=${first.type_id}`,
    value: first.value,
  };
};

// Extract endpoint fields from the first evidence artifact.
const getEndpoints = (alert: Alert) => {
  const ev = alert.evidences?.[0];
  const src = ev?.src_endpoint ?? null;
  const dst = ev?.dst_endpoint ?? null;
  const url = readString(ev?.url, 'url') ?? readString(ev, 'url');
  return {
    src_ip: readString(src, 'ip'),
    src_port: readString(src, 'port'),
    src_hostname: readString(src, 'hostname'),
    dst_ip: readString(dst, 'ip'),
    dst_port: readString(dst, 'port'),
    dst_hostname: readString(dst, 'hostname'),
    url,
    hasAny: !!(src || dst || url),
  };
};

// Helper to format duration
const formatDuration = (ms: number): string => {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`;
  } else if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  } else {
    return `${seconds}s`;
  }
};

// Helper to get artifact type icon
const getArtifactIcon = (mimeType: string): React.ReactNode => {
  if (mimeType.startsWith('image/')) {
    return <PhotoIcon className="h-4 w-4" />;
  }
  if (mimeType === 'application/json' || mimeType.includes('json')) {
    return <CodeBracketIcon className="h-4 w-4" />;
  }
  if (mimeType.startsWith('text/')) {
    return <DocumentTextIcon className="h-4 w-4" />;
  }
  return <DocumentIcon className="h-4 w-4" />;
};

// Clickable stat card component
const StatCard: React.FC<{
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  subtext?: string;
  onClick?: () => void;
  className?: string;
}> = ({ icon, label, value, subtext, onClick, className = '' }) => {
  const Wrapper = onClick ? 'button' : 'div';

  return (
    <Wrapper
      onClick={onClick}
      className={`bg-dark-800 border border-gray-700 rounded-lg p-4 text-left transition-colors ${
        onClick ? 'hover:bg-dark-700 hover:border-primary/50 cursor-pointer group' : ''
      } ${className}`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2 text-gray-400 mb-2">
          {icon}
          <span className="text-sm font-medium">{label}</span>
        </div>
        {onClick && (
          <ChevronRightIcon className="h-4 w-4 text-gray-600 group-hover:text-primary transition-colors" />
        )}
      </div>
      <div className="text-xl font-semibold text-gray-100">{value}</div>
      {subtext && <div className="text-xs text-gray-500 mt-1">{subtext}</div>}
    </Wrapper>
  );
};

// Info card for key-value pairs
const InfoCard: React.FC<{
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}> = ({ title, icon, children }) => (
  <div className="bg-dark-800 border border-gray-700 rounded-lg p-4">
    <div className="flex items-center gap-2 text-gray-300 mb-3">
      {icon}
      <h4 className="text-sm font-medium">{title}</h4>
    </div>
    <div className="space-y-2">{children}</div>
  </div>
);

// Key-value row component
const InfoRow: React.FC<{
  label: string;
  value: React.ReactNode;
  monospace?: boolean;
}> = ({ label, value, monospace = false }) => (
  <div className="flex justify-between items-start gap-4 text-sm">
    <span className="text-gray-500 shrink-0">{label}</span>
    <span
      className={`text-gray-200 text-right break-all min-w-0 ${monospace ? 'font-mono text-xs' : ''}`}
    >
      {value}
    </span>
  </div>
);

// Collapsible section using native details/summary
const CollapsibleSection: React.FC<{
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}> = ({ title, defaultOpen = true, children }) => (
  <details open={defaultOpen} className="group">
    <summary className="flex items-center gap-2 cursor-pointer select-none text-sm font-medium text-gray-400 hover:text-gray-200 mb-3">
      <ChevronRightIcon className="h-4 w-4 transition-transform group-open:rotate-90" />
      {title}
    </summary>
    <div className="ml-1">{children}</div>
  </details>
);

export const OverviewTab: React.FC<OverviewTabProps> = ({ alert, taskRuns, onNavigateToTab }) => {
  const { runSafe } = useErrorHandler('OverviewTab');
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loadingArtifacts, setLoadingArtifacts] = useState(false);

  // Fetch artifacts for this alert's analysis
  useEffect(() => {
    const fetchArtifacts = async () => {
      if (!alert.current_analysis_id) return;

      setLoadingArtifacts(true);
      const [response] = await runSafe(
        backendApi.getArtifacts({ analysis_id: alert.current_analysis_id, limit: 100 }),
        'fetchArtifacts',
        { action: 'fetching artifacts', entityId: alert.current_analysis_id }
      );

      if (response?.artifacts) {
        setArtifacts(response.artifacts);
      }
      setLoadingArtifacts(false);
    };

    void fetchArtifacts();
  }, [alert.current_analysis_id, runSafe]);

  // Calculate stats
  const succeededTasks = taskRuns.filter((t) => t.status === 'completed').length;
  const failedTasks = taskRuns.filter((t) => t.status === 'failed').length;
  const totalTasks = taskRuns.length;

  // Calculate total LLM cost from task runs
  const totalLLMCost = taskRuns.reduce((sum, run) => {
    return sum + (run.llm_usage?.cost_usd ?? 0);
  }, 0);
  const hasLLMCostData = taskRuns.some((run) => run.llm_usage?.cost_usd != null);

  // Helper to categorize artifact type
  const getArtifactCategory = (mimeType: string): string => {
    if (mimeType.startsWith('image/')) return 'images';
    if (mimeType === 'application/json') return 'json';
    if (mimeType.startsWith('text/')) return 'text';
    return 'other';
  };

  // Group artifacts by type for display
  const artifactsByType = artifacts.reduce<Record<string, number>>((acc, artifact) => {
    const type = getArtifactCategory(artifact.mime_type);
    acc[type] = (acc[type] || 0) + 1;
    return acc;
  }, {});

  // Format artifact summary
  const artifactSummary = Object.entries(artifactsByType)
    .map(([type, count]) => `${count} ${type}`)
    .join(', ');

  // Calculate analysis duration
  const analysisDuration = React.useMemo((): string | null => {
    if (!alert.current_analysis?.started_at) return null;

    const startTime = new Date(alert.current_analysis.started_at).getTime();
    const endTime = alert.current_analysis.completed_at
      ? new Date(alert.current_analysis.completed_at).getTime()
      : new Date().getTime();

    return formatDuration(endTime - startTime);
  }, [alert.current_analysis?.started_at, alert.current_analysis?.completed_at]);

  const primaryRiskEntity = getPrimaryRiskEntity(alert);
  const primaryObservable = getPrimaryObservable(alert);
  const hasEntities = !!primaryRiskEntity || !!primaryObservable;

  const endpoints = getEndpoints(alert);
  const hasNetworkInfo = endpoints.hasAny;

  const hasSourceInfo = alert.source_vendor || alert.source_product || alert.rule_name;
  const findingType = alert.finding_info?.types?.[0];

  return (
    <div className="space-y-6">
      {/* 1. Key Entities (always visible) */}
      {hasEntities && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {primaryRiskEntity && (
            <InfoCard
              title="Primary Risk Entity"
              icon={<ShieldExclamationIcon className="h-5 w-5 text-orange-400" />}
            >
              <InfoRow label="Entity Type" value={primaryRiskEntity.type} />
              <InfoRow label="Value" value={primaryRiskEntity.value} monospace />
            </InfoCard>
          )}

          {primaryObservable && (
            <InfoCard
              title="Primary Indicator of Compromise"
              icon={<ShieldExclamationIcon className="h-5 w-5 text-red-400" />}
            >
              <InfoRow label="IOC Type" value={primaryObservable.type} />
              <InfoRow
                label="Value"
                value={
                  <Link
                    to={`/alerts?search=${encodeURIComponent(primaryObservable.value)}`}
                    className="text-primary hover:underline font-mono text-xs"
                    title="View all alerts with this IOC"
                  >
                    {primaryObservable.value}
                  </Link>
                }
              />
            </InfoCard>
          )}
        </div>
      )}

      {/* Observables list (collapsible, if multiple observables exist) */}
      {alert.observables && alert.observables.length > 0 && (
        <CollapsibleSection title={`Observables (${alert.observables.length})`} defaultOpen={false}>
          <div className="bg-dark-800 border border-gray-700 rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-700">
              <thead>
                <tr className="bg-dark-700">
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-400">Type</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-400">Value</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-400">Name</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700/50">
                {alert.observables.map((obs, i) => (
                  <tr key={i} className="hover:bg-dark-700/50">
                    <td className="px-4 py-2 text-xs text-gray-300">
                      <span className="inline-flex items-center gap-1">
                        {obs.type || `type_id=${obs.type_id}`}
                        {i === 0 && (
                          <span className="px-1.5 py-0.5 text-[10px] font-medium bg-red-900/30 text-red-400 border border-red-700/50 rounded">
                            primary
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-xs">
                      <Link
                        to={`/alerts?search=${encodeURIComponent(obs.value)}`}
                        className="text-primary hover:underline font-mono"
                        title="View all alerts with this observable"
                      >
                        {obs.value}
                      </Link>
                    </td>
                    <td className="px-4 py-2 text-xs text-gray-400">{obs.name ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CollapsibleSection>
      )}

      {/* 2. Network & Source Context (collapsible, open by default) */}
      {(hasNetworkInfo || hasSourceInfo) && (
        <CollapsibleSection title="Network & Source Context">
          <div className="space-y-4">
            {hasNetworkInfo && (
              <InfoCard
                title="Network Context"
                icon={<GlobeAltIcon className="h-5 w-5 text-blue-400" />}
              >
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                      Source
                    </div>
                    {endpoints.src_ip && <InfoRow label="IP" value={endpoints.src_ip} monospace />}
                    {endpoints.src_port && <InfoRow label="Port" value={endpoints.src_port} />}
                    {endpoints.src_hostname && (
                      <InfoRow label="Hostname" value={endpoints.src_hostname} monospace />
                    )}
                  </div>
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                      Destination
                    </div>
                    {endpoints.dst_ip && <InfoRow label="IP" value={endpoints.dst_ip} monospace />}
                    {endpoints.dst_port && <InfoRow label="Port" value={endpoints.dst_port} />}
                    {endpoints.dst_hostname && (
                      <InfoRow label="Hostname" value={endpoints.dst_hostname} monospace />
                    )}
                  </div>
                </div>
                {endpoints.url && (
                  <div className="mt-3 pt-3 border-t border-gray-700">
                    <InfoRow
                      label="URL"
                      value={<span className="break-all">{endpoints.url}</span>}
                    />
                  </div>
                )}
              </InfoCard>
            )}

            {hasSourceInfo && (
              <InfoCard
                title="Alert Source"
                icon={<ServerIcon className="h-5 w-5 text-purple-400" />}
              >
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
                  {alert.source_vendor && <InfoRow label="Vendor" value={alert.source_vendor} />}
                  {alert.source_product && <InfoRow label="Product" value={alert.source_product} />}
                  {alert.rule_name && <InfoRow label="Rule" value={alert.rule_name} />}
                  {findingType && <InfoRow label="Finding Type" value={findingType} />}
                </div>
              </InfoCard>
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* 4. Investigation Details (collapsible, collapsed by default) */}
      <CollapsibleSection title="Investigation Details" defaultOpen={false}>
        <div className="space-y-4">
          {/* Quick Stats Row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {totalTasks > 0 && (
              <StatCard
                icon={<DocumentMagnifyingGlassIcon className="h-5 w-5" />}
                label="Findings"
                value={
                  <div className="flex items-center gap-2">
                    <span className="text-green-400">{succeededTasks}</span>
                    <span className="text-gray-500">/</span>
                    <span>{totalTasks}</span>
                    {failedTasks > 0 && (
                      <span className="text-xs text-red-400">({failedTasks} failed)</span>
                    )}
                  </div>
                }
                subtext="tasks completed"
                onClick={() => onNavigateToTab('findings')}
              />
            )}

            <StatCard
              icon={<DocumentIcon className="h-5 w-5" />}
              label="Artifacts"
              value={loadingArtifacts ? '...' : artifacts.length}
              subtext={artifactSummary || 'No artifacts collected'}
              onClick={() => onNavigateToTab('analysis', 'artifacts')}
            />

            {analysisDuration && (
              <StatCard
                icon={<ClockIcon className="h-5 w-5" />}
                label="Analysis Time"
                value={analysisDuration}
                subtext={alert.current_analysis?.status || 'completed'}
              />
            )}

            {hasLLMCostData && totalTasks > 0 && (
              <StatCard
                icon={<span className="text-emerald-400 text-base font-bold leading-none">$</span>}
                label="Execution Cost"
                value={<span className="text-emerald-400">${totalLLMCost.toFixed(4)}</span>}
                subtext="LLM cost across all tasks"
                onClick={() => onNavigateToTab('analysis')}
              />
            )}

            {alert.current_disposition_confidence != null && (
              <StatCard
                icon={
                  alert.current_disposition_confidence >= 70 ? (
                    <CheckCircleIcon className="h-5 w-5 text-green-400" />
                  ) : (
                    <XCircleIcon className="h-5 w-5 text-yellow-400" />
                  )
                }
                label="Confidence"
                value={`${alert.current_disposition_confidence}%`}
                subtext={alert.current_disposition_display_name || 'disposition'}
              />
            )}
          </div>

          {/* Artifacts List Preview */}
          {artifacts.length > 0 && (
            <div className="bg-dark-800 border border-gray-700 rounded-lg p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-gray-300">
                  <DocumentIcon className="h-5 w-5" />
                  <h4 className="text-sm font-medium">Collected Artifacts</h4>
                </div>
                <button
                  onClick={() => onNavigateToTab('analysis', 'artifacts')}
                  className="text-xs text-primary hover:text-primary/80 flex items-center gap-1"
                >
                  View all
                  <ChevronRightIcon className="h-3 w-3" />
                </button>
              </div>
              <div className="space-y-2">
                {artifacts.slice(0, 5).map((artifact) => (
                  <div
                    key={artifact.id}
                    className="flex items-center gap-3 p-2 bg-dark-900 rounded-sm text-sm"
                  >
                    <div className="text-gray-400">{getArtifactIcon(artifact.mime_type)}</div>
                    <div className="flex-1 min-w-0">
                      <div className="text-gray-200 truncate">{artifact.name}</div>
                      <div className="text-xs text-gray-500">
                        {artifact.artifact_type || artifact.mime_type}
                      </div>
                    </div>
                  </div>
                ))}
                {artifacts.length > 5 && (
                  <div className="text-xs text-gray-500 text-center pt-2">
                    +{artifacts.length - 5} more artifacts
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Key Timestamps */}
          <InfoCard title="Timeline" icon={<ClockIcon className="h-5 w-5 text-cyan-400" />}>
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 rounded-full bg-red-400 mt-1.5 shrink-0" />
                <div className="flex-1">
                  <div className="text-xs text-gray-500">Event Triggered</div>
                  <div className="text-sm text-gray-200">
                    {new Date(alert.triggering_event_time).toLocaleString()}
                  </div>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-2 h-2 rounded-full bg-blue-400 mt-1.5 shrink-0" />
                <div className="flex-1">
                  <div className="text-xs text-gray-500">Alert Ingested</div>
                  <div className="text-sm text-gray-200">
                    {new Date(alert.ingested_at || alert.created_at).toLocaleString()}
                  </div>
                </div>
              </div>
              {alert.current_analysis?.started_at && (
                <div className="flex items-start gap-3">
                  <div className="w-2 h-2 rounded-full bg-yellow-400 mt-1.5 shrink-0" />
                  <div className="flex-1">
                    <div className="text-xs text-gray-500">Analysis Started</div>
                    <div className="text-sm text-gray-200">
                      {new Date(alert.current_analysis.started_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              )}
              {alert.current_analysis?.completed_at && (
                <div className="flex items-start gap-3">
                  <div className="w-2 h-2 rounded-full bg-green-400 mt-1.5 shrink-0" />
                  <div className="flex-1">
                    <div className="text-xs text-gray-500">Analysis Completed</div>
                    <div className="text-sm text-gray-200">
                      {new Date(alert.current_analysis.completed_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </InfoCard>
        </div>
      </CollapsibleSection>
    </div>
  );
};
