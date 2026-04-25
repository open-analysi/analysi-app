import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

import CollectedArtifacts from '../CollectedArtifacts';

// Mock the useArtifactContent hook
vi.mock('../hooks/useArtifactContent', () => ({
  useArtifactContent: vi.fn(() => ({
    content: null,
    isLoading: false,
    error: undefined,
  })),
}));

// Mock react-markdown to avoid ESM issues in test environment
vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => <div data-testid="markdown">{children}</div>,
}));

// Constants
const ALERT_ID = 'alert-001';
const MAIN_HEADING = 'AI Powered Data Collection and Alert Analysis';
const NO_CONTENT_MESSAGE = 'No content available';

describe('CollectedArtifacts', () => {
  it('renders without crashing when no artifacts provided', () => {
    render(<CollectedArtifacts alertId={ALERT_ID} />);

    expect(screen.getByText(MAIN_HEADING)).toBeInTheDocument();
  });

  it('shows the navigation sidebar with category names', () => {
    render(<CollectedArtifacts alertId={ALERT_ID} />);

    // The ArtifactNavigation component renders analysis subcategories
    expect(screen.getByText('Step-by-Step Details')).toBeInTheDocument();
    expect(screen.getByText('Short Summary')).toBeInTheDocument();
    expect(screen.getByText('Graph')).toBeInTheDocument();

    // And artifact category names from artifactCategories
    expect(screen.getByText('Original Alert')).toBeInTheDocument();
    expect(screen.getByText('Threat Intelligence')).toBeInTheDocument();
  });

  it('displays "No content available" when no analysis data is provided', () => {
    render(<CollectedArtifacts alertId={ALERT_ID} />);

    // Default category is "analysis" with "graph" subcategory,
    // and without analysisData prop, AnalysisContentRenderer shows NoContentState
    expect(screen.getByText(NO_CONTENT_MESSAGE)).toBeInTheDocument();
  });
});
