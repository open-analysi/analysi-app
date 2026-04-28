import React from 'react';

import {
  ComputerDesktopIcon,
  ExclamationTriangleIcon,
  DocumentTextIcon,
  TableCellsIcon,
  BellAlertIcon,
  ShieldExclamationIcon,
} from '@heroicons/react/24/outline';

// Types for artifacts
export type ArtifactViewMode = 'original' | 'summary';

export interface ArtifactSubcategory {
  id: string;
  name: string;
  description?: string;
}

export interface ArtifactCategory {
  id: string;
  name: string;
  icon: React.ReactNode;
  description?: string;
  hasSubcategories: boolean;
  subcategories?: ArtifactSubcategory[];
}

export type ArtifactContentType = 'json' | 'log' | 'text';

export interface ArtifactContent {
  contentType: ArtifactContentType;
  category: string;
  subcategory?: string;
  data: unknown;
  summaryData?: Record<string, unknown>;
}

export interface ArtifactContentConfig {
  alertId: string;
  category: string;
  subcategory?: string;
  viewMode?: ArtifactViewMode;
  provider?: string;
}

// Define shared constants for categories and subcategories
export const THREAT_INTEL_CATEGORY = 'threat-intel';
export const EDR_CATEGORY = 'edr';
export const ORIGINAL_ALERT_CATEGORY = 'original-alert';
export const ANALYSIS_CATEGORY = 'analysis';
export const ANALYSIS_GRAPH_SUBCATEGORY = 'graph';
export const ANALYSIS_STEP_BY_STEP_SUBCATEGORY = 'step-by-step';
export const ANALYSIS_SUMMARY_SUBCATEGORY = 'summary';
export const VULNERABILITIES_CATEGORY = 'vulnerabilities';

// Map the directory names to our category IDs
export const directoryToCategoryMap: Record<string, string> = {
  triggering_events: 'timeline',
  supporting_events: 'logs',
  edr: 'edr',
  cve_info: 'vulnerabilities',
  original_alert: 'original-alert',
  threat_intel: 'threat-intel',
};

// List of available artifact categories
export const artifactCategories: ArtifactCategory[] = [
  {
    id: 'triggering_events',
    name: 'Triggering Events',
    icon: React.createElement(ExclamationTriangleIcon, { className: 'w-6 h-6' }),
    description: 'Events that directly triggered this alert.',
    hasSubcategories: false,
  },
  {
    id: 'supporting_events',
    name: 'Supporting Events',
    icon: React.createElement(TableCellsIcon, { className: 'w-6 h-6' }),
    description: 'Additional events providing context to the alert.',
    hasSubcategories: false,
  },
  {
    id: 'original-alert',
    name: 'Original Alert',
    icon: React.createElement(BellAlertIcon, { className: 'w-6 h-6' }),
    description: 'Original alert data from the security system.',
    hasSubcategories: false,
  },
  {
    id: 'threat-intel',
    name: 'Threat Intelligence',
    icon: React.createElement(ShieldExclamationIcon, { className: 'w-6 h-6' }),
    description:
      'Threat intelligence data from various providers about the entities involved in this incident.',
    hasSubcategories: true,
    subcategories: [
      {
        id: 'virustotal',
        name: 'VirusTotal',
        description: 'Reputation and analysis data from VirusTotal for IPs, domains, and files.',
      },
    ],
  },
  {
    id: 'edr',
    name: 'EDR Data',
    icon: React.createElement(ComputerDesktopIcon, { className: 'w-6 h-6' }),
    description: 'Endpoint Detection and Response data collected from affected systems.',
    hasSubcategories: true,
    subcategories: [
      {
        id: 'Processes',
        name: 'Process Activities',
        description: 'Information about processes that were executed on the affected systems.',
      },
      {
        id: 'Network_Action',
        name: 'Network Actions',
        description: 'Details about network connections established by the affected systems.',
      },
      {
        id: 'Browser_History',
        name: 'Browser History',
        description: 'Web browsing history from the affected systems.',
      },
      {
        id: 'Terminal_History',
        name: 'Terminal History',
        description: 'Command line history from terminals on the affected systems.',
      },
      {
        id: 'Host_Information',
        name: 'Host Information',
        description: 'System information about the affected hosts.',
      },
    ],
  },
  {
    id: 'vulnerabilities',
    name: 'Vulnerabilities',
    icon: React.createElement(ExclamationTriangleIcon, { className: 'w-6 h-6' }),
    description: 'CVEs and other vulnerabilities exploited in this incident.',
    hasSubcategories: false,
  },
];

// Define the threat intel provider type
interface ThreatIntelProvider {
  id: string;
  name: string;
  filename: string;
}

