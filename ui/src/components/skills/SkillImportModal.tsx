import React, { useCallback, useRef, useState } from 'react';

import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react';
import {
  ArrowPathIcon,
  ArrowUpTrayIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import type { SkillImportResponse } from '../../types/skill';

interface ProblemDetail {
  title: string;
  detail?: string | null;
  hint?: string | null;
  error_code?: string | null;
  status?: number;
}

function extractProblemDetail(err: unknown): ProblemDetail {
  const data = (err as { response?: { data?: ProblemDetail } })?.response?.data;
  if (data?.title) return data;

  const message = err instanceof Error ? err.message : 'An unexpected error occurred.';
  return { title: 'Import failed', detail: message };
}

interface SkillImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImported?: (skillId: string) => void;
}

export const SkillImportModal: React.FC<SkillImportModalProps> = ({
  isOpen,
  onClose,
  onImported,
}) => {
  const { runSafe } = useErrorHandler('SkillImportModal');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [dragActive, setDragActive] = useState(false);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<SkillImportResponse | null>(null);
  const [importError, setImportError] = useState<ProblemDetail | null>(null);

  const reset = useCallback(() => {
    setResult(null);
    setImportError(null);
    setImporting(false);
    setDragActive(false);
  }, []);

  const handleClose = useCallback(() => {
    reset();
    onClose();
  }, [reset, onClose]);

  const handleFile = useCallback(
    async (file: File) => {
      setImporting(true);
      setImportError(null);
      setResult(null);

      const [response, err] = await runSafe(backendApi.importSkill(file), 'importSkill', {
        action: 'importing skill',
      });

      if (err) {
        setImportError(extractProblemDetail(err));
        setImporting(false);
        return;
      }

      if (response) {
        setResult(response);
      }
      setImporting(false);
    },
    [runSafe]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const file = e.dataTransfer.files[0];
      if (file) void handleFile(file);
    },
    [handleFile]
  );

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) void handleFile(file);
    },
    [handleFile]
  );

  const handleTryAgain = useCallback(() => {
    setImportError(null);
    setResult(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  return (
    <Dialog open={isOpen} onClose={handleClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/50" aria-hidden="true" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel className="mx-auto rounded-lg bg-dark-800 p-6 w-full max-w-lg max-h-[90vh] flex flex-col">
          {/* Header */}
          <div className="flex justify-between items-start mb-4">
            <div>
              <DialogTitle className="text-xl font-semibold text-white">Import Skill</DialogTitle>
              <p className="text-gray-400 text-sm mt-1">
                Upload a skill package to add it to your knowledge base
              </p>
            </div>
            <button
              onClick={handleClose}
              className="text-gray-400 hover:text-white transition-colors"
              aria-label="Close"
            >
              <XMarkIcon className="w-6 h-6" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto">
            {!result && !importing && !importError && (
              <>
                {/* Drop zone */}
                <button
                  type="button"
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragActive(true);
                  }}
                  onDragLeave={() => setDragActive(false)}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`w-full border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${
                    dragActive
                      ? 'border-primary bg-primary/5'
                      : 'border-gray-600/50 hover:border-gray-500 bg-dark-800'
                  }`}
                  data-testid="import-dropzone"
                >
                  <ArrowUpTrayIcon className="w-10 h-10 mx-auto text-gray-400 mb-3" />
                  <p className="text-sm text-gray-300">
                    Drop a .zip or .skill package here, or click to browse
                  </p>
                </button>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,.skill"
                  className="hidden"
                  onChange={handleInputChange}
                  data-testid="import-file-input"
                />
              </>
            )}

            {importing && (
              <div className="flex flex-col items-center justify-center py-12">
                <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mb-4" />
                <p className="text-sm text-gray-300">Importing skill...</p>
              </div>
            )}

            {importError && (
              <div className="space-y-3" data-testid="import-error">
                <div className="flex items-start gap-3 bg-red-900/20 border border-red-500/30 rounded-lg p-4">
                  <ExclamationTriangleIcon className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-red-400">{importError.title}</p>
                    {importError.detail && (
                      <p className="text-xs text-gray-400 mt-1">{importError.detail}</p>
                    )}
                  </div>
                </div>

                {importError.hint && (
                  <div className="bg-dark-800 border border-gray-700/30 rounded-lg p-4">
                    <p className="text-xs font-medium text-gray-300 mb-1">How to fix</p>
                    <p className="text-xs text-gray-400 whitespace-pre-line">{importError.hint}</p>
                  </div>
                )}
              </div>
            )}

            {result && (
              <div className="space-y-4">
                <div className="flex items-start gap-3 bg-green-900/20 border border-green-500/30 rounded-lg p-4">
                  <CheckCircleIcon className="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-green-400">Import successful</p>
                    <p className="text-xs text-gray-400 mt-1">
                      Skill &quot;{result.name}&quot; imported with {result.documents_submitted}{' '}
                      document{result.documents_submitted !== 1 ? 's' : ''} submitted for review.
                    </p>
                    {result.review_ids.length > 0 && (
                      <p className="text-xs text-gray-500 mt-1">
                        {result.review_ids.length} review{result.review_ids.length !== 1 ? 's' : ''}{' '}
                        created.
                      </p>
                    )}
                  </div>
                </div>

                {result.sync_failures && result.sync_failures.length > 0 && (
                  <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-4">
                    <p className="text-sm font-medium text-yellow-400 mb-2">Sync failures</p>
                    <ul className="text-xs text-gray-400 space-y-1">
                      {result.sync_failures.map((f, i) => (
                        <li key={i} className="font-mono">
                          {JSON.stringify(f)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end space-x-3 mt-6">
            {result && (
              <>
                <button
                  onClick={handleClose}
                  className="px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-sm text-white text-sm"
                >
                  Close
                </button>
                <button
                  onClick={() => {
                    onImported?.(result.skill_id);
                    handleClose();
                  }}
                  className="px-4 py-2 bg-primary hover:bg-primary-dark rounded-sm text-white text-sm font-medium"
                >
                  Go to Skill
                </button>
              </>
            )}
            {importError && (
              <>
                <button
                  onClick={handleClose}
                  className="px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-sm text-white text-sm"
                >
                  Cancel
                </button>
                <button
                  onClick={handleTryAgain}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary-dark rounded-sm text-white text-sm font-medium"
                >
                  <ArrowPathIcon className="w-4 h-4" />
                  Try Again
                </button>
              </>
            )}
            {!result && !importError && (
              <button
                onClick={handleClose}
                className="px-4 py-2 bg-dark-700 hover:bg-dark-600 rounded-sm text-white text-sm"
              >
                Cancel
              </button>
            )}
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  );
};
