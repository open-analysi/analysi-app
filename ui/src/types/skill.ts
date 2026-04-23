// Skill — re-exported from generated types (backed by SkillResponse schema)
export type { Skill } from './api';

export interface SkillFile {
  path: string;
  document_id: string;
  staged: boolean;
}

export interface SkillTree {
  skill_id: string;
  files: SkillFile[];
  total: number;
}

// SkillFileContent — re-exported from generated types
export type { SkillFileContent } from './api';

export interface StagedDocument {
  document_id: string;
  path: string;
  edge_id: string;
}

// ContentReview — re-exported from generated types (backed by ContentReviewResponse schema)
export type {
  ContentReview,
  SkillImportResponse,
  SkillDeleteCheck,
  ContentGateResult,
} from './api';

export interface SkillsResponse {
  skills: import('./api').Skill[];
  total: number;
}

export interface ContentReviewsResponse {
  content_reviews: import('./api').ContentReview[];
  total: number;
}

export interface SkillQueryParams {
  search?: string;
  status?: string;
  limit?: number;
  offset?: number;
}