// List of available threat intel providers
const threatIntelProviders: ThreatIntelProvider[] = [
  {
    id: 'virustotal',
    name: 'VirusTotal',
    filename: 'virus_total.json',
  },
];

// Helper function to convert category ID to directory name
const getCategoryDirectory = (categoryId: string): string => {
  // Find the directory name that maps to this category ID
  const dirName = Object.entries(directoryToCategoryMap).find(
    ([_, catId]) => catId === categoryId
  )?.[0];
  return dirName ?? categoryId;
};

// Helper function to determine content type based on file extension or category
export const determineContentType = (
  filename: string,
  categoryId: string
): 'json' | 'log' | 'text' => {
  // First, check the category - timeline and logs categories should always be treated as logs
  if (categoryId === 'timeline' || categoryId === 'logs') {
    return 'log';
  }

  // Then check the file extension
  if (filename.endsWith('.json')) {
    return 'json';
  } else if (filename.endsWith('.log')) {
    return 'log';
  }

  // Default to text for unknown types
  return 'text';
};

// Helper function to find a file of a specific type in a list of files
const findFileByType = (files: string[], extension: string): string | undefined => {
  return files.find((file) => file.endsWith(extension));
};

// Helper function for checking specific category paths
const checkCategoryPath = async (
  alertId: string,
  categoryDir: string,
  viewDir: string
): Promise<string | undefined> => {
  const basePath = `/mocks/data/alert_details/${alertId}/artifacts/${categoryDir}/${viewDir}/`;

  const files = await listFilesInDirectory(basePath);
  if (files.length === 0) return undefined;

  // Prefer JSON files
  const jsonFile = findFileByType(files, '.json');
  if (jsonFile) return jsonFile;

  // If no JSON file, try to get a log file
  const logFile = findFileByType(files, '.log');
  if (logFile) return logFile;

  // If no specific type found but we have files, return the first one
  return files.length > 0 ? files[0] : undefined;
};

// Helper function for checking subcategory paths
const checkSubcategoryPath = async (
  alertId: string,
  categoryDir: string,
  subcategoryId: string,
  viewDir: string
): Promise<string | undefined> => {
  const basePath = `/mocks/data/alert_details/${alertId}/artifacts/${categoryDir}/${subcategoryId}/${viewDir}/`;

  const files = await listFilesInDirectory(basePath);
  if (files.length === 0) return undefined;

  // Prefer JSON files
  const jsonFile = findFileByType(files, '.json');
  if (jsonFile) return jsonFile;

  // If no JSON file, try to get a log file
  const logFile = findFileByType(files, '.log');
  if (logFile) return logFile;

  return undefined;
};

// Helper function to check file existence
// This is used by other functions in the codebase, keeping for future use
/* istanbul ignore next */
export const checkFileExists = async (filePath: string): Promise<string | undefined> => {
  try {
    const resp = await fetch(filePath);
    return resp.ok ? filePath : undefined;
  } catch (error) {
    console.error(`Error checking file existence: ${String(error)}`);
    return undefined;
  }
};

// Modified buildFilePath function with reduced complexity
const buildFilePath = async (
  alertId: string,
  categoryDir: string,
  subcategoryId: string | undefined,
  viewMode: ArtifactViewMode,
  provider?: string
): Promise<string> => {
  const viewDir = viewMode === 'original' ? 'original' : 'summary';

  // For threat intel, use the provider as the subcategory if not provided
  if (categoryDir === 'threat_intel' && provider && !subcategoryId) {
    subcategoryId = provider;
  }

  // Ensure we're explicitly using the correct view directory
  const basePath = subcategoryId
    ? `/mocks/data/alert_details/${alertId}/artifacts/${categoryDir}/${subcategoryId}/${viewDir}/`
    : `/mocks/data/alert_details/${alertId}/artifacts/${categoryDir}/${viewDir}/`;

  const filePath = subcategoryId
    ? await checkSubcategoryPath(alertId, categoryDir, subcategoryId, viewDir)
    : await checkCategoryPath(alertId, categoryDir, viewDir);

  // If a file was found, return it, otherwise return a default path
  return filePath || `${basePath}not_found.json`;
};

// Helper function to list files in a directory using fetch
const listFilesInDirectory = async (dirPath: string): Promise<string[]> => {
  try {
    // Special direct file check for known paths to avoid directory listing issues
    const directFileResult = await checkDirectFiles(dirPath);
    if (directFileResult.length > 0) {
      return directFileResult;
    }

    // Continue with regular directory listing logic
    // Make a HEAD request to check if the directory exists
    const response = await fetch(dirPath, { method: 'HEAD' });

    if (!response.ok) {
      return [];
    }

    // Get possible files based on directory path
    const possibleFiles = getPossibleFilesForPath(dirPath);

    // Try to HEAD each possible file to see if it exists
    return await checkFilesExistence(possibleFiles);
  } catch {
    return [];
  }
};

