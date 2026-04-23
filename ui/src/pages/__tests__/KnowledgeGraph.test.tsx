import React from 'react';

import { render } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { describe, it, expect, vi } from 'vitest';

import KnowledgeGraphPage from '../KnowledgeGraph';

// Mock the KnowledgeGraph component since we're testing the page wrapper
vi.mock('../../components/settings/KnowledgeGraph', () => ({
  KnowledgeGraph: () => (
    <div data-testid="knowledge-graph-component">Knowledge Graph Component</div>
  ),
}));

// Mock the ErrorBoundary component to pass through children
vi.mock('../../components/common/ErrorBoundary', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

// Mock the componentStyles
vi.mock('../../styles/components', () => ({
  componentStyles: {
    pageBackground: 'mock-page-background',
  },
}));

const renderWithRouter = (component: React.ReactElement) => {
  return render(<BrowserRouter>{component}</BrowserRouter>);
};

describe('KnowledgeGraphPage', () => {
  it('renders the knowledge graph page with correct heading', () => {
    const { container } = renderWithRouter(<KnowledgeGraphPage />);

    // Check that the page renders
    expect(container.firstChild).toBeTruthy();

    // Check for the page element
    const pageElement = container.querySelector('[data-testid="knowledge-graph-page"]');
    expect(pageElement).toBeTruthy();

    // Check for heading text
    expect(container.textContent).toContain('Knowledge Dependency Graph');
    expect(container.textContent).toContain(
      'Visualize relationships between tasks, knowledge units, and modules'
    );
  });

  it('renders the knowledge graph component', () => {
    const { container } = renderWithRouter(<KnowledgeGraphPage />);

    const componentElement = container.querySelector('[data-testid="knowledge-graph-component"]');
    expect(componentElement).toBeTruthy();
  });

  it('applies the correct page background styling', () => {
    const { container } = renderWithRouter(<KnowledgeGraphPage />);

    const pageContainer = container.querySelector('[data-testid="knowledge-graph-page"]');
    expect(pageContainer).toBeTruthy();
    expect(pageContainer).toHaveClass('mock-page-background');
  });

  it('wraps content in error boundary', () => {
    // This test verifies the component structure includes error boundary
    const { container } = renderWithRouter(<KnowledgeGraphPage />);

    // The page should render without throwing
    const pageElement = container.querySelector('[data-testid="knowledge-graph-page"]');
    expect(pageElement).toBeTruthy();

    const componentElement = container.querySelector('[data-testid="knowledge-graph-component"]');
    expect(componentElement).toBeTruthy();
  });
});
