import React, { useState, useMemo } from 'react';

import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';

import { Skill, SkillFile } from '../../types/skill';

import { SkillTreeItem } from './SkillTreeItem';

interface SkillsSidebarProps {
  skills: Skill[];
  selectedSkillId: string | null;
  selectedFilePath: string | null;
  skillTree: SkillFile[];
  onSelectSkill: (skillId: string) => void;
  onSelectFile: (filePath: string) => void;
}

export const SkillsSidebar: React.FC<SkillsSidebarProps> = ({
  skills,
  selectedSkillId,
  selectedFilePath,
  skillTree,
  onSelectSkill,
  onSelectFile,
}) => {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredSkills = useMemo(() => {
    if (!searchTerm.trim()) return skills;
    const lower = searchTerm.toLowerCase();
    return skills.filter(
      (s) =>
        s.name.toLowerCase().includes(lower) ||
        s.cy_name?.toLowerCase().includes(lower) ||
        s.description?.toLowerCase().includes(lower)
    );
  }, [skills, searchTerm]);

  return (
    <div className="flex flex-col h-full">
      {/* Search */}
      <div className="p-3 border-b border-gray-700/30">
        <div className="relative">
          <MagnifyingGlassIcon className="absolute left-2.5 top-2.5 w-4 h-4 text-gray-500" />
          <input
            type="text"
            placeholder="Search skills..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-8 pr-3 py-2 text-sm bg-dark-700 border border-gray-600/30 rounded-md text-gray-200 placeholder-gray-500 focus:outline-hidden focus:ring-1 focus:ring-primary focus:border-primary"
          />
        </div>
      </div>

      {/* Skills List */}
      <div className="flex-1 overflow-y-auto py-1">
        {filteredSkills.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-gray-500">
            {searchTerm ? 'No skills match your search' : 'No skills found'}
          </div>
        ) : (
          filteredSkills.map((skill) => (
            <SkillTreeItem
              key={skill.id}
              skill={skill}
              isSelected={skill.id === selectedSkillId}
              selectedFilePath={selectedFilePath}
              files={skill.id === selectedSkillId ? skillTree : []}
              onSelectSkill={onSelectSkill}
              onSelectFile={onSelectFile}
            />
          ))
        )}
      </div>
    </div>
  );
};
