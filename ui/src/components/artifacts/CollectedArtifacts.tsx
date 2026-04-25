import React, { useState, useEffect } from 'react';

import { DocumentTextIcon, DocumentChartBarIcon } from '@heroicons/react/24/outline';
import ReactMarkdown from 'react-markdown';

import ArtifactContentRenderer from './ArtifactContentRenderer';
import ArtifactNavigation from './ArtifactNavigation';
import {
  artifactCategories as allArtifactCategories, // Use this consistently or rename
  type ArtifactViewMode,
  type ArtifactCategory,
} from './artifactUtils';
import {
  ANALYSIS_CATEGORY,
  ANALYSIS_GRAPH_SUBCATEGORY,
  ANALYSIS_STEP_BY_STEP_SUBCATEGORY,
  ANALYSIS_SUMMARY_SUBCATEGORY,
  EDR_CATEGORY,
  ORIGINAL_ALERT_CATEGORY,
  THREAT_INTEL_CATEGORY,
} from './artifactUtils'; // Import the new constants
import { useArtifactContent } from './hooks/useArtifactContent';

// Define constants for repeated strings
const BUTTON_ACTIVE_CLASS = 'bg-primary text-white';
const BUTTON_INACTIVE_CLASS = 'bg-dark-700 text-gray-300 hover:bg-dark-600';
const ARROW_SEPARATOR = ' > ';
const NO_CONTENT_MESSAGE = 'No content available';

// Restore the interface definition
interface CollectedArtifactsProps {
  alertId: string;
  originalAlertData?: Record<string, unknown>;
  keyFieldsData?: Record<string, unknown>;
  analysisData?: {
    markdownAnalysis: string;
    summaryAnalysis: string;
    dotGraph: string; // This should contain the JSON string for Cytoscape
  };
}

// Helper function to get initial subcategory
const getInitialSubcategory = (category: ArtifactCategory | undefined): string | undefined => {
  if (!category?.hasSubcategories || !category?.subcategories?.length) return undefined;
  return category.subcategories[0].id;
};

// Helper function to handle category change - Fixed setActiveCategory type
const handleCategoryChange = (
  categoryId: string,
  categories: ArtifactCategory[],
  setActiveCategory: React.Dispatch<React.SetStateAction<string>>, // Changed from string | null
  setActiveSubcategory: React.Dispatch<React.SetStateAction<string | undefined>>,
  setActiveProvider: React.Dispatch<React.SetStateAction<string>>,
  _setViewMode: React.Dispatch<React.SetStateAction<ArtifactViewMode>> // Prefix unused parameter
) => {
  setActiveCategory(categoryId);

  const selectedCategory = categories.find((cat) => cat.id === categoryId);
  const initialSubcategory = getInitialSubcategory(selectedCategory);
  setActiveSubcategory(initialSubcategory);

  if (categoryId === THREAT_INTEL_CATEGORY) {
    setActiveProvider('virustotal');
  } else {
    setActiveProvider('');
  }
};

// Helper components (LoadingState, ErrorState, NoContentState remain the same)
const LoadingState = () => (
  <div className="flex items-center justify-center h-full">
    <div className="animate-pulse text-gray-400">Loading content...</div>
  </div>
);
const ErrorState = ({ message }: { message: string }) => (
  <div className="p-4 text-red-400 border border-red-700 bg-red-900/30 rounded-md">{message}</div>
);
const NoContentState = () => (
  <div className="flex items-center justify-center h-full">
    <div className="text-gray-400">{NO_CONTENT_MESSAGE}</div>
  </div>
);

// AnalysisContentRenderer with Cytoscape graph logic restored
const AnalysisContentRenderer: React.FC<{
  activeSubcategory?: string;
  analysisData?: CollectedArtifactsProps['analysisData'];
  graphError?: string;
}> = ({ activeSubcategory, analysisData, graphError }) => {
  if (!analysisData) {
    return <NoContentState />;
  }

  switch (activeSubcategory) {
    case ANALYSIS_STEP_BY_STEP_SUBCATEGORY: {
      return (
        <div className="prose prose-invert max-w-none">
          <ReactMarkdown>{analysisData.markdownAnalysis || ''}</ReactMarkdown>
        </div>
      );
    }
    case ANALYSIS_SUMMARY_SUBCATEGORY: {
      return (
        <div className="prose prose-invert max-w-none">
          <ReactMarkdown>{analysisData.summaryAnalysis || ''}</ReactMarkdown>
        </div>
      );
    }
    case ANALYSIS_GRAPH_SUBCATEGORY: {
      if (graphError) {
        return <ErrorState message={graphError} />;
      }
      // Graph visualization disabled — cytoscape not yet packaged for Docker
      return (
        <div className="relative h-full">
          <div className="flex items-center justify-center h-full text-gray-400">
            Graph visualization temporarily disabled for Docker deployment
          </div>
        </div>
      );
    }
    default: {
      return <NoContentState />;
    }
  }
};

