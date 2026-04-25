import { useState, useEffect } from 'react';

import { loadArtifactContent, type ArtifactContent, type ArtifactViewMode } from '../artifactUtils';

// Constants
const ORIGINAL_ALERT_CATEGORY = 'original-alert';

export const useArtifactContent = (
  alertId: string,
  category: string,
  subcategory?: string,
  viewMode: ArtifactViewMode = 'original',
  provider?: string
) => {
  const [content, setContent] = useState<ArtifactContent>();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>();

  // Load content when dependencies change
  useEffect(() => {
    let isMounted = true;

    const loadContent = async () => {
      // Skip loading for the original-alert category as it's handled through props
      if (!category || category === ORIGINAL_ALERT_CATEGORY) return;

      setIsLoading(true);
      setError(undefined);

      try {
        const result = await loadArtifactContent({
          alertId,
          category,
          subcategory,
          viewMode,
          provider,
        });

        if (isMounted) {
          setContent(result);
        }
      } catch (error_) {
        console.error('Error loading artifact content:', error_);
        if (isMounted) {
          setError('Failed to load artifact content. Please try again.');
          setContent(undefined);
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    void loadContent();

    return () => {
      isMounted = false;
    };
  }, [alertId, category, subcategory, viewMode, provider]);

  return { content, isLoading, error };
};
