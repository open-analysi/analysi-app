import React from 'react';

import {
  DocumentMagnifyingGlassIcon,
  DocumentMinusIcon,
  Square3Stack3DIcon,
} from '@heroicons/react/24/outline';

import {
  ArtifactCategory,
  ArtifactSubcategory,
  ANALYSIS_CATEGORY,
  ANALYSIS_STEP_BY_STEP_SUBCATEGORY,
  ANALYSIS_SUMMARY_SUBCATEGORY,
  ANALYSIS_GRAPH_SUBCATEGORY,
} from './artifactUtils';

interface ArtifactNavigationProps {
  categories: ArtifactCategory[];
  activeCategoryId: string;
  activeSubcategoryId?: string;
  onSelectCategory: (categoryId: string) => void;
  onSelectSubcategory: (subcategoryId: string) => void;
  hideAnalysis?: boolean;
}

const analysisSubcategories: ArtifactSubcategory[] = [
  {
    id: ANALYSIS_STEP_BY_STEP_SUBCATEGORY,
    name: 'Step-by-Step Details',
    description: 'Detailed step-by-step analysis of the alert investigation.',
  },
  {
    id: ANALYSIS_SUMMARY_SUBCATEGORY,
    name: 'Short Summary',
    description: 'Concise summary of the alert analysis and findings.',
  },
  {
    id: ANALYSIS_GRAPH_SUBCATEGORY,
    name: 'Graph',
    description: 'Visual representation of the alert analysis and relationships.',
  },
];

type AnalysisSubcategoryId =
  | typeof ANALYSIS_STEP_BY_STEP_SUBCATEGORY
  | typeof ANALYSIS_SUMMARY_SUBCATEGORY
  | typeof ANALYSIS_GRAPH_SUBCATEGORY;

const ArtifactNavigation: React.FC<ArtifactNavigationProps> = ({
  categories,
  activeCategoryId,
  activeSubcategoryId,
  onSelectCategory,
  onSelectSubcategory,
  hideAnalysis = false,
}) => {
  const handleAnalysisClick = (analysisType: AnalysisSubcategoryId) => {
    onSelectCategory(ANALYSIS_CATEGORY);
    onSelectSubcategory(analysisType);
  };

  return (
    <div className="space-y-6">
      {/* Alert Analysis Details Section */}
      <div className="bg-dark-800 rounded-md p-4">
        <h3 className="text-lg font-medium text-gray-100 mb-4">Alert Analysis Details</h3>
        <ul className="space-y-1">
          {analysisSubcategories.map((subcategory) => (
            <li key={subcategory.id}>
              <button
                className={`w-full text-left px-3 py-2 rounded-md flex items-center ${
                  activeCategoryId === ANALYSIS_CATEGORY && activeSubcategoryId === subcategory.id
                    ? 'bg-primary text-white'
                    : 'text-gray-300 hover:bg-dark-700'
                }`}
                onClick={() => handleAnalysisClick(subcategory.id as AnalysisSubcategoryId)}
              >
                <span className="mr-2">
                  {subcategory.id === ANALYSIS_STEP_BY_STEP_SUBCATEGORY && (
                    <DocumentMagnifyingGlassIcon className="w-6 h-6" />
                  )}
                  {subcategory.id === ANALYSIS_SUMMARY_SUBCATEGORY && (
                    <DocumentMinusIcon className="w-6 h-6" />
                  )}
                  {subcategory.id === ANALYSIS_GRAPH_SUBCATEGORY && (
                    <Square3Stack3DIcon className="w-6 h-6" />
                  )}
                </span>
                <span>{subcategory.name}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* Artifact Categories Section */}
      <div className="bg-dark-800 rounded-md p-4">
        <h3 className="text-lg font-medium text-gray-100 mb-4">Artifact Categories</h3>

        <ul className="space-y-1">
          {categories
            .filter((category) => !hideAnalysis || category.id !== ANALYSIS_CATEGORY)
            .map((category) => (
              <li key={category.id}>
                <button
                  className={`w-full text-left px-3 py-2 rounded-md flex items-center ${
                    category.id === activeCategoryId
                      ? 'bg-primary text-white'
                      : 'text-gray-300 hover:bg-dark-700'
                  }`}
                  onClick={() => onSelectCategory(category.id)}
                >
                  <span className="mr-2">{category.icon}</span>
                  <span>{category.name}</span>
                </button>

                {/* Display subcategories if this category is active and has subcategories */}
                {category.id === activeCategoryId && category.hasSubcategories && (
                  <ul className="ml-6 mt-2 space-y-1">
                    {category.subcategories?.map((subcategory: ArtifactSubcategory) => (
                      <li key={subcategory.id}>
                        <button
                          className={`w-full text-left px-3 py-1.5 rounded-md ${
                            subcategory.id === activeSubcategoryId
                              ? 'bg-primary/80 text-white'
                              : 'text-gray-400 hover:bg-dark-700'
                          }`}
                          onClick={() => onSelectSubcategory(subcategory.id)}
                        >
                          {subcategory.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
        </ul>
      </div>
    </div>
  );
};

export default ArtifactNavigation;