// Render title for content area
const renderContentTitle = (
  isAnalysisCategory: boolean,
  activeSubcategory: string | undefined,
  isThreatIntelCategory: boolean,
  activeProvider: string,
  hasSubcategories: boolean | undefined,
  activeCategoryName: string | undefined,
  currentSubcategoryName: string | undefined
) => {
  if (isAnalysisCategory) {
    if (activeSubcategory === ANALYSIS_STEP_BY_STEP_SUBCATEGORY) return 'Step-by-Step Details';
    if (activeSubcategory === ANALYSIS_SUMMARY_SUBCATEGORY) return 'Short Summary';
    if (activeSubcategory === ANALYSIS_GRAPH_SUBCATEGORY) return 'Analysis Graph';
    return 'Alert Analysis';
  }

  let title = activeCategoryName || '';

  if (isThreatIntelCategory && activeProvider) {
    title += `${ARROW_SEPARATOR}VirusTotal`;
  } else if (
    activeSubcategory &&
    !isAnalysisCategory &&
    !isThreatIntelCategory &&
    hasSubcategories
  ) {
    title += `${ARROW_SEPARATOR}${currentSubcategoryName}`;
  }

  return title;
};

// Render category description
const renderCategoryDescription = (
  activeCategoryObj: ArtifactCategory | undefined,
  isAnalysisCategory: boolean,
  isThreatIntelCategory: boolean,
  activeProvider: string,
  isEdrCategory: boolean,
  activeSubcategory: string | undefined,
  currentSubcategoryName: string | undefined,
  subcategories: Array<{ id: string; description?: string }>
) => {
  if (!activeCategoryObj || isAnalysisCategory) return;

  if (isThreatIntelCategory && activeProvider) {
    return `${activeCategoryObj.description} - VirusTotal analysis and reputation data`;
  }

  if (isEdrCategory && activeSubcategory) {
    const subcategoryDesc =
      subcategories.find((s) => s.id === activeSubcategory)?.description || '';
    return `${activeCategoryObj.description} - ${currentSubcategoryName} description:&apos;${subcategoryDesc}`;
  }

  return activeCategoryObj.description;
};

// Original alert content handler
const getOriginalAlertContent = (
  isOriginalAlertCategory: boolean,
  viewMode: ArtifactViewMode,
  keyFieldsData?: Record<string, unknown>,
  originalAlertData?: Record<string, unknown>
) => {
  if (!isOriginalAlertCategory) return;

  const contentToShow = viewMode === 'summary' ? keyFieldsData : originalAlertData;
  if (!contentToShow) return;

  return {
    contentType: 'json' as const,
    category: ORIGINAL_ALERT_CATEGORY,
    data: contentToShow,
  };
};

