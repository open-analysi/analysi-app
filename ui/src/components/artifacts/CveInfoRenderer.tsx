import React from 'react';

import JsonRenderer from './JsonRenderer';

interface CveInfoRendererProps {
  data: Record<string, unknown>;
}

/**
 * Component to render CVE information in a pretty-printed JSON format
 * similar to the Original Alert Detail in AlertDetails.tsx
 */
const CveInfoRenderer: React.FC<CveInfoRendererProps> = ({ data }) => {
  if (!data) {
    return (
      <div className="p-4 bg-dark-800 rounded-md text-gray-400">No CVE information available</div>
    );
  }

  // Extract basic CVE info for the header if available
  const cveMetadata = data.cveMetadata as Record<string, unknown> | undefined;
  const containers = data.containers as Record<string, unknown> | undefined;
  const cna = containers?.cna as Record<string, unknown> | undefined;

  // Handle both original and summary formats
  let cveId: string | undefined;
  let cveTitle: string | undefined;

  // Check for original format
  if (cveMetadata?.cveId) {
    cveId = cveMetadata.cveId as string;
    cveTitle = cna?.title as string | undefined;
  }
  // Check for summary format
  else if (data.cveId) {
    cveId = data.cveId as string;
    cveTitle = data.title as string | undefined;
  }

  return (
    <JsonRenderer
      data={data}
      title={cveId || 'CVE Information'}
      subtitle={cveTitle}
      id="json-pretty-cve-info"
    />
  );
};

export default CveInfoRenderer;
