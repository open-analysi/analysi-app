import { create } from 'zustand';

import { ContentReview, Skill, SkillFile, SkillFileContent, StagedDocument } from '../types/skill';

export interface SkillStore {
  // Data
  skills: Skill[];
  setSkills: (skills: Skill[]) => void;

  // Selection
  selectedSkillId: string | null;
  setSelectedSkillId: (id: string | null) => void;
  selectedFilePath: string | null;
  setSelectedFilePath: (path: string | null) => void;

  // Tree for selected skill
  skillTree: SkillFile[];
  setSkillTree: (files: SkillFile[]) => void;

  // File content
  fileContent: SkillFileContent | null;
  setFileContent: (content: SkillFileContent | null) => void;

  // Staged documents
  stagedDocuments: StagedDocument[];
  setStagedDocuments: (docs: StagedDocument[]) => void;

  // Content reviews
  contentReviews: ContentReview[];
  setContentReviews: (reviews: ContentReview[]) => void;

  // Loading states
  loading: boolean;
  setLoading: (loading: boolean) => void;
  treeLoading: boolean;
  setTreeLoading: (loading: boolean) => void;
  fileLoading: boolean;
  setFileLoading: (loading: boolean) => void;
  reviewing: boolean;
  setReviewing: (reviewing: boolean) => void;

  // Reset
  reset: () => void;
}

const initialState = {
  skills: [],
  selectedSkillId: null,
  selectedFilePath: null,
  skillTree: [],
  fileContent: null,
  stagedDocuments: [],
  contentReviews: [],
  loading: false,
  treeLoading: false,
  fileLoading: false,
  reviewing: false,
};

export const useSkillStore = create<SkillStore>((set) => ({
  ...initialState,

  setSkills: (skills) => set({ skills }),
  setSelectedSkillId: (selectedSkillId) =>
    set({ selectedSkillId, skillTree: [], fileContent: null, selectedFilePath: null }),
  setSelectedFilePath: (selectedFilePath) => set({ selectedFilePath }),
  setSkillTree: (skillTree) => set({ skillTree }),
  setFileContent: (fileContent) => set({ fileContent }),
  setStagedDocuments: (stagedDocuments) => set({ stagedDocuments }),
  setContentReviews: (contentReviews) => set({ contentReviews }),
  setLoading: (loading) => set({ loading }),
  setTreeLoading: (treeLoading) => set({ treeLoading }),
  setFileLoading: (fileLoading) => set({ fileLoading }),
  setReviewing: (reviewing) => set({ reviewing }),
  reset: () => set(initialState),
}));
