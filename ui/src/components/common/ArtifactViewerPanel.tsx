import React, { useEffect, useCallback, useState } from 'react';

import { Dialog, DialogPanel, DialogTitle, Transition, TransitionChild } from '@headlessui/react';
import {
  XMarkIcon,
  ClipboardDocumentIcon,
  ArrowDownTrayIcon,
  CheckIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import moment from 'moment-timezone';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { useTimezoneStore } from '../../store/timezoneStore';
import { Artifact } from '../../types/artifact';
import { formatBytes } from '../../utils/formatUtils';

interface ArtifactViewerPanelProps {
  artifact: Artifact;
  onClose: () => void;
}

// Helper to format content as string
const formatContentAsString = (content: string | Record<string, unknown> | null): string => {
  if (content === null) {
    return '';
  }
  if (typeof content === 'string') {
    try {
      const parsed: unknown = JSON.parse(content);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return content;
    }
  }
  return JSON.stringify(content, null, 2);
};

// Helper to get base64 image src
const getBase64ImageSrc = (
  mimeType: string,
  content: string | Record<string, unknown> | null
): string => {
  if (typeof content === 'string') {
    return `data:${mimeType};base64,${content}`;
  }
  return '';
};

export const ArtifactViewerPanel: React.FC<ArtifactViewerPanelProps> = ({
  artifact: initialArtifact,
  onClose,
}) => {
  const { timezone } = useTimezoneStore();
  const { runSafe } = useErrorHandler('ArtifactViewerPanel');
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const [artifact, setArtifact] = useState<Artifact>(initialArtifact);

  // Fetch full artifact with content when panel opens
  useEffect(() => {
    const fetchFullArtifact = async () => {
      setLoading(true);
      const [fullArtifact] = await runSafe(
        backendApi.getArtifact(initialArtifact.id),
        'fetchArtifact',
        { action: 'fetching artifact content', entityId: initialArtifact.id }
      );
      if (fullArtifact) {
        setArtifact(fullArtifact);
      }
      setLoading(false);
    };

    void fetchFullArtifact();
  }, [initialArtifact.id, runSafe]);

  // Handle Escape key
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || event.key === 'Esc') {
        event.preventDefault();
        event.stopPropagation();
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape, true);
    return () => document.removeEventListener('keydown', handleEscape, true);
  }, [onClose]);

  const getContentString = useCallback((): string => {
    return formatContentAsString(artifact.content ?? null);
  }, [artifact.content]);

  const handleCopyToClipboard = async () => {
    const content = getContentString();
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const handleDownload = () => {
    if (artifact.download_url) {
      window.open(artifact.download_url, '_blank');
    } else {
      const content = getContentString();
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

  const formatTimestamp = (dateStr: string): string => {
    return moment(dateStr).tz(timezone).format('MMM D, YYYY h:mm A');
  };

  const isImage = artifact.mime_type?.startsWith('image/');
  const isJson = artifact.mime_type === 'application/json';
  const content = getContentString();

  // Render content based on type - extracted to avoid nested ternaries
  const renderContent = (): React.ReactElement => {
    // Loading state
    if (loading) {
      return (
        <div className="flex flex-col items-center justify-center h-full text-gray-400">
          <ArrowPathIcon className="h-8 w-8 animate-spin mb-4" />
          <p>Loading content...</p>
        </div>
      );
    }

    // Image with download URL
    if (isImage && artifact.download_url) {
      return (
        <div className="flex items-center justify-center h-full">
          <img
            src={artifact.download_url}
            alt={artifact.name}
            className="max-w-full max-h-full object-contain rounded-lg"
          />
        </div>
      );
    }

    // Image with inline base64 content
    if (isImage && artifact.content) {
      return (
        <div className="flex items-center justify-center h-full">
          <img
            src={getBase64ImageSrc(artifact.mime_type, artifact.content)}
            alt={artifact.name}
            className="max-w-full max-h-full object-contain rounded-lg"
          />
        </div>
      );
    }

    // Text/JSON content
    if (content) {
      const textColorClass = isJson ? 'text-yellow-300' : 'text-gray-200';
      return (
        <pre
          className={`text-sm p-4 rounded-lg overflow-auto h-full bg-dark-900 ${textColorClass} font-mono whitespace-pre-wrap wrap-break-word`}
        >
          {content}
        </pre>
      );
    }

    // External storage - show download button
    if (artifact.storage_class === 'object') {
      return (
        <div className="flex flex-col items-center justify-center h-full text-gray-400">
          <p className="mb-4">Content stored externally</p>
          <button
            onClick={handleDownload}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary/90 text-white rounded-md transition-colors"
          >
            <ArrowDownTrayIcon className="h-5 w-5" />
            Download File
          </button>
        </div>
      );
    }

    // No content available
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <p>No content available to display</p>
      </div>
    );
  };

  return (
    <Transition show={true} as={React.Fragment}>
      <Dialog onClose={onClose} className="relative z-50">
        {/* Backdrop */}
        <TransitionChild
          as={React.Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/50" aria-hidden="true" />
        </TransitionChild>

        {/* Slide-out Panel */}
        <div className="fixed inset-0 overflow-hidden">
          <div className="absolute inset-0 overflow-hidden">
            <div className="pointer-events-none fixed inset-y-0 right-0 flex max-w-full pl-10">
              <TransitionChild
                as={React.Fragment}
                enter="transform transition ease-in-out duration-300"
                enterFrom="translate-x-full"
                enterTo="translate-x-0"
                leave="transform transition ease-in-out duration-300"
                leaveFrom="translate-x-0"
                leaveTo="translate-x-full"
              >
                <DialogPanel className="pointer-events-auto w-screen max-w-xl">
                  <div className="flex h-full flex-col bg-dark-800 shadow-xl">
                    {/* Header */}
                    <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
                      <div className="flex-1 min-w-0">
                        <DialogTitle className="text-lg font-medium text-white truncate">
                          {artifact.name}
                        </DialogTitle>
                        <p className="text-sm text-gray-400 mt-0.5">
                          {artifact.artifact_type || artifact.mime_type}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 ml-4">
                        <button
                          onClick={() => void handleCopyToClipboard()}
                          className="p-2 text-gray-400 hover:text-gray-200 rounded-md hover:bg-dark-700 transition-colors"
                          title="Copy to clipboard"
                        >
                          {copied ? (
                            <CheckIcon className="h-5 w-5 text-green-400" />
                          ) : (
                            <ClipboardDocumentIcon className="h-5 w-5" />
                          )}
                        </button>
                        <button
                          onClick={handleDownload}
                          className="p-2 text-gray-400 hover:text-gray-200 rounded-md hover:bg-dark-700 transition-colors"
                          title="Download"
                        >
                          <ArrowDownTrayIcon className="h-5 w-5" />
                        </button>
                        <button
                          onClick={onClose}
                          className="p-2 text-gray-400 hover:text-gray-200 rounded-md hover:bg-dark-700 transition-colors"
                          title="Close"
                        >
                          <XMarkIcon className="h-5 w-5" />
                        </button>
                      </div>
                    </div>

                    {/* Metadata */}
                    <div className="px-4 py-3 border-b border-gray-700 bg-dark-900/50">
                      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                        <div>
                          <span className="text-gray-400">Size:</span>
                          <span className="ml-2 text-gray-200">
                            {formatBytes(artifact.size_bytes)}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-400">Created:</span>
                          <span className="ml-2 text-gray-200">
                            {formatTimestamp(artifact.created_at)}
                          </span>
                        </div>
                        {artifact.sha256 && (
                          <div className="col-span-2">
                            <span className="text-gray-400">SHA256:</span>
                            <span className="ml-2 text-gray-200 font-mono text-xs break-all">
                              {artifact.sha256}
                            </span>
                          </div>
                        )}
                        {artifact.source && (
                          <div>
                            <span className="text-gray-400">Source:</span>
                            <span className="ml-2 text-gray-200">{artifact.source}</span>
                          </div>
                        )}
                        {artifact.storage_class && (
                          <div>
                            <span className="text-gray-400">Storage:</span>
                            <span className="ml-2 text-gray-200">{artifact.storage_class}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Content */}
                    <div className="flex-1 overflow-auto p-4">{renderContent()}</div>
                  </div>
                </DialogPanel>
              </TransitionChild>
            </div>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
};
