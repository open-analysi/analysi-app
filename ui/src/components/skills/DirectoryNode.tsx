import React, { useState } from 'react';

import {
  ChevronDownIcon,
  ChevronRightIcon,
  FolderIcon,
  FolderOpenIcon,
} from '@heroicons/react/24/outline';

import { FileTreeNode } from './FileTreeNode';

export interface TreeNode {
  name: string;
  /** True for directory nodes, false for file nodes */
  isDirectory: boolean;
  /** Full path — only present on file nodes */
  path?: string;
  /** Only present on file nodes */
  document_id?: string;
  staged?: boolean;
  /** Child directories and files */
  children: TreeNode[];
}

interface DirectoryNodeProps {
  node: TreeNode;
  selectedFilePath: string | null;
  onSelectFile: (filePath: string) => void;
  depth: number;
  defaultOpen?: boolean;
}

export const DirectoryNode: React.FC<DirectoryNodeProps> = ({
  node,
  selectedFilePath,
  onSelectFile,
  depth,
  defaultOpen = true,
}) => {
  const [open, setOpen] = useState(defaultOpen);

  if (!node.isDirectory) {
    return (
      <FileTreeNode
        file={{ path: node.path ?? '', document_id: node.document_id ?? '', staged: node.staged ?? false }}
        isActive={Boolean(node.path && node.path === selectedFilePath)}
        onSelect={onSelectFile}
        depth={depth}
      />
    );
  }

  // Directory node
  const dirs = node.children.filter((c) => c.isDirectory);
  const files = node.children.filter((c) => !c.isDirectory);

  return (
    <div>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="w-full flex items-center gap-1.5 py-1.5 text-left text-sm text-gray-300 hover:bg-dark-700/50 hover:text-gray-100 transition-colors"
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
      >
        {open ? (
          <ChevronDownIcon className="w-3.5 h-3.5 shrink-0 text-gray-500" />
        ) : (
          <ChevronRightIcon className="w-3.5 h-3.5 shrink-0 text-gray-500" />
        )}
        {open ? (
          <FolderOpenIcon className="w-4 h-4 shrink-0 text-yellow-500" />
        ) : (
          <FolderIcon className="w-4 h-4 shrink-0 text-yellow-500" />
        )}
        <span className="truncate">{node.name}</span>
      </button>
      {open && (
        <div>
          {dirs.map((child) => (
            <DirectoryNode
              key={child.name}
              node={child}
              selectedFilePath={selectedFilePath}
              onSelectFile={onSelectFile}
              depth={depth + 1}
              defaultOpen={defaultOpen}
            />
          ))}
          {files.map((child) => (
            <DirectoryNode
              key={child.path}
              node={child}
              selectedFilePath={selectedFilePath}
              onSelectFile={onSelectFile}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
};
