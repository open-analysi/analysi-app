import React from 'react';

import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';

import JsonRenderer from './JsonRenderer';

interface LogEntry {
  timestamp?: string;
  level?: string;
  message?: string;
  [key: string]: unknown;
}

interface LogEventsRendererProps {
  data: string | Record<string, unknown> | null;
  category?: string;
  maxHeight?: string;
  viewMode?: 'original' | 'summary';
}

// Constants for commonly used strings
const TRIGGERING_EVENTS = 'Triggering Events';
const SUPPORTING_EVENTS = 'Supporting Events';

// Helper function to get the display title based on category
const getDisplayTitle = (category?: string): string => {
  return category === 'timeline' ? TRIGGERING_EVENTS : SUPPORTING_EVENTS;
};

const getLevelClass = (level: string): string => {
  const lowerLevel = level.toLowerCase();
  switch (lowerLevel) {
    case 'error':
    case 'critical':
    case 'fatal': {
      return 'text-red-400';
    }
    case 'warning':
    case 'warn': {
      return 'text-yellow-400';
    }
    case 'info':
    case 'information': {
      return 'text-blue-400';
    }
    case 'debug': {
      return 'text-gray-400';
    }
    default: {
      return 'text-gray-300';
    }
  }
};

const parseLogEntry = (entry: string): LogEntry => {
  // Try to extract timestamp and level if they exist
  const timestampMatch = /^\[(.*?)]/.exec(entry);
  const levelMatch = /\[(debug|info|warn(?:ing)?|error|critical|fatal)]/i.exec(entry);

  return {
    timestamp: timestampMatch ? timestampMatch[1] : undefined,
    level: levelMatch ? levelMatch[1] : undefined,
    message: entry
      .replace(timestampMatch?.[0] || '', '')
      .replace(levelMatch?.[0] || '', '')
      .trim(),
  };
};

// Export this component for testing
export const DataUnavailableMessage: React.FC<{ category?: string }> = ({ category }) => {
  const categoryName = category || 'data';
  const title = getDisplayTitle(category);
  let unavailableLabel: string;
  if (category === 'timeline') {
    unavailableLabel = TRIGGERING_EVENTS;
  } else if (category === 'logs') {
    unavailableLabel = SUPPORTING_EVENTS;
  } else {
    unavailableLabel = `edr - ${categoryName}`;
  }

  return (
    <div className="bg-dark-800 rounded-md border border-dark-700">
      <div className="p-3 border-b border-dark-700">
        <h3 className="text-lg font-medium text-gray-200">{title}</h3>
      </div>
      <div className="flex flex-col items-center justify-center py-12">
        <ExclamationTriangleIcon className="w-12 h-12 mb-4 text-gray-400" />
        <p className="text-lg font-medium text-gray-400">Data Unavailable</p>
        <p className="text-sm mt-2 text-gray-400">Failed to load data for {unavailableLabel}</p>
      </div>
    </div>
  );
};

// Separated summary view rendering to reduce cognitive complexity
const renderSummaryView = (
  data: string | Record<string, unknown> | null,
  category?: string
): React.JSX.Element => {
  if (typeof data === 'object' && data !== null) {
    return <JsonRenderer data={data} title={getDisplayTitle(category)} />;
  }

  // If it's a string but looks like JSON, try to parse it
  if (typeof data === 'string') {
    try {
      // Check if it starts with { or [ for JSON objects or arrays
      if (data.trim().startsWith('{') || data.trim().startsWith('[')) {
        const jsonData = JSON.parse(data) as Record<string, unknown>;
        return <JsonRenderer data={jsonData} title={getDisplayTitle(category)} />;
      }
    } catch {
      // Error parsing JSON, fall through to unavailable message
    }
  }

  // Fall back to unavailable message if data isn't valid JSON
  return <DataUnavailableMessage category={category} />;
};

/**
 * Component to render log data with clear separation between events
 * Each event is assumed to be on a separate line
 */
const LogEventsRenderer: React.FC<LogEventsRendererProps> = ({
  data,
  category,
  maxHeight = '600px',
  viewMode = 'original',
}) => {
  // Handle summary view with structured JSON data
  if (viewMode === 'summary') {
    return renderSummaryView(data, category);
  }

  // For original view, we need to handle both string data and object data that needs to be stringified
  let logData: string;

  if (typeof data === 'string') {
    // Direct string data
    logData = data;
  } else if (typeof data === 'object' && data !== null) {
    // Try to convert object to string for display
    try {
      logData = JSON.stringify(data, undefined, 2);
    } catch {
      return <DataUnavailableMessage category={category} />;
    }
  } else {
    // No valid data
    return <DataUnavailableMessage category={category} />;
  }

  // Check for HTML error responses
  if (logData.includes('<!DOCTYPE html>')) {
    return <DataUnavailableMessage category={category} />;
  }

  // Split the data into individual log entries (one per line)
  const logEntries = logData.split('\n').filter((entry) => entry.trim() !== '');

  if (logEntries.length === 0) {
    return <DataUnavailableMessage category={category} />;
  }

  const processedLines = logEntries.map((entry, index) => {
    const parsedEntry = parseLogEntry(entry);

    return (
      <div
        key={index}
        className={`py-3 px-4 border-b border-dark-700 last:border-b-0 ${
          index % 2 === 0 ? 'bg-dark-800' : 'bg-dark-700'
        }`}
      >
        {parsedEntry.timestamp && (
          <span className="text-gray-400 mr-4">{parsedEntry.timestamp}</span>
        )}
        {parsedEntry.level && (
          <span className={`mr-4 ${getLevelClass(parsedEntry.level)}`}>
            {parsedEntry.level.toUpperCase()}
          </span>
        )}
        <span className="text-gray-200">{parsedEntry.message || entry}</span>
      </div>
    );
  });

  return (
    <div className="bg-dark-800 rounded-md border border-dark-700">
      <div className="p-3 border-b border-dark-700 flex justify-between items-center">
        <h3 className="text-lg font-medium text-gray-200">{getDisplayTitle(category)}</h3>
        <span className="text-sm text-gray-400">{logEntries.length} events</span>
      </div>
      <div className={`overflow-auto`} style={{ maxHeight }}>
        {processedLines}
      </div>
    </div>
  );
};

export default LogEventsRenderer;
