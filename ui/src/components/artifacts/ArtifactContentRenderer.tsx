import React from 'react';

import type { ArtifactContent, ArtifactViewMode } from './artifactUtils';
import CveInfoRenderer from './CveInfoRenderer';
import { EdrTableRenderer } from './EdrTableRenderer';
import JsonRenderer from './JsonRenderer';
import LogEventsRenderer from './LogEventsRenderer';
import ThreatIntelRenderer from './ThreatIntelRenderer';

interface ArtifactContentRendererProps {
  content: ArtifactContent;
  viewMode: ArtifactViewMode;
  isLoading: boolean;
  error?: string;
  isEdrData?: boolean;
}

// Component to render error messages
const ErrorDisplay: React.FC<{ message: string }> = ({ message }) => (
  <div className="bg-dark-700 rounded-md p-6 text-gray-300">
    <div className="flex items-center text-yellow-500 mb-4">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-6 w-6 mr-2"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
      <span className="font-semibold">Data Unavailable</span>
    </div>
    <p className="text-gray-400">{message}</p>
  </div>
);

// Loading spinner component
const LoadingSpinner: React.FC = () => (
  <div className="flex justify-center items-center h-60">
    <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
  </div>
);

// Extract rendering logic for Original Alert data
const renderOriginalAlertData = (data: unknown): React.JSX.Element => {
  let title = 'Alert Details';
  let subtitle = '';

  if (typeof data === 'object' && data !== null) {
    const typedData = data as Record<string, unknown>;

    // Extract rule name for title
    if (typedData.rule_name && typeof typedData.rule_name === 'string') {
      title = typedData.rule_name;
    }

    // Create subtitle with severity and time
    const parts = [];
    if (typedData.severity && typeof typedData.severity === 'string') {
      parts.push(`Severity: ${typedData.severity}`);
    }
    if (typedData._time && typeof typedData._time === 'string') {
      parts.push(`Time: ${typedData._time}`);
    }
    if (parts.length > 0) {
      subtitle = parts.join(' | ');
    }
  }

  return (
    <JsonRenderer data={data} title={title} subtitle={subtitle} id="json-pretty-original-alert" />
  );
};

// Extract rendering logic for generic JSON data
const renderGenericJsonData = (
  data: unknown,
  category?: string,
  subcategory?: string
): React.JSX.Element => {
  let title = category ? category.charAt(0).toUpperCase() + category.slice(1) : 'JSON Data';

  if (subcategory) {
    title += ` - ${subcategory.charAt(0).toUpperCase() + subcategory.slice(1)}`;
  }

  return <JsonRenderer data={data} title={title} />;
};

// Determine appropriate renderer for JSON content type
const renderJsonContent = (
  data: unknown,
  category?: string,
  subcategory?: string,
  isEdrData?: boolean,
  viewMode?: ArtifactViewMode,
  summaryData?: Record<string, unknown>
): React.JSX.Element => {
  // For EDR data
  if (isEdrData && typeof data === 'object' && data !== null) {
    return <EdrTableRenderer data={data as Record<string, unknown>} subcategory={subcategory} />;
  }

  // For threat intel data
  if (subcategory === 'virustotal') {
    return <ThreatIntelRenderer vtData={data} />;
  }

  // For CVE info
  if (subcategory === 'cve' || category === 'vulnerabilities') {
    // Use summaryData when in summary mode for vulnerabilities
    if (category === 'vulnerabilities' && viewMode === 'summary' && summaryData) {
      return <CveInfoRenderer data={summaryData} />;
    }
    return <CveInfoRenderer data={data as Record<string, unknown>} />;
  }

  // For Original Alert data
  if (category === 'original-alert') {
    return renderOriginalAlertData(data);
  }

  // For other JSON data
  if (typeof data === 'object' && data !== null) {
    return renderGenericJsonData(data, category, subcategory);
  }

  // Default to generic JSON
  return renderGenericJsonData(data, category, subcategory);
};

// Check for error in data
const checkForDataError = (data: unknown): string | undefined => {
  if (typeof data === 'object' && data !== null && 'error' in data) {
    if ('message' in data && typeof data.message === 'string') {
      return data.message;
    }
    return 'The requested data could not be loaded. Please try again later.';
  }
  return undefined;
};

// Main component to render artifact content based on type
const ArtifactContentRenderer: React.FC<ArtifactContentRendererProps> = (props) => {
  const { content, viewMode, isLoading, error, isEdrData } = props;

  // Handle loading state
  if (isLoading) {
    return <LoadingSpinner />;
  }

  // Handle error state from parent
  if (error) {
    return <ErrorDisplay message={error} />;
  }

  const { data, contentType, subcategory, category, summaryData } = content;

  // Check for error in data (from fallbacks)
  const errorMessage = checkForDataError(data);
  if (errorMessage) {
    return <ErrorDisplay message={errorMessage} />;
  }

  // Render based on content type
  if (contentType === 'json') {
    return renderJsonContent(data, category, subcategory, isEdrData, viewMode, summaryData);
  }

  // Default to log renderer
  if (
    contentType === 'log' ||
    (typeof data === 'string' && (category === 'timeline' || category === 'logs'))
  ) {
    // For log data, we know it's a string
    return <LogEventsRenderer data={data as string} category={category} viewMode={viewMode} />;
  }

  // Fallback for any other data type - convert to string for display
  return <LogEventsRenderer data={String(data)} category={category} viewMode={viewMode} />;
};

export default ArtifactContentRenderer;
