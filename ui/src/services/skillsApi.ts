import {
  Skill,
  SkillsResponse,
  SkillTree,
  SkillFileContent,
  StagedDocument,
  ContentReview,
  ContentReviewsResponse,
  SkillQueryParams,
  SkillImportResponse,
  SkillDeleteCheck,
} from '../types/skill';

import {
  withApi,
  fetchOne,
  fetchList,
  mutateOne,
  apiDelete,
  backendApiClient,
  type SifnosEnvelope,
} from './apiClient';

// ==================== Skills ====================

export const getSkills = async (params?: SkillQueryParams): Promise<SkillsResponse> =>
  withApi('getSkills', 'fetching skills', () =>
    fetchList<'skills', Skill>('/skills', 'skills', { params })
  );

export const getSkill = async (skillId: string): Promise<Skill> =>
  withApi('getSkill', 'fetching skill', () => fetchOne<Skill>(`/skills/${skillId}`), {
    entityId: skillId,
    entityType: 'skill',
  });

export const getSkillTree = async (skillId: string): Promise<SkillTree> =>
  withApi(
    'getSkillTree',
    'fetching skill tree',
    () => fetchOne<SkillTree>(`/skills/${skillId}/tree`),
    { entityId: skillId, entityType: 'skill' }
  );

export const getSkillFile = async (skillId: string, filePath: string): Promise<SkillFileContent> =>
  withApi(
    'getSkillFile',
    'fetching skill file',
    async () => {
      const response = await backendApiClient.get<SifnosEnvelope<{ file: SkillFileContent }>>(
        `/skills/${skillId}/files/${filePath}`
      );
      return response.data.data.file;
    },
    { entityId: skillId, entityType: 'skill' }
  );

export const getStagedDocuments = async (skillId: string): Promise<StagedDocument[]> =>
  withApi(
    'getStagedDocuments',
    'fetching staged documents',
    async () => {
      const response = await backendApiClient.get<
        SifnosEnvelope<StagedDocument[] | { documents: StagedDocument[] }>
      >(`/skills/${skillId}/staged-documents`);
      const result = response.data.data;
      // Handle both possible shapes
      return Array.isArray(result) ? result : result.documents;
    },
    { entityId: skillId, entityType: 'skill' }
  );

export const stageDocument = async (
  skillId: string,
  body: { document_id: string; namespace_path: string }
): Promise<StagedDocument> =>
  withApi(
    'stageDocument',
    'staging document',
    () => mutateOne<StagedDocument>('post', `/skills/${skillId}/staged-documents`, body),
    { entityId: skillId, entityType: 'skill' }
  );

export const unstageDocument = async (skillId: string, documentId: string): Promise<void> =>
  withApi(
    'unstageDocument',
    'unstaging document',
    () => apiDelete(`/skills/${skillId}/staged-documents/${documentId}`),
    { entityId: skillId, entityType: 'skill' }
  );

// ==================== Content Reviews ====================

export const createContentReview = async (
  skillId: string,
  body: { document_id: string }
): Promise<ContentReview> =>
  withApi(
    'createContentReview',
    'creating content review',
    () => mutateOne<ContentReview>('post', `/skills/${skillId}/content-reviews`, body),
    { entityId: skillId, entityType: 'skill' }
  );

export const getContentReviews = async (
  skillId: string,
  params?: { limit?: number; offset?: number }
): Promise<ContentReviewsResponse> =>
  withApi(
    'getContentReviews',
    'fetching content reviews',
    () =>
      fetchList<'content_reviews', ContentReview>(
        `/skills/${skillId}/content-reviews`,
        'content_reviews',
        { params }
      ),
    { entityId: skillId, entityType: 'skill' }
  );

export const getContentReview = async (skillId: string, reviewId: string): Promise<ContentReview> =>
  withApi(
    'getContentReview',
    'fetching content review',
    () => fetchOne<ContentReview>(`/skills/${skillId}/content-reviews/${reviewId}`),
    { entityId: reviewId, entityType: 'content-review' }
  );

export const applyContentReview = async (
  skillId: string,
  reviewId: string,
  overrides?: Record<string, unknown>
): Promise<void> =>
  withApi(
    'applyContentReview',
    'applying content review',
    async () => {
      await backendApiClient.post(
        `/skills/${skillId}/content-reviews/${reviewId}/apply`,
        overrides
      );
    },
    { entityId: reviewId, entityType: 'content-review' }
  );

export const rejectContentReview = async (
  skillId: string,
  reviewId: string,
  body: { reason: string }
): Promise<void> =>
  withApi(
    'rejectContentReview',
    'rejecting content review',
    async () => {
      await backendApiClient.post(`/skills/${skillId}/content-reviews/${reviewId}/reject`, body);
    },
    { entityId: reviewId, entityType: 'content-review' }
  );

export const retryContentReview = async (
  skillId: string,
  reviewId: string
): Promise<ContentReview> =>
  withApi(
    'retryContentReview',
    'retrying content review',
    () => mutateOne<ContentReview>('post', `/skills/${skillId}/content-reviews/${reviewId}/retry`),
    { entityId: reviewId, entityType: 'content-review' }
  );

// ==================== Skill Management ====================

export const checkSkillDelete = async (skillId: string): Promise<SkillDeleteCheck> =>
  withApi(
    'checkSkillDelete',
    'checking skill delete',
    () => fetchOne<SkillDeleteCheck>(`/skills/${skillId}/check-delete`),
    { entityId: skillId, entityType: 'skill' }
  );

export const deleteSkill = async (skillId: string): Promise<void> =>
  withApi('deleteSkill', 'deleting skill', () => apiDelete(`/skills/${skillId}`), {
    entityId: skillId,
    entityType: 'skill',
  });

export const importSkill = async (file: File): Promise<SkillImportResponse> =>
  withApi('importSkill', 'importing skill', async () => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await backendApiClient.post<SifnosEnvelope<SkillImportResponse>>(
      '/skills/import',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return response.data.data;
  });
