import React, { useState, useMemo, useEffect } from 'react';

import {
  ArrowPathIcon,
  DocumentIcon,
  ArrowDownTrayIcon,
  EyeIcon,
  PhotoIcon,
  CodeBracketIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';
import moment from 'moment-timezone';

import { useTimezoneStore } from '../../store/timezoneStore';
import { componentStyles } from '../../styles/components';
import { Artifact } from '../../types/artifact';
import { formatBytes } from '../../utils/formatUtils';

import { ArtifactViewerPanel } from './ArtifactViewerPanel';
import { Pagination } from './Pagination';

const ITEMS_PER_PAGE = 10;

interface ArtifactListProps {
  artifacts: Artifact[];
  loading?: boolean;
  className?: string;
}

export const ArtifactList: React.FC<ArtifactListProps> = ({
  artifacts,
  loading = false,
  className = '',
}) => {
  const { timezone } = useTimezoneStore();
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [currentPage, setCurrentPage] = useState(1);

  // Calculate pagination
  const totalItems = artifacts.length;
  const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);

  // Get paginated items
  const paginatedArtifacts = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const endIndex = startIndex + ITEMS_PER_PAGE;
    return artifacts.slice(startIndex, endIndex);
  }, [artifacts, currentPage]);

  // Reset to page 1 when artifacts change
  useEffect(() => {
    setCurrentPage(1);
  }, [artifacts.length]);

  const getArtifactTypeIcon = (artifact: Artifact) => {
    const mimeType = artifact.mime_type || '';
    const artifactType = artifact.artifact_type || '';

    if (mimeType.startsWith('image/')) {
      return <PhotoIcon className="h-5 w-5 text-purple-400" />;
    }
    if (mimeType === 'application/json' || artifactType === 'json') {
      return <CodeBracketIcon className="h-5 w-5 text-yellow-400" />;
    }
    if (mimeType.startsWith('text/') || artifactType === 'text') {
      return <DocumentTextIcon className="h-5 w-5 text-blue-400" />;
    }
    return <DocumentIcon className="h-5 w-5 text-gray-400" />;
  };

  const getArtifactTypeBadge = (artifact: Artifact) => {
    const type = artifact.artifact_type || 'unknown';
    const baseClasses = 'px-2 py-0.5 text-xs font-medium rounded-full';

    switch (type.toLowerCase()) {
      case 'report':
        return `${baseClasses} bg-blue-100 text-blue-800 dark:bg-blue-800 dark:text-blue-200`;
      case 'ioc_list':
      case 'iocs':
        return `${baseClasses} bg-red-100 text-red-800 dark:bg-red-800 dark:text-red-200`;
      case 'screenshot':
      case 'image':
        return `${baseClasses} bg-purple-100 text-purple-800 dark:bg-purple-800 dark:text-purple-200`;
      case 'json':
        return `${baseClasses} bg-yellow-100 text-yellow-800 dark:bg-yellow-800 dark:text-yellow-200`;
      case 'log':
        return `${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200`;
      default:
        return `${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200`;
    }
  };

  const getSourceLabel = (artifact: Artifact): string => {
    if (artifact.source === 'auto_capture') return 'Auto Capture';
    if (artifact.source === 'cy_script') return 'Cy Script';
    if (artifact.source === 'rest_api') return 'REST API';
    if (artifact.source === 'mcp') return 'MCP';
    return artifact.source || '-';
  };

  const formatTimestamp = (dateStr: string): string => {
    return moment(dateStr).tz(timezone).fromNow();
  };

  const canViewInline = (artifact: Artifact): boolean => {
    // Can view inline if storage_class is 'inline' and content exists
    // Or if it's a text/json type that might be viewable
    if (artifact.storage_class === 'inline' && artifact.content !== null) {
      return true;
    }
    const mimeType = artifact.mime_type || '';
    return (
      mimeType === 'application/json' ||
      mimeType.startsWith('text/') ||
      mimeType.startsWith('image/')
    );
  };

  const handleDownload = (artifact: Artifact) => {
    if (artifact.download_url) {
      window.open(artifact.download_url, '_blank');
    } else if (artifact.content) {
      // Create downloadable content from inline data
      const content =
        typeof artifact.content === 'string'
          ? artifact.content
          : JSON.stringify(artifact.content, null, 2);
      const blob = new Blob([content], { type: artifact.mime_type || 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = artifact.name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <ArrowPathIcon className="h-8 w-8 animate-spin text-gray-400" />
        <span className="ml-2 text-gray-400">Loading artifacts...</span>
      </div>
    );
  }

  if (artifacts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[300px] text-gray-400">
        <DocumentIcon className="h-12 w-12 mb-4" />
        <p className="text-lg mb-2">No Artifacts</p>
        <p className="text-sm">No artifacts were generated during this analysis run</p>
      </div>
    );
  }

  return (
    <>
      <div className={className}>
        {/* Top Pagination */}
        {totalItems > 0 && (
          <div className="mb-2">
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalItems={totalItems}
              itemsPerPage={ITEMS_PER_PAGE}
              onPageChange={setCurrentPage}
            />
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className={componentStyles.tableHeader}>
              <tr>
                <th className={componentStyles.tableHeaderCell}>Name</th>
                <th className={componentStyles.tableHeaderCell}>Type</th>
                <th className={componentStyles.tableHeaderCell}>Size</th>
                <th className={componentStyles.tableHeaderCell}>Source</th>
                <th className={componentStyles.tableHeaderCell}>Created</th>
                <th className={componentStyles.tableHeaderCell}>Actions</th>
              </tr>
            </thead>
            <tbody className={componentStyles.tableBody}>
              {paginatedArtifacts.map((artifact) => (
                <tr key={artifact.id} className={componentStyles.tableRow}>
                  <td className={`${componentStyles.tableCell} font-medium`}>
                    <div className="flex items-center gap-2">
                      {getArtifactTypeIcon(artifact)}
                      <span className="truncate max-w-[200px]" title={artifact.name}>
                        {artifact.name}
                      </span>
                    </div>
                  </td>
                  <td className={componentStyles.tableCell}>
                    <span className={getArtifactTypeBadge(artifact)}>
                      {artifact.artifact_type || 'unknown'}
                    </span>
                  </td>
                  <td className={`${componentStyles.tableCell} text-gray-400`}>
                    {formatBytes(artifact.size_bytes)}
                  </td>
                  <td className={`${componentStyles.tableCell} text-gray-400`}>
                    {getSourceLabel(artifact)}
                  </td>
                  <td className={`${componentStyles.tableCell} text-gray-400`}>
                    {formatTimestamp(artifact.created_at)}
                  </td>
                  <td className={componentStyles.tableCell}>
                    <div className="flex items-center gap-2">
                      {canViewInline(artifact) && (
                        <button
                          onClick={() => setSelectedArtifact(artifact)}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-primary hover:text-primary/80 transition-colors"
                          title="View artifact content"
                        >
                          <EyeIcon className="h-4 w-4" />
                          View
                        </button>
                      )}
                      <button
                        onClick={() => handleDownload(artifact)}
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-400 hover:text-gray-200 transition-colors"
                        title="Download artifact"
                      >
                        <ArrowDownTrayIcon className="h-4 w-4" />
                        Download
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Bottom Pagination */}
        {totalItems > ITEMS_PER_PAGE && (
          <div className="mt-2">
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              totalItems={totalItems}
              itemsPerPage={ITEMS_PER_PAGE}
              onPageChange={setCurrentPage}
            />
          </div>
        )}
      </div>

      {/* Artifact Viewer Panel */}
      {selectedArtifact && (
        <ArtifactViewerPanel
          artifact={selectedArtifact}
          onClose={() => setSelectedArtifact(null)}
        />
      )}
    </>
  );
};