// Helper to check for direct file paths for special cases
const checkDirectFiles = async (dirPath: string): Promise<string[]> => {
  // Special direct file check for known paths to avoid directory listing issues
  if (dirPath.includes('triggering_events/original')) {
    const panThreatPath = `${dirPath}pan_threat.log`;
    const resp = await fetch(panThreatPath, { method: 'HEAD' });
    if (resp.ok) {
      return [panThreatPath];
    }
  }

  if (dirPath.includes('supporting_events/original')) {
    const panThreatPath = `${dirPath}pan_threat.log`;
    const resp = await fetch(panThreatPath, { method: 'HEAD' });
    if (resp.ok) {
      return [panThreatPath];
    }
  }

  return [];
};

// Helper to get possible files based on directory path
const getPossibleFilesForPath = (dirPath: string): string[] => {
  // Determine which category/subcategory we're dealing with based on the dirPath
  if (dirPath.includes('threat_intel')) {
    // Add all known threat intel provider files
    const possibleFiles = threatIntelProviders.map((provider) => `${dirPath}${provider.filename}`);
    // Add fallback options in case there are files we don't know about
    return [...possibleFiles, `${dirPath}threat_intelligence.json`, `${dirPath}pan_threat.log`];
  }

  if (dirPath.includes('Browser_History')) {
    return [`${dirPath}browser_history_data.json`];
  }

  if (dirPath.includes('Processes')) {
    return [`${dirPath}processes_data.json`];
  }

  if (dirPath.includes('Terminal_History')) {
    return [`${dirPath}terminal_history_data.json`];
  }

  if (dirPath.includes('Host_Information')) {
    return [`${dirPath}host_information_data.json`];
  }

  if (dirPath.includes('Network_Action')) {
    return [`${dirPath}network_action_data.json`];
  }

  // If we're looking at triggering or supporting events, prioritize log files
  if (dirPath.includes('triggering_events/summary')) {
    return [
      `${dirPath}pan_threat_summary.json`,
      `${dirPath}summary.json`,
      `${dirPath}events_summary.json`,
      `${dirPath}alert_summary.json`,
    ];
  }

  if (dirPath.includes('supporting_events/summary')) {
    return [
      `${dirPath}pan_threat_summary.json`,
      `${dirPath}summary.json`,
      `${dirPath}events_summary.json`,
      `${dirPath}support_summary.json`,
    ];
  }

  // Add specific handling for CVE info summary view
  if (dirPath.includes('cve_info/summary')) {
    return [
      `${dirPath}cveawg_mitre_org.json`,
      `${dirPath}cve_data.json`,
      `${dirPath}vulnerabilities.json`,
      `${dirPath}summary.json`,
    ];
  }

  // Original check for triggering_events and supporting_events (original view)
  if (dirPath.includes('triggering_events')) {
    return [
      `${dirPath}pan_threat.log`,
      `${dirPath}events.log`,
      `${dirPath}alert_events.log`,
      `${dirPath}trigger.log`,
    ];
  }

  if (dirPath.includes('supporting_events')) {
    return [
      `${dirPath}pan_threat.log`,
      `${dirPath}events.log`,
      `${dirPath}support_events.log`,
      `${dirPath}related_events.log`,
    ];
  }

  // For CVE info, check for specific files
  if (dirPath.includes('cve_info')) {
    // Give priority to the proper file based on viewMode
    if (dirPath.includes('/summary/')) {
      return [
        `${dirPath}cveawg_mitre_org.json`, // First priority for summary CVE data
        `${dirPath}cve_data.json`,
        `${dirPath}vulnerabilities.json`,
        `${dirPath}summary.json`,
      ];
    }

    return [
      `${dirPath}cveawg_mitre_org.json`,
      `${dirPath}cve_data.json`,
      `${dirPath}vulnerabilities.json`,
      `${dirPath}pan_threat.log`,
    ];
  }

  // Default possible files if no specific subcategory is matched
  return [
    `${dirPath}data.json`,
    `${dirPath}report.json`,
    `${dirPath}summary.json`,
    `${dirPath}log_data.json`,
    `${dirPath}pan_threat.log`,
  ];
};

// Helper to check if multiple files exist
const checkFilesExistence = async (filePaths: string[]): Promise<string[]> => {
  const fileCheckPromises = filePaths.map(async (filePath) => {
    try {
      const resp = await fetch(filePath, { method: 'HEAD' });
      return resp.ok ? filePath : undefined;
    } catch {
      return;
    }
  });

  const results = await Promise.all(fileCheckPromises);
  return results.filter((path): path is string => path !== undefined);
};

