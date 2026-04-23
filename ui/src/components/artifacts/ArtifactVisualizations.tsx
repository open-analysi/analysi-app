import React from 'react';

// Common Props interface for all visualizations
interface VisualizationProps {
  data: Record<string, unknown>;
}

// String data props interface
interface StringDataProps {
  data: string | Record<string, unknown>;
}

// JSON Viewer component
export const JSONViewer: React.FC<StringDataProps> = ({ data }) => {
  const jsonData = typeof data === 'string' ? data : JSON.stringify(data, undefined, 2);

  return (
    <div className="bg-dark-800 p-4 rounded-md">
      <pre className="whitespace-pre-wrap text-gray-200 font-mono text-sm overflow-auto max-h-96">
        {jsonData}
      </pre>
    </div>
  );
};

// Log Viewer component
export const LogViewer: React.FC<StringDataProps> = ({ data }) => {
  const logLines = typeof data === 'string' ? data.split('\n') : [];

  return (
    <div className="bg-dark-800 p-4 rounded-md">
      <div className="font-mono text-sm text-gray-200 overflow-auto max-h-96">
        {logLines.map((line: string, index: number) => (
          <div key={index} className="py-1 border-b border-dark-700 last:border-0">
            {line}
          </div>
        ))}
      </div>
    </div>
  );
};

// Generic Summary component
export const GenericSummary: React.FC<VisualizationProps> = ({ data }) => {
  return (
    <div className="bg-dark-800 p-4 rounded-md">
      <h3 className="text-lg font-medium text-gray-100 mb-4">Summary Data</h3>
      <div className="overflow-auto max-h-96">
        <pre className="whitespace-pre-wrap text-gray-300 font-mono text-sm">
          {JSON.stringify(data, undefined, 2)}
        </pre>
      </div>
    </div>
  );
};

// Placeholder components for all visualization types
export const CVESeveritySummary = GenericSummary;
export const ThreatIntelSummary = GenericSummary;
export const TimelineSummary = GenericSummary;
export const BarChartSummary = GenericSummary;
export const ProcessListSummary = GenericSummary;
export const NetworkActivitySummary = GenericSummary;
export const HostInfoSummary = GenericSummary;
