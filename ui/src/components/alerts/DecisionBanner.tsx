import React from 'react';

import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';

import type { Alert, Disposition } from '../../types/alert';

// Severity badge component
export const SeverityBadge: React.FC<{ severity: string }> = ({ severity }) => {
  const colorClasses: Record<string, string> = {
    critical: 'bg-red-900 text-red-300 border-red-700',
    high: 'bg-orange-900 text-orange-300 border-orange-700',
    medium: 'bg-yellow-900 text-yellow-300 border-yellow-700',
    low: 'bg-blue-900 text-blue-300 border-blue-700',
    info: 'bg-gray-700 text-gray-300 border-gray-600',
  };

  return (
    <span
      className={`px-3 py-1 text-sm font-medium rounded-md border ${colorClasses[severity] || colorClasses.info}`}
    >
      {severity.toUpperCase()}
    </span>
  );
};

// Analysis status badge component
export const AnalysisStatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const statusConfig: Record<string, { label: string; class: string }> = {
    not_analyzed: { label: 'Not Analyzed', class: 'bg-gray-700 text-gray-300 border-gray-600' },
    new: { label: 'Not Analyzed', class: 'bg-gray-700 text-gray-300 border-gray-600' },
    analyzing: {
      label: 'Analyzing',
      class: 'bg-blue-900 text-blue-300 border-blue-700 animate-pulse',
    },
    in_progress: {
      label: 'Analyzing',
      class: 'bg-blue-900 text-blue-300 border-blue-700 animate-pulse',
    },
    analyzed: { label: 'Analyzed', class: 'bg-green-900 text-green-300 border-green-700' },
    completed: { label: 'Analyzed', class: 'bg-green-900 text-green-300 border-green-700' },
    analysis_failed: { label: 'Analysis Failed', class: 'bg-red-900 text-red-300 border-red-700' },
    failed: { label: 'Analysis Failed', class: 'bg-red-900 text-red-300 border-red-700' },
    cancelled: { label: 'Cancelled', class: 'bg-yellow-900 text-yellow-300 border-yellow-700' },
  };

  const config = statusConfig[status] || statusConfig.not_analyzed;
  return (
    <span className={`px-3 py-1 text-sm font-medium rounded-md border ${config.class}`}>
      {config.label}
    </span>
  );
};

// Compact source info line (vendor · product)
const SourceLine: React.FC<{ alert: Alert }> = ({ alert }) => {
  const parts: string[] = [];
  if (alert.source_vendor) parts.push(alert.source_vendor);
  if (alert.source_product) parts.push(alert.source_product);
  if (parts.length === 0) return null;

  return <div className="text-xs text-gray-500 mt-1.5">{parts.join(' · ')}</div>;
};

interface DecisionBannerProps {
  alert: Alert;
  disposition?: Disposition;
}

export const DecisionBanner: React.FC<DecisionBannerProps> = ({ alert, disposition }) => {
  const isAnalyzed = alert.analysis_status === 'completed';
  const hasDisposition = isAnalyzed && disposition;

  // Non-analyzed alerts: show a minimal badges row
  if (!hasDisposition) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <SeverityBadge severity={alert.severity} />
          <AnalysisStatusBadge status={alert.analysis_status} />
        </div>
        <SourceLine alert={alert} />
      </div>
    );
  }

  const confidence = alert.current_disposition_confidence;
  const shortSummary = alert.current_analysis?.short_summary || alert.short_summary;

  return (
    <div
      className="bg-dark-800 border border-gray-700/30 rounded-lg p-5"
      style={{ borderLeftWidth: '4px', borderLeftColor: disposition.color_hex }}
    >
      {/* Top row: disposition name + confidence */}
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xl font-semibold text-white">{disposition.display_name}</h2>
        {confidence != null && (
          <div className="text-right">
            <span className="text-3xl font-bold text-white">{confidence}</span>
            <span className="text-lg text-gray-400 ml-0.5">%</span>
            <div className="text-xs text-gray-500">confidence</div>
          </div>
        )}
      </div>

      {/* Middle: short summary */}
      {shortSummary && (
        <p className="text-base text-gray-300 leading-relaxed mb-3">{shortSummary}</p>
      )}

      {/* Bottom: two sub-banners — Alert Source + AI Verdict */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Alert Source banner */}
        <div className="bg-gray-900/50 border border-gray-700/40 rounded-md px-4 py-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold mb-2">
            Alert Source
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <SeverityBadge severity={alert.severity} />
            {alert.finding_info?.types?.[0] && (
              <span className="px-2.5 py-0.5 text-xs font-medium rounded-md border bg-gray-700/50 text-gray-300 border-gray-600">
                {alert.finding_info.types[0]}
              </span>
            )}
          </div>
          <SourceLine alert={alert} />
        </div>

        {/* AI Verdict banner */}
        <div className="bg-gray-900/50 border border-gray-700/40 rounded-md px-4 py-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold mb-2">
            AI Verdict
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="px-3 py-1 text-sm font-medium rounded-md border"
              style={{
                backgroundColor: `${disposition.color_hex}20`,
                color: disposition.color_hex,
                borderColor: `${disposition.color_hex}50`,
              }}
            >
              {disposition.subcategory}
            </span>
            {disposition.requires_escalation && (
              <span className="flex items-center gap-1.5 px-3 py-1 text-sm font-medium rounded-md border bg-orange-900/50 text-orange-300 border-orange-700">
                <ExclamationTriangleIcon className="h-4 w-4" />
                Escalation Required
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
