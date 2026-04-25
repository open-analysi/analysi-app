import React, { useMemo } from 'react';

import { ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/outline';

import { Skill, SkillFile } from '../../types/skill';

import { DirectoryNode, TreeNode } from './DirectoryNode';

/**
 * Build a nested tree structure from flat file paths.
 * e.g. ["common/universal/alert.md", "repository/sql.md"] becomes:
 *   common/ -> universal/ -> alert.md
 *   repository/ -> sql.md
 */
function buildTree(files: SkillFile[]): TreeNode[] {
  const root: TreeNode = { name: '', isDirectory: true, children: [] };

  for (const file of files) {
    const parts = file.path.split('/');
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;

      if (isLast) {
        current.children.push({
          name: part,
          isDirectory: false,
          path: file.path,
          document_id: file.document_id,
          staged: file.staged,
          children: [],
        });
      } else {
        let dir = current.children.find((c) => c.isDirectory && c.name === part);
        if (!dir) {
          dir = { name: part, isDirectory: true, children: [] };
          current.children.push(dir);
        }
        current = dir;
      }
    }
  }

  return root.children;
}

interface SkillTreeItemProps {
  skill: Skill;
  isSelected: boolean;
  selectedFilePath: string | null;
  files: SkillFile[];
  onSelectSkill: (skillId: string) => void;
  onSelectFile: (filePath: string) => void;
}

export const SkillTreeItem: React.FC<SkillTreeItemProps> = ({
  skill,
  isSelected,
  selectedFilePath,
  files,
  onSelectSkill,
  onSelectFile,
}) => {
  const tree = useMemo(() => buildTree(files), [files]);

  // Separate top-level directories and files
  const dirs = tree.filter((n) => n.isDirectory);
  const leafFiles = tree.filter((n) => !n.isDirectory);

  return (
    <div>
      {/* Skill Header */}
      <button
        onClick={() => onSelectSkill(skill.id)}
        className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm transition-colors ${
          isSelected
            ? 'bg-dark-700 text-white'
            : 'text-gray-300 hover:bg-dark-700/50 hover:text-gray-100'
        }`}
      >
        {isSelected ? (
          <ChevronDownIcon className="w-4 h-4 shrink-0 text-gray-400" />
        ) : (
          <ChevronRightIcon className="w-4 h-4 shrink-0 text-gray-400" />
        )}
        <span className="truncate font-medium">{skill.name}</span>
      </button>

      {/* Directory Tree (when expanded) */}
      {isSelected && files.length > 0 && (
        <div className="ml-2">
          {dirs.map((node) => (
            <DirectoryNode
              key={node.name}
              node={node}
              selectedFilePath={selectedFilePath}
              onSelectFile={onSelectFile}
              depth={1}
            />
          ))}
          {leafFiles.map((node) => (
            <DirectoryNode
              key={node.path}
              node={node}
              selectedFilePath={selectedFilePath}
              onSelectFile={onSelectFile}
              depth={1}
            />
          ))}
        </div>
      )}
    </div>
  );
};