// Main component for displaying collected artifacts
const CollectedArtifacts: React.FC<CollectedArtifactsProps> = ({
  alertId,
  originalAlertData,
  keyFieldsData,
  analysisData,
}) => {
  const [activeCategory, setActiveCategory] = useState<string>(ANALYSIS_CATEGORY);
  const [activeSubcategory, setActiveSubcategory] = useState<string | undefined>(
    ANALYSIS_GRAPH_SUBCATEGORY
  );
  const [activeProvider, setActiveProvider] = useState<string>('');
  const [viewMode, setViewMode] = useState<ArtifactViewMode>('original');
  const [localOriginalAlertView, setLocalOriginalAlertView] = useState<'original' | 'summary'>(
    viewMode
  );
  const [graphError, setGraphError] = useState<string | undefined>();

  // Use the imported categories consistently
  const artifactCategories = allArtifactCategories;
  const activeCategoryObj = artifactCategories.find(
    (cat: ArtifactCategory) => cat.id === activeCategory
  );
  const subcategories = activeCategoryObj?.subcategories || [];

  // Check category types
  const isThreatIntelCategory = activeCategory === THREAT_INTEL_CATEGORY;
  const isEdrCategory = activeCategory === EDR_CATEGORY;
  const isOriginalAlertCategory = activeCategory === ORIGINAL_ALERT_CATEGORY;
  const isAnalysisCategory = activeCategory === ANALYSIS_CATEGORY;
  const effectiveViewMode = isOriginalAlertCategory ? localOriginalAlertView : viewMode;

  // Load content with custom hook
  const {
    content: hookContent,
    isLoading: isLoadingContent,
    error: errorMessage,
  } = useArtifactContent(
    alertId,
    activeCategory,
    activeSubcategory,
    viewMode,
    isThreatIntelCategory ? activeProvider : undefined
  );

  // Sync view modes
  useEffect(() => {
    if (isOriginalAlertCategory) {
      if (viewMode !== localOriginalAlertView) {
        setViewMode(localOriginalAlertView);
      }
    } else if (localOriginalAlertView !== viewMode) {
      setLocalOriginalAlertView(viewMode);
    }
  }, [isOriginalAlertCategory, localOriginalAlertView, viewMode]);

  // Prepare graph data
  useEffect(() => {
    if (isAnalysisCategory && activeSubcategory === ANALYSIS_GRAPH_SUBCATEGORY) {
      try {
        // eslint-disable-next-line no-console
        console.log('Checking graph data:', analysisData?.dotGraph);
        if (!analysisData?.dotGraph) {
          throw new Error('No graph data available');
        }
        JSON.parse(analysisData.dotGraph);
        setGraphError(undefined);
      } catch (error) {
        console.error('Error parsing graph data:', error);
        setGraphError(`Failed to parse graph data: ${(error as Error).message}`);
      }
    }
  }, [isAnalysisCategory, activeSubcategory, analysisData?.dotGraph]);

  // Event handlers
  const onCategoryChange = (categoryId: string) => {
    if (categoryId === ORIGINAL_ALERT_CATEGORY) {
      setLocalOriginalAlertView(viewMode);
    }
    // Reset content state when changing categories
    setActiveCategory(categoryId);
    setActiveSubcategory(undefined);
    setActiveProvider('');
    handleCategoryChange(
      categoryId,
      artifactCategories,
      setActiveCategory,
      setActiveSubcategory,
      setActiveProvider,
      setViewMode
    );
  };

  const onSubcategoryChange = (subcategoryId: string) => {
    setActiveSubcategory(subcategoryId);
  };

  const onProviderChange = (providerId: string) => {
    setActiveProvider(providerId);
    setActiveSubcategory(providerId);
  };

  const onViewModeChange = (mode: ArtifactViewMode) => {
    setViewMode(mode);
    if (isOriginalAlertCategory) {
      setLocalOriginalAlertView(mode);
    }
  };

  // Render provider tabs for Threat Intel
  const renderProviderTabs = () => {
    if (!isThreatIntelCategory) return;

    return (
      <div className="mb-4 border-b border-dark-700">
        <ul className="flex flex-wrap -mb-px text-sm font-medium text-center">
          <li className="mr-2">
            <button
              onClick={() => onProviderChange('virustotal')}
              className={`inline-block p-4 border-b-2 rounded-t-lg ${
                activeProvider === 'virustotal'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-gray-400 hover:text-gray-300 hover:border-gray-300'
              }`}
            >
              VirusTotal
            </button>
          </li>
        </ul>
      </div>
    );
  };

  // Render subcategory tabs for EDR Data only
  const renderSubcategoryTabs = () => {
    if (!isEdrCategory || subcategories.length === 0) return;

    return (
      <div className="mb-4 border-b border-dark-700">
        <ul className="flex flex-wrap -mb-px text-sm font-medium text-center">
          {subcategories.map((subcategory: { id: string; name: string }) => (
            <li className="mr-2" key={subcategory.id}>
              <button
                onClick={() => onSubcategoryChange(subcategory.id)}
                className={`inline-block p-4 border-b-2 rounded-t-lg ${
                  activeSubcategory === subcategory.id
                    ? BUTTON_ACTIVE_CLASS
                    : 'border-transparent text-gray-400 hover:text-gray-300 hover:border-gray-300'
                }`}
              >
                {subcategory.name}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  // Combined render logic for content area
  const renderContentArea = () => {
    if (isLoadingContent) return <LoadingState />;
    if (errorMessage) return <ErrorState message={errorMessage} />;

    if (isAnalysisCategory) {
      return (
        <AnalysisContentRenderer
          activeSubcategory={activeSubcategory}
          analysisData={analysisData}
          graphError={graphError}
        />
      );
    }

    // Handle original alert content
    if (isOriginalAlertCategory) {
      const originalContent = getOriginalAlertContent(
        isOriginalAlertCategory,
        viewMode,
        keyFieldsData,
        originalAlertData
      );

      if (originalContent) {
        return (
          <ArtifactContentRenderer
            content={originalContent}
            viewMode={viewMode}
            isLoading={false}
            error={undefined}
            isEdrData={false}
          />
        );
      }
      return <NoContentState />;
    }

    // For all other categories, check if we have content
    if (!hookContent) {
      return <NoContentState />;
    }

    return (
      <ArtifactContentRenderer
        content={hookContent}
        viewMode={viewMode}
        isLoading={isLoadingContent}
        error={undefined}
        isEdrData={isEdrCategory}
      />
    );
  };

  // Get current subcategory name for display
  const currentSubcategoryName = subcategories.find(
    (s: { id: string; name: string }) => s.id === activeSubcategory
  )?.name;

  // Get title for content area
  const contentTitle = renderContentTitle(
    isAnalysisCategory,
    activeSubcategory,
    isThreatIntelCategory,
    activeProvider,
    activeCategoryObj?.hasSubcategories,
    activeCategoryObj?.name,
    currentSubcategoryName
  );

  // Get category description
  const categoryDescription = renderCategoryDescription(
    activeCategoryObj,
    isAnalysisCategory,
    isThreatIntelCategory,
    activeProvider,
    isEdrCategory,
    activeSubcategory,
    currentSubcategoryName,
    subcategories
  );

  return (
    <div className="bg-dark-900 rounded-md p-6 mb-6 border border-dark-700">
      <h2 className="text-2xl font-bold text-gray-100 mb-6 flex items-center">
        <span className="border-b-2 border-primary pb-1">
          AI Powered Data Collection and Alert Analysis
        </span>
      </h2>

      <div className="flex flex-col md:flex-row space-y-6 md:space-y-0 md:space-x-6">
        {/* Left sidebar */}
        <div className="w-full md:w-1/4">
          {/* Artifact Categories Section */}
          <div>
            <ArtifactNavigation
              categories={artifactCategories}
              activeCategoryId={activeCategory}
              activeSubcategoryId={activeSubcategory}
              onSelectCategory={onCategoryChange}
              onSelectSubcategory={onSubcategoryChange}
            />
          </div>
        </div>

        {/* Right content area */}
        <div className="w-full md:w-3/4">
          <div className="flex justify-between items-center mb-4">
            <div className="text-xl font-semibold text-gray-100">{contentTitle}</div>

            {/* Show view mode toggles for non-analysis categories */}
            {!isAnalysisCategory && (
              <div className="flex items-center space-x-2">
                <button
                  className={`px-3 py-1 rounded-l-md flex items-center ${
                    effectiveViewMode === 'original' ? BUTTON_ACTIVE_CLASS : BUTTON_INACTIVE_CLASS
                  }`}
                  onClick={() => onViewModeChange('original')}
                >
                  <DocumentTextIcon className="w-5 h-5 mr-1" />
                  <span>Original</span>
                </button>
                <button
                  className={`px-3 py-1 rounded-r-md flex items-center ${
                    effectiveViewMode === 'summary' ? BUTTON_ACTIVE_CLASS : BUTTON_INACTIVE_CLASS
                  }`}
                  onClick={() => onViewModeChange('summary')}
                >
                  <DocumentChartBarIcon className="w-5 h-5 mr-1" />
                  <span>Summary</span>
                </button>
              </div>
            )}
          </div>

          {renderProviderTabs()}
          {renderSubcategoryTabs()}

          <div className="bg-dark-800 rounded-md p-4 border border-dark-700 h-[800px] relative">
            {renderContentArea()}
          </div>

          {/* Display category description */}
          {categoryDescription && (
            <div className="mt-4 text-sm text-gray-400">{categoryDescription}</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CollectedArtifacts;
