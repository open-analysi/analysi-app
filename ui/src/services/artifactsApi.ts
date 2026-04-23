import { Artifact, ArtifactListResponse, ArtifactQueryParams } from '../types/artifact';

import { withApi, fetchOne, fetchList, backendApiClient, type SifnosEnvelope } from './apiClient';

// ==================== Artifacts API ====================

export const getArtifacts = async (
  params: ArtifactQueryParams = {}
): Promise<ArtifactListResponse> =>
  withApi('getArtifacts', 'fetching artifacts', () =>
    fetchList<'artifacts', Artifact>('/artifacts', 'artifacts', { params })
  );

export const getArtifact = async (artifactId: string): Promise<Artifact> =>
  withApi('getArtifact', 'fetching artifact', () => fetchOne<Artifact>(`/artifacts/${artifactId}`));

export const getArtifactDownloadUrl = async (artifactId: string): Promise<string> =>
  withApi('getArtifactDownloadUrl', 'getting artifact download URL', async () => {
    const response = await backendApiClient.get<SifnosEnvelope<{ download_url: string }>>(
      `/artifacts/${artifactId}/download`
    );
    return response.data.data.download_url;
  });

// ==================== Task Run Enrichment ====================

export const getTaskRunEnrichment = async (taskRunId: string): Promise<Record<string, unknown>> =>
  withApi('getTaskRunEnrichment', 'fetching task run enrichment', () =>
    fetchOne<Record<string, unknown>>(`/task-runs/${taskRunId}/enrichment`)
  );