// Helper to process the response data based on content type
const processResponseData = async (
  response: Response,
  contentType: 'json' | 'log' | 'text'
): Promise<unknown> => {
  if (contentType === 'json') {
    return (await response.json()) as Record<string, unknown>;
  }

  // For logs and text, return as string
  return await response.text();
};

// Helper for loading view mode content
const loadViewContent = async (
  alertId: string,
  categoryDir: string,
  subcategory: string | undefined,
  viewMode: ArtifactViewMode,
  provider?: string
): Promise<{
  filePath: string;
  contentType: 'json' | 'log' | 'text';
  data: unknown;
}> => {
  // Build the file path for the current view mode
  const filePath = await buildFilePath(alertId, categoryDir, subcategory, viewMode, provider);

  // Fetch the content from the file
  const response = await fetch(filePath);

  if (!response.ok) {
    throw new Error(`Failed to load file: ${filePath}`);
  }

  const contentType = determineContentType(filePath, categoryDir);
  const data = await processResponseData(response, contentType);

  return { filePath, contentType, data };
};

// Helper to attempt loading the alternate view mode data
const loadAlternateViewData = async (
  alertId: string,
  categoryDir: string,
  subcategory: string | undefined,
  currentViewMode: ArtifactViewMode,
  provider?: string
): Promise<unknown> => {
  const otherViewMode = currentViewMode === 'original' ? 'summary' : 'original';

  try {
    const otherFilePath = await buildFilePath(
      alertId,
      categoryDir,
      subcategory,
      otherViewMode,
      provider
    );

    const otherResponse = await fetch(otherFilePath);

    if (!otherResponse.ok) {
      return undefined;
    }

    const otherContentType = determineContentType(otherFilePath, categoryDir);
    return await processResponseData(otherResponse, otherContentType);
  } catch {
    // Silently return undefined if we can't load the other view
    return undefined;
  }
};

// Modified loadArtifactContent function to support provider parameter
export const loadArtifactContent = async (
  config: ArtifactContentConfig
): Promise<ArtifactContent> => {
  const { alertId, category, subcategory, viewMode = 'original', provider } = config;

  try {
    const categoryDir = getCategoryDirectory(category);

    // Load the requested view data
    const { contentType, data } = await loadViewContent(
      alertId,
      categoryDir,
      subcategory,
      viewMode,
      provider
    );

    // Try to load data for the alternate view mode
    const otherViewData = await loadAlternateViewData(
      alertId,
      categoryDir,
      subcategory,
      viewMode,
      provider
    );

    // Determine summary data based on view mode
    let summaryData: Record<string, unknown> | undefined;
    if (viewMode === 'original' && otherViewData && typeof otherViewData === 'object') {
      summaryData = otherViewData as Record<string, unknown>;
    }

    // Special handling for vulnerabilities (CVE info)
    if (category === 'vulnerabilities') {
      if (viewMode === 'summary') {
        // In summary mode, we use the loaded data as the summary data
        return {
          contentType,
          category,
          subcategory,
          data: undefined, // Don't show original data in summary mode
          summaryData: data as Record<string, unknown>,
        };
      } else if (viewMode === 'original' && otherViewData) {
        // In original mode with available summary data
        return {
          contentType,
          category,
          subcategory,
          data: data as Record<string, unknown>,
          summaryData: otherViewData as Record<string, unknown>,
        };
      }
    }

    // Return the final content
    return {
      contentType,
      category,
      subcategory,
      data,
      summaryData,
    };
  } catch {
    // If there was an error loading the file, use the fallback mock data
    return fallbackToMockData(category, subcategory, viewMode);
  }
};

// Function to provide fallback data when real data cannot be loaded
const fallbackToMockData = (
  categoryId: string,
  subcategoryId?: string,
  viewMode: ArtifactViewMode = 'original'
): ArtifactContent => {
  // Always use 'json' as the content type for fallbacks - simpler to handle
  const contentType = 'json';

  // Minimal fallback data
  const data = {
    error: true,
    message: `Failed to load data for ${categoryId}${subcategoryId ? ' - ' + subcategoryId : ''}`,
    category: categoryId,
    subcategory: subcategoryId || '',
    viewMode: viewMode,
  };

  // Minimal fallback summary data
  const summaryData = {
    error: true,
    message: `Failed to load summary data for ${categoryId}${subcategoryId ? ' - ' + subcategoryId : ''}`,
  };

  return {
    contentType,
    category: categoryId,
    subcategory: subcategoryId,
    data,
    summaryData: viewMode === 'summary' ? summaryData : undefined,
  };
};

export const getArtifactIcon = (category: string) =>
  category === 'edr' ? TableCellsIcon : DocumentTextIcon;
