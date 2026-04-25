import React, { useCallback, useEffect, useRef, useState } from 'react';

import {
  ArrowUpTrayIcon,
  DocumentTextIcon,
  TrashIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { useSkillStore } from '../../store/skillStore';
import { StagedDocument } from '../../types/skill';

interface KnowledgeOnboardingProps {
  skillId: string;
  onSwitchTab?: (tab: string) => void;
}

export const KnowledgeOnboarding: React.FC<KnowledgeOnboardingProps> = ({
  skillId,
  onSwitchTab,
}) => {
  const { runSafe } = useErrorHandler('KnowledgeOnboarding');
  const { stagedDocuments, setStagedDocuments, reviewing, setReviewing } = useSkillStore();
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch staged documents
  useEffect(() => {
    const fetchStaged = async () => {
      const [result] = await runSafe(
        backendApi.getStagedDocuments(skillId),
        'fetchStagedDocuments',
        { action: 'fetching staged documents', entityId: skillId }
      );
      if (result) {
        setStagedDocuments(result);
      }
    };
    void fetchStaged();
  }, [skillId, runSafe, setStagedDocuments]);

  const handleFiles = useCallback(
    async (files: FileList) => {
      setUploading(true);
      for (const file of Array.from(files)) {
        const content = await file.text();
        const baseName = file.name.replace(/\.[^.]+$/, '');
        const suffix = Date.now().toString(36);
        const cyName = `${baseName}_${suffix}`
          .toLowerCase()
          .replace(/[^a-z0-9_]/g, '_')
          .replace(/^[^a-z]/, 'f');
        const [doc] = await runSafe(
          backendApi.createDocument({
            name: file.name,
            content,
            doc_format: file.name.endsWith('.md') ? 'markdown' : 'text',
            cy_name: cyName,
          }),
          'createDocument',
          { action: 'creating document', entityId: file.name }
        );
        if (doc?.id) {
          await runSafe(
            backendApi.stageDocument(skillId, {
              document_id: doc.id,
              namespace_path: file.name,
            }),
            'stageDocument',
            { action: 'staging document', entityId: skillId }
          );
        }
      }
      // Refresh staged docs
      const [refreshed] = await runSafe(
        backendApi.getStagedDocuments(skillId),
        'refreshStagedDocuments',
        { action: 'refreshing staged documents', entityId: skillId }
      );
      if (refreshed) {
        setStagedDocuments(refreshed);
      }
      setUploading(false);
    },
    [skillId, runSafe, setStagedDocuments]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      if (e.dataTransfer.files.length > 0) {
        void handleFiles(e.dataTransfer.files);
      }
    },
    [handleFiles]
  );

  const handleUnstage = useCallback(
    async (doc: StagedDocument) => {
      await runSafe(backendApi.unstageDocument(skillId, doc.document_id), 'unstageDocument', {
        action: 'unstaging document',
        entityId: doc.document_id,
      });
      setStagedDocuments(stagedDocuments.filter((d) => d.document_id !== doc.document_id));
    },
    [skillId, runSafe, stagedDocuments, setStagedDocuments]
  );

  const handleExtract = useCallback(async () => {
    if (stagedDocuments.length === 0) return;
    setReviewing(true);
    for (const doc of stagedDocuments) {
      await runSafe(
        backendApi.createContentReview(skillId, { document_id: doc.document_id }),
        'createContentReview',
        { action: 'creating content review', entityId: skillId }
      );
    }
    setReviewing(false);
    onSwitchTab?.('reviews');
  }, [skillId, stagedDocuments, runSafe, setReviewing, onSwitchTab]);

  return (
    <div className="space-y-6">
      {/* Upload Dropzone */}
      <button
        type="button"
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`w-full border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragActive
            ? 'border-primary bg-primary/5'
            : 'border-gray-600/50 hover:border-gray-500 bg-dark-800'
        }`}
      >
        <ArrowUpTrayIcon className="w-8 h-8 mx-auto text-gray-400 mb-3" />
        <p className="text-sm text-gray-300">
          {uploading ? 'Uploading...' : 'Drop .md or .txt files here, or click to upload'}
        </p>
        <p className="text-xs text-gray-500 mt-1">Files will be staged for extraction</p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".md,.txt,.markdown"
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              void handleFiles(e.target.files);
            }
          }}
        />
      </button>

      {/* Staged Documents */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-gray-300">
            Staged Documents ({stagedDocuments.length})
          </h3>
          {stagedDocuments.length > 0 && (
            <div className="flex items-center gap-3">
              {reviewing && (
                <span className="text-xs text-yellow-400">This may take several minutes...</span>
              )}
              <button
                onClick={() => void handleExtract()}
                disabled={reviewing}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {reviewing ? (
                  <>
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Reviewing...
                  </>
                ) : (
                  <>
                    <SparklesIcon className="w-4 h-4" />
                    Extract
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {stagedDocuments.length === 0 ? (
          <p className="text-sm text-gray-500">No staged documents. Upload files above to begin.</p>
        ) : (
          <div className="space-y-2">
            {stagedDocuments.map((doc) => (
              <div
                key={doc.document_id}
                className="flex items-center justify-between bg-dark-800 border border-gray-700/30 rounded-md px-3 py-2"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <DocumentTextIcon className="w-4 h-4 text-yellow-400 shrink-0" />
                  <span className="text-sm text-gray-200 truncate">{doc.path}</span>
                </div>
                <button
                  onClick={() => void handleUnstage(doc)}
                  className="text-gray-500 hover:text-red-400 transition-colors shrink-0 ml-2"
                  title="Unstage"
                >
                  <TrashIcon className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
