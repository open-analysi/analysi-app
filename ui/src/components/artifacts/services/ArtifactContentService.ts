import { loadArtifactContent, type ArtifactContent, type ArtifactViewMode } from '../artifactUtils';

interface ArtifactContentConfig {
  alertId: string;
  category: string;
  subcategory?: string;
  viewMode?: ArtifactViewMode;
  provider?: string;
}

export class ArtifactContentService {
  private config: ArtifactContentConfig;

  constructor(config: ArtifactContentConfig) {
    this.config = {
      ...config,
      viewMode: config.viewMode || 'original',
    };
  }

  async loadContent(): Promise<ArtifactContent | undefined> {
    if (!this.config.category) return undefined;

    try {
      return await loadArtifactContent(this.config);
    } catch (error) {
      console.error('Error loading artifact content:', error);
      throw error;
    }
  }
}
