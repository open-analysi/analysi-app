import React, { useCallback, useEffect, useState } from 'react';

import {
  ArrowLeftIcon,
  ArrowUpTrayIcon,
  BookOpenIcon,
  ExclamationTriangleIcon,
  PencilSquareIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { useSearchParams } from 'react-router';

import useErrorHandler from '../../hooks/useErrorHandler';
import { useUrlState } from '../../hooks/useUrlState';
import { backendApi } from '../../services/backendApi';
import { useSkillStore } from '../../store/skillStore';
import type { Skill } from '../../types/skill';
import { ConfirmDialog } from '../common/ConfirmDialog';

import { ContentReviewList } from './ContentReviewList';
import { KnowledgeOnboarding } from './KnowledgeOnboarding';
import { SkillFileViewer } from './SkillFileViewer';
import { SkillImportModal } from './SkillImportModal';
import { SkillsSidebar } from './SkillsSidebar';

type TabId = 'viewer' | 'onboarding' | 'reviews';

export const SkillsLayout: React.FC = () => {
  const { runSafe } = useErrorHandler('SkillsLayout');
  const [, setSearchParams] = useSearchParams();

  const [activeTab, setActiveTab] = useUrlState<string>('tab', 'viewer');
  const [selectedSkillParam] = useUrlState<string>('skill', '');
  const [selectedFileParam] = useUrlState<string>('file', '');

  const {
    skills,
    setSkills,
    selectedSkillId,
    setSelectedSkillId,
    selectedFilePath,
    setSelectedFilePath,
    skillTree,
    setSkillTree,
    setLoading,
    setTreeLoading,
  } = useSkillStore();

  const [showImportModal, setShowImportModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; skill: Skill | null }>({
    isOpen: false,
    skill: null,
  });

  const selectedSkill = skills.find((s) => s.id === selectedSkillId);

  // Fetch skills on mount
  useEffect(() => {
    const fetchSkills = async () => {
      setLoading(true);
      const [result] = await runSafe(backendApi.getSkills(), 'fetchSkills', {
        action: 'fetching skills list',
      });
      if (result) {
        setSkills(result.skills || []);
      }
      setLoading(false);
    };
    void fetchSkills();
  }, [runSafe, setSkills, setLoading]);

  // Sync URL param to store on mount
  useEffect(() => {
    if (selectedSkillParam && selectedSkillParam !== selectedSkillId) {
      setSelectedSkillId(selectedSkillParam);
    }
  }, [selectedSkillParam]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selectedFileParam && selectedFileParam !== selectedFilePath) {
      setSelectedFilePath(selectedFileParam);
    }
  }, [selectedFileParam]); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshTree = useCallback(async () => {
    if (!selectedSkillId) return;
    setTreeLoading(true);
    const [result] = await runSafe(backendApi.getSkillTree(selectedSkillId), 'fetchSkillTree', {
      action: 'fetching skill tree',
      entityId: selectedSkillId,
    });
    if (result) {
      setSkillTree(result.files || []);
    }
    setTreeLoading(false);
  }, [selectedSkillId, runSafe, setSkillTree, setTreeLoading]);

  // Fetch tree when skill changes
  useEffect(() => {
    if (!selectedSkillId) return;
    void refreshTree();
  }, [selectedSkillId, refreshTree]);

  const handleSelectSkill = useCallback(
    (skillId: string) => {
      const isToggleOff = skillId === selectedSkillId;
      setSelectedSkillId(isToggleOff ? null : skillId);
      const skill = skills.find((s) => s.id === skillId);
      const hasActiveReviews =
        skill && ((skill.pending_reviews_count ?? 0) > 0 || (skill.flagged_reviews_count ?? 0) > 0);
      setSearchParams(
        (prev) => {
          if (isToggleOff) {
            prev.delete('skill');
          } else {
            prev.set('skill', skillId);
          }
          prev.delete('file');
          if (hasActiveReviews && !isToggleOff) {
            prev.set('tab', 'reviews');
          } else {
            prev.delete('tab');
          }
          return prev;
        },
        { replace: true }
      );
    },
    [selectedSkillId, setSelectedSkillId, setSearchParams, skills]
  );

  const handleSelectSkillReviews = useCallback(
    (e: React.MouseEvent, skillId: string) => {
      e.stopPropagation();
      setSelectedSkillId(skillId);
      setSearchParams(
        (prev) => {
          prev.set('skill', skillId);
          prev.set('tab', 'reviews');
          prev.delete('file');
          return prev;
        },
        { replace: true }
      );
    },
    [setSelectedSkillId, setSearchParams]
  );

  const handleSelectFile = useCallback(
    (filePath: string) => {
      setSelectedFilePath(filePath);
      setSearchParams(
        (prev) => {
          prev.set('file', filePath);
          prev.set('tab', 'viewer');
          return prev;
        },
        { replace: true }
      );
    },
    [setSelectedFilePath, setSearchParams]
  );

  const handleBack = useCallback(() => {
    setSelectedSkillId(null);
    setSearchParams(
      (prev) => {
        prev.delete('skill');
        prev.delete('file');
        prev.delete('tab');
        return prev;
      },
      { replace: true }
    );
  }, [setSelectedSkillId, setSearchParams]);

  const handleImported = useCallback(
    async (skillId: string) => {
      // Refresh skills list
      const [result] = await runSafe(backendApi.getSkills(), 'refreshSkills', {
        action: 'refreshing skills after import',
      });
      if (result) {
        setSkills(result.skills || []);
      }
      // Navigate to the imported skill's Reviews tab — imports always create reviews
      setSelectedSkillId(skillId);
      setSearchParams(
        (prev) => {
          prev.set('skill', skillId);
          prev.set('tab', 'reviews');
          prev.delete('file');
          return prev;
        },
        { replace: true }
      );
    },
    [runSafe, setSkills, setSelectedSkillId, setSearchParams]
  );

  const handleDeleteClick = useCallback((e: React.MouseEvent, skill: Skill) => {
    e.stopPropagation();
    setDeleteConfirm({ isOpen: true, skill });
  }, []);

  const handleConfirmDelete = useCallback(async () => {
    const skill = deleteConfirm.skill;
    if (!skill) return;

    await runSafe(backendApi.deleteSkill(skill.id), 'deleteSkill', {
      action: 'deleting skill',
      entityId: skill.id,
    });

    setSkills(skills.filter((s) => s.id !== skill.id));
    setDeleteConfirm({ isOpen: false, skill: null });
  }, [deleteConfirm.skill, runSafe, skills, setSkills]);

  const isExtractionEligible = selectedSkill?.extraction_eligible ?? false;

  const totalPending = skills.reduce((sum, s) => sum + (s.pending_reviews_count ?? 0), 0);
  const totalFlagged = skills.reduce((sum, s) => sum + (s.flagged_reviews_count ?? 0), 0);
  const skillsWithFlagged = skills.filter((s) => (s.flagged_reviews_count ?? 0) > 0);

  const tabs: { id: TabId; label: string; show: boolean }[] = [
    { id: 'viewer', label: 'Viewer', show: true },
    { id: 'onboarding', label: 'Onboarding', show: isExtractionEligible },
    { id: 'reviews', label: 'Reviews', show: true },
  ];

  // Landing: full-width card grid (no sidebar)
  if (!selectedSkillId) {
    return (
      <div className="py-6 px-4 sm:px-6 md:px-8">
        <div className="mb-6 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-gray-100">Skills</h1>
            <p className="mt-1 text-sm text-gray-500">
              Select a skill to browse its files, onboard knowledge, and run extractions
            </p>
          </div>
          <button
            onClick={() => setShowImportModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-md text-white bg-primary hover:bg-primary/90 transition-colors"
          >
            <ArrowUpTrayIcon className="w-4 h-4" />
            Import Skill
          </button>
        </div>

        {/* Cross-skill review summary */}
        {(totalPending > 0 || totalFlagged > 0) && (
          <div
            className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3"
            data-testid="review-summary-banner"
          >
            <div className="flex items-center gap-4 text-sm">
              {totalPending > 0 && (
                <span className="inline-flex items-center gap-1.5 text-yellow-400">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-yellow-400" />
                  </span>
                  {totalPending} review{totalPending !== 1 ? 's' : ''} processing
                </span>
              )}
              {totalFlagged > 0 && (
                <span className="inline-flex items-center gap-1.5 text-amber-400">
                  <ExclamationTriangleIcon className="w-4 h-4" />
                  {totalFlagged} review{totalFlagged !== 1 ? 's' : ''} flagged across{' '}
                  {skillsWithFlagged.length} skill{skillsWithFlagged.length !== 1 ? 's' : ''}
                  <span className="text-gray-500 font-normal">
                    — flagged reviews did not pass content gates and need manual review
                  </span>
                </span>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {skills.map((skill) => (
            <button
              key={skill.id}
              onClick={() => handleSelectSkill(skill.id)}
              className="text-left p-4 rounded-lg border border-gray-700 bg-dark-800 hover:border-primary hover:bg-dark-700 transition-colors group"
            >
              <div className="flex items-start gap-3">
                <div className="shrink-0 mt-0.5 w-8 h-8 rounded-md bg-primary/10 flex items-center justify-center group-hover:bg-primary/20 transition-colors">
                  <BookOpenIcon className="w-4 h-4 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 text-sm font-medium text-gray-100 group-hover:text-white">
                    {skill.name}
                    {skill.extraction_eligible && (
                      <PencilSquareIcon
                        className="w-3.5 h-3.5 text-green-400 shrink-0"
                        aria-label="Editable"
                        data-testid="editable-icon"
                      />
                    )}
                    <span
                      role="button"
                      tabIndex={0}
                      onClick={(e) => handleDeleteClick(e, skill)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleDeleteClick(e as unknown as React.MouseEvent, skill);
                        }
                      }}
                      className="ml-auto opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition-all shrink-0"
                      aria-label={`Delete ${skill.name}`}
                    >
                      <TrashIcon className="w-3.5 h-3.5" />
                    </span>
                  </div>
                  {skill.description ? (
                    <div className="text-xs text-gray-500 mt-1 line-clamp-2 group-hover:text-gray-400">
                      {skill.description}
                    </div>
                  ) : (
                    <div className="text-xs text-gray-600 mt-1 italic">No description</div>
                  )}
                  {(skill.pending_reviews_count > 0 || skill.flagged_reviews_count > 0) && (
                    <div
                      role="link"
                      tabIndex={0}
                      className="flex items-center gap-3 mt-2 hover:underline cursor-pointer"
                      onClick={(e) => handleSelectSkillReviews(e, skill.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleSelectSkillReviews(e as unknown as React.MouseEvent, skill.id);
                        }
                      }}
                      data-testid="review-badges"
                    >
                      {skill.pending_reviews_count > 0 && (
                        <span
                          className="inline-flex items-center gap-1.5 text-xs text-yellow-400"
                          data-testid="pending-reviews-indicator"
                        >
                          <span className="relative flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75" />
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-yellow-400" />
                          </span>
                          {skill.pending_reviews_count} processing
                        </span>
                      )}
                      {skill.flagged_reviews_count > 0 && (
                        <span
                          className="inline-flex items-center gap-1 text-xs text-amber-400"
                          data-testid="flagged-reviews-indicator"
                        >
                          <ExclamationTriangleIcon className="w-3.5 h-3.5" />
                          {skill.flagged_reviews_count} flagged
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>

        <SkillImportModal
          isOpen={showImportModal}
          onClose={() => setShowImportModal(false)}
          onImported={(skillId) => void handleImported(skillId)}
        />

        <ConfirmDialog
          isOpen={deleteConfirm.isOpen}
          onClose={() => setDeleteConfirm({ isOpen: false, skill: null })}
          onConfirm={() => void handleConfirmDelete()}
          title="Delete Skill?"
          message={`Are you sure you want to delete "${deleteConfirm.skill?.name}"? This action cannot be undone.`}
          confirmLabel="Delete"
          cancelLabel="Cancel"
          variant="warning"
        />
      </div>
    );
  }

  // Drill-down: breadcrumb + sidebar + detail panel
  return (
    <div className="flex flex-col h-full">
      {/* Breadcrumb */}
      <div className="px-4 sm:px-6 md:px-8 pt-4 pb-3">
        <div className="flex items-center gap-2">
          <button
            onClick={handleBack}
            className="text-gray-400 hover:text-gray-200 transition-colors"
            aria-label="Back to Skills"
          >
            <ArrowLeftIcon className="h-4 w-4" />
          </button>
          <button
            onClick={handleBack}
            className="text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            Skills
          </button>
          <span className="text-sm text-gray-600">/</span>
          <span className="text-sm text-gray-200">{selectedSkill?.name}</span>
        </div>
      </div>

      {/* Sidebar + Detail */}
      <div className="flex flex-1 min-h-0">
        {/* Skills Sidebar */}
        <div className="w-72 border-r border-gray-700/30 shrink-0 overflow-y-auto">
          <SkillsSidebar
            skills={skills}
            selectedSkillId={selectedSkillId}
            selectedFilePath={selectedFilePath}
            skillTree={skillTree}
            onSelectSkill={handleSelectSkill}
            onSelectFile={handleSelectFile}
          />
        </div>

        {/* Detail Panel */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Skill Header */}
          <div className="px-6 pt-5 pb-4">
            <div className="flex items-center gap-2.5">
              <span className="text-xs font-medium uppercase tracking-wider text-primary">
                Selected Skill
              </span>
              <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
            </div>
            <h2 className="text-lg font-semibold text-white mt-1">{selectedSkill?.name}</h2>
            {selectedSkill?.description && (
              <p className="text-sm text-gray-400 mt-1">{selectedSkill.description}</p>
            )}
          </div>

          {/* Tabs */}
          <div className="border-b border-gray-700/30 px-6">
            <div className="flex space-x-6">
              {tabs
                .filter((t) => t.show)
                .map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                      activeTab === tab.id
                        ? 'border-primary text-white'
                        : 'border-transparent text-gray-400 hover:text-gray-200'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
            </div>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-6">
            {activeTab === 'viewer' && (
              <SkillFileViewer skillId={selectedSkillId} filePath={selectedFilePath} />
            )}
            {activeTab === 'onboarding' && (
              <KnowledgeOnboarding skillId={selectedSkillId} onSwitchTab={setActiveTab} />
            )}
            {activeTab === 'reviews' && <ContentReviewList skillId={selectedSkillId} />}
          </div>
        </div>
      </div>
    </div>
  );
};
