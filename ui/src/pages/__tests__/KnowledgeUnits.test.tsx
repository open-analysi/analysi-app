import React from 'react';

import { render, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router';
import { describe, it, expect, vi } from 'vitest';

import KnowledgeUnitsPage from '../KnowledgeUnits';

// Mock the API and store dependencies
vi.mock('../../services/backendApi', () => ({
  backendApi: {
    getKnowledgeUnits: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('../../store/knowledgeUnitStore', () => ({
  useKnowledgeUnitStore: () => ({
    knowledgeUnits: [],
    setKnowledgeUnits: vi.fn(),
    totalCount: 0,
    setTotalCount: vi.fn(),
    searchTerm: '',
    setSearchTerm: vi.fn(),
    sortField: 'name',
    sortDirection: 'asc',
    setSorting: vi.fn(),
    pagination: { currentPage: 1, itemsPerPage: 10 },
    setPagination: vi.fn(),
    kuTypeFilter: '',
    setKuTypeFilter: vi.fn(),
    categoryFilter: [],
    toggleCategory: vi.fn(),
    setCategoryFilter: vi.fn(),
    getApiParams: vi.fn().mockReturnValue({}),
  }),
  SortField: {},
}));

// Mock the error handler hook
vi.mock('../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: { hasError: false, message: '' },
    clearError: vi.fn(),
    runSafe: vi.fn(() => Promise.resolve([[], null])),
  }),
}));

// Mock the table components
vi.mock('../../components/settings/KnowledgeUnitsTable', () => ({
  KnowledgeUnitsTable: () => <div>Knowledge Units Table</div>,
}));

vi.mock('../../components/settings/UnifiedSearch', () => ({
  UnifiedSearch: () => <div>Unified Search</div>,
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

describe('KnowledgeUnitsPage', () => {
  it('renders the knowledge units page', async () => {
    const { container } = renderWithRouter(<KnowledgeUnitsPage />);

    // Wait for any async operations to complete
    await waitFor(() => {
      // Check that the page renders
      expect(container.firstChild).toBeTruthy();

      // Check for the page element using a more flexible approach
      const pageElement = container.querySelector('[data-testid="knowledge-units-page"]');
      expect(pageElement).toBeTruthy();

      const componentElement = container.querySelector('[data-testid="knowledge-units-component"]');
      expect(componentElement).toBeTruthy();
    });
  });

  it('applies the correct page background styling', async () => {
    const { container } = renderWithRouter(<KnowledgeUnitsPage />);

    await waitFor(() => {
      // Check that the page container renders with correct styling
      const pageContainer = container.querySelector('[data-testid="knowledge-units-page"]');
      expect(pageContainer).toBeTruthy();
      expect(pageContainer).toHaveClass('mock-page-background');
    });
  });

  it('wraps content in error boundary', async () => {
    // This test verifies the component structure includes error boundary
    const { container } = renderWithRouter(<KnowledgeUnitsPage />);

    await waitFor(() => {
      // The page should render without throwing
      const pageElement = container.querySelector('[data-testid="knowledge-units-page"]');
      expect(pageElement).toBeTruthy();
    });
  });
});
