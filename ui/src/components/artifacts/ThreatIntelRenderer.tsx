import React from 'react';

import JsonRenderer from './JsonRenderer';

interface ThreatIntelRendererProps {
  vtData: unknown;
}

interface VirusTotalAttributes {
  as_owner?: string;
  country?: string;
  last_analysis_stats?: {
    malicious: number;
    suspicious: number;
    harmless: number;
    undetected: number;
  };
}

/**
 * Component to render Threat Intelligence information in a pretty-printed JSON format
 * identical approach to CveInfoRenderer
 */
const ThreatIntelRenderer: React.FC<ThreatIntelRendererProps> = ({ vtData }) => {
  if (!vtData) {
    return (
      <div className="p-4 bg-dark-800 rounded-md text-gray-400">
        No threat intelligence information available
      </div>
    );
  }

  try {
    // Extract VirusTotal info for the header if available
    const data = vtData as Record<string, unknown>;
    const vtRecord = data.data as Record<string, unknown> | undefined;

    if (!vtRecord || !vtRecord.id) {
      return (
        <JsonRenderer
          data={vtData}
          title="Threat Intelligence Data"
          id="json-pretty-threat-intel"
        />
      );
    }

    const id = vtRecord.id as string;
    const type = (vtRecord.type as string) || '';
    const displayType = type === 'ip_address' ? 'IP Address' : type;

    const attributes = vtRecord.attributes as VirusTotalAttributes | undefined;
    const subtitle = attributes?.as_owner || '';

    return (
      <JsonRenderer
        data={vtData}
        title={`${displayType}: ${id}`}
        subtitle={subtitle}
        id="json-pretty-threat-intel"
      />
    );
  } catch (error: unknown) {
    // Safe error logging with proper type handling
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error('Error in ThreatIntelRenderer:', errorMessage);

    // Fallback to basic renderer
    return (
      <JsonRenderer data={vtData} title="Threat Intelligence Data" id="json-pretty-threat-intel" />
    );
  }
};

export default ThreatIntelRenderer;
