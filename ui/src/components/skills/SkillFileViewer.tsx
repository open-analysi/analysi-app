import React, { useEffect } from 'react';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { useSkillStore } from '../../store/skillStore';
import { SkillFileContent } from '../../types/skill';

interface SkillFileViewerProps {
  skillId: string;
  filePath: string | null;
}

export const SkillFileViewer: React.FC<SkillFileViewerProps> = ({ skillId, filePath }) => {
  const { runSafe } = useErrorHandler('SkillFileViewer');
  const { fileContent, setFileContent, fileLoading, setFileLoading, skillTree } = useSkillStore();

  useEffect(() => {
    if (!filePath) {
      setFileContent(null);
      return;
    }

    const fetchFile = async () => {
      setFileLoading(true);

      // Try the skill file endpoint first
      const [result] = await runSafe(backendApi.getSkillFile(skillId, filePath), 'fetchSkillFile', {
        action: 'fetching skill file',
        entityId: skillId,
      });

      if (result) {
        setFileContent(result);
        setFileLoading(false);
        return;
      }

      // Fallback: look up document_id from tree and fetch via knowledge-units API
      const treeFile = skillTree.find((f) => f.path === filePath);
      if (treeFile?.document_id) {
        const [docResult] = await runSafe(
          backendApi.getDocument(treeFile.document_id),
          'fetchDocument',
          { action: 'fetching document content', entityId: treeFile.document_id }
        );
        if (docResult) {
          const doc = docResult;
          setFileContent({
            path: filePath,
            document_id: treeFile.document_id,
            name: doc.name,
            content: doc.content,
            markdown_content: doc.content,
            doc_format: doc.document_type,
            document_type: doc.document_type,
            metadata: {},
          } as SkillFileContent);
        }
      }

      setFileLoading(false);
    };
    void fetchFile();
  }, [skillId, filePath, skillTree, runSafe, setFileContent, setFileLoading]);

  if (!filePath) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500 text-sm">
        Select a file from the sidebar to view its content
      </div>
    );
  }

  if (fileLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!fileContent) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500 text-sm">
        File not found
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4">
        <h3 className="text-sm font-medium text-gray-300">{fileContent.path}</h3>
        {fileContent.document_type && (
          <span className="text-xs text-gray-500 mt-1">{fileContent.document_type}</span>
        )}
      </div>
      <div className="bg-dark-800 border border-gray-700/30 rounded-lg p-4 overflow-x-auto">
        <pre className="text-sm text-gray-200 whitespace-pre-wrap font-mono">
          {fileContent.markdown_content || fileContent.content}
        </pre>
      </div>
    </div>
  );
};
