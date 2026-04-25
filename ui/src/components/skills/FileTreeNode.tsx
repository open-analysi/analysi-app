import React from 'react';

import { DocumentTextIcon } from '@heroicons/react/24/outline';

import { SkillFile } from '../../types/skill';

interface FileTreeNodeProps {
  file: SkillFile;
  isActive: boolean;
  onSelect: (filePath: string) => void;
  depth?: number;
}

export const FileTreeNode: React.FC<FileTreeNodeProps> = ({
  file,
  isActive,
  onSelect,
  depth = 0,
}) => {
  const fileName = file.path.split('/').pop() || file.path;

  return (
    <button
      onClick={() => onSelect(file.path)}
      className={`w-full flex items-center gap-2 pr-3 py-1.5 text-left text-sm transition-colors ${
        isActive
          ? 'bg-primary/10 text-primary'
          : 'text-gray-400 hover:bg-dark-700/50 hover:text-gray-200'
      }`}
      style={{ paddingLeft: `${depth * 12 + 8}px` }}
      title={file.path}
    >
      {file.staged ? (
        <span className="w-4 h-4 shrink-0 text-center text-xs leading-4 text-yellow-400">
          &#9676;
        </span>
      ) : (
        <DocumentTextIcon className="w-4 h-4 shrink-0" />
      )}
      <span className="truncate">{fileName}</span>
    </button>
  );
};
