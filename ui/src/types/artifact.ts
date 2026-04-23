/**
 * Artifact types for the Artifacts API
 */

// Artifact — re-exported from generated types (backed by ArtifactResponse schema)
export type { Artifact } from './api';

export interface ArtifactListResponse {
  artifacts: import('./api').Artifact[];
  total: number;
}

export interface ArtifactQueryParams {
  [key: string]: string | number | undefined;
  name?: string;
  artifact_type?: string;
  task_run_id?: string;
  workflow_run_id?: string;
  analysis_id?: string;
  limit?: number;
  offset?: number;
  sort?: string;
  order?: 'asc' | 'desc';
}
