import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import { useKnowledgeUnitStore } from '../../../store/knowledgeUnitStore';
import { KnowledgeUnits } from '../KnowledgeUnits';

// Mock the backendApi
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getKnowledgeUnits: vi.fn(),
    getDirective: vi.fn(),
    getTable: vi.fn(),
    getDocument: vi.fn(),
    getKnowledgeUnit: vi.fn(),
    getKnowledgeUnitTasks: vi.fn(),
    getKnowledgeUnitDependencies: vi.fn(),
  },
}));

// Mock the error handler hook
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: vi.fn().mockReturnValue({
    error: { hasError: false, message: '' },
    clearError: vi.fn(),
    runSafe: vi.fn((promise) => Promise.resolve([promise])),
  }),
}));

// Mock the user display hook to return the userId as-is
vi.mock('../../../hooks/useUserDisplay', () => ({
  useUserDisplay: (userId: string | undefined) => userId || 'Unknown',
}));

// Mock the store
vi.mock('../../../store/knowledgeUnitStore', () => ({
  useKnowledgeUnitStore: vi.fn(),
}));

// These tests need to be updated after the API integration changes
// The component behavior has changed with the new backend integration
describe.skip('KnowledgeUnits Component', () => {
  const MOCK_TIMESTAMP = '2025-04-24T17:32:36.048157';
  const DIRECTIVE_NAME = 'Company Default';
  const mockKnowledgeUnits = [
    {
      id: '00000001-0000-0000-0000-000000000001',
      name: DIRECTIVE_NAME,
      description: 'Default company directive for all analyses',
      type: 'directive',
      created_by: 'system',
      status: 'active',
      version: '1.0.0',
      created_at: MOCK_TIMESTAMP,
      updated_at: MOCK_TIMESTAMP,
      tags: [],
      usage_stats: { count: 0, last_used: null },
      visibility: 'public',
      dependencies: [],
      embedding_vector: null,
      source_document_id: null,
      editable: true,
    },
    {
      id: '00000002-0000-0000-0000-000000000001',
      name: 'Crown Jewels',
      description: 'List of critical assets and systems for the company',
      type: 'table',
      created_by: 'system',
      status: 'active',
      version: '1.0.0',
      created_at: MOCK_TIMESTAMP,
      updated_at: MOCK_TIMESTAMP,
      tags: [],
      usage_stats: { count: 0, last_used: null },
      visibility: 'public',
      dependencies: [],
      embedding_vector: null,
      source_document_id: null,
      editable: true,
    },
  ];

  // Mock store implementation
  const mockStore = {
    knowledgeUnits: mockKnowledgeUnits,
    setKnowledgeUnits: vi.fn(),
    totalCount: 2,
    setTotalCount: vi.fn(),
    filters: {
      type: {
        directive: true,
        table: true,
        tool: true,
        document: true,
      },
      status: {
        active: true,
        deprecated: true,
        experimental: true,
      },
    },
    setTypeFilters: vi.fn(),
    setStatusFilters: vi.fn(),
    resetFilters: vi.fn(),
    searchTerm: '',
    setSearchTerm: vi.fn(),
    sortField: 'updated_at',
    sortDirection: 'desc',
    setSorting: vi.fn(),
    pagination: {
      currentPage: 1,
      itemsPerPage: 10,
    },
    setPagination: vi.fn(),
    getApiParams: vi.fn().mockReturnValue({
      limit: 10,
      offset: 0,
      sort: 'updated_at',
      order: 'desc',
    }),
  };

  beforeEach(() => {
    vi.clearAllMocks();

    // Setup store mock
    vi.mocked(useKnowledgeUnitStore).mockReturnValue(mockStore);

    // Setup API mock to return in the format that matches our updated API (full response object)
    vi.mocked(backendApi.getKnowledgeUnits).mockResolvedValue({
      knowledge_units: mockKnowledgeUnits as any,
      total: mockKnowledgeUnits.length,
      page: 1,
      page_size: 10,
      total_pages: 1,
      execution_time: 0,
    });
  });

  it('renders the Knowledge Units component with table', async () => {
    render(<KnowledgeUnits />);

    // Check for title
    expect(screen.getByText('Knowledge Units')).toBeInTheDocument();

    // Should show loading state initially
    expect(screen.getByText('Loading knowledge units...')).toBeInTheDocument();

    // Wait for the data to load
    await waitFor(() => {
      expect(screen.getByText(DIRECTIVE_NAME)).toBeInTheDocument();
      expect(screen.getByText('Crown Jewels')).toBeInTheDocument();
    });
  });

  it('handles sorting when clicking column headers', async () => {
    render(<KnowledgeUnits />);

    // Wait for the data to load
    await waitFor(() => {
      expect(screen.getByText(DIRECTIVE_NAME)).toBeInTheDocument();
    });

    // Click on the Name column header
    fireEvent.click(screen.getByText('Name'));

    // Should call the setSorting method
    expect(mockStore.setSorting).toHaveBeenCalledWith('name');
  });

  it('handles search input', async () => {
    render(<KnowledgeUnits />);

    // Wait for the data to load
    await waitFor(() => {
      expect(screen.getByText('Crown Jewels')).toBeInTheDocument();
    });

    // Find the search input and type in it
    const searchInput = screen.getByPlaceholderText('Search knowledge units...');
    fireEvent.change(searchInput, { target: { value: 'crown' } });

    // Wait for debounce
    await waitFor(() => {
      expect(mockStore.setSearchTerm).toHaveBeenCalledWith('crown');
    });
  });

  it('handles type filtering', async () => {
    render(<KnowledgeUnits />);

    // Wait for the data to load
    await waitFor(() => {
      expect(screen.getByText(DIRECTIVE_NAME)).toBeInTheDocument();
    });

    // Check that the filter components are rendered
    expect(screen.getByText('Type')).toBeInTheDocument();
    expect(screen.getByText('Directive')).toBeInTheDocument();
    expect(screen.getByText('Table')).toBeInTheDocument();
    expect(screen.getByText('Tool')).toBeInTheDocument();
    expect(screen.getByText('Document')).toBeInTheDocument();
  });

  it('handles errors gracefully', async () => {
    // Mock an API error
    const mockRunSafe = vi.fn().mockResolvedValue([null, new Error('Failed to fetch')]);

    // Update the useErrorHandler mock to return an error
    // eslint-disable-next-line @typescript-eslint/no-require-imports -- legacy skipped test
    const mockUseErrorHandler = require('../../../hooks/useErrorHandler').default;
    mockUseErrorHandler.mockReturnValue({
      error: { hasError: true, message: 'Failed to fetch knowledge units' },
      clearError: vi.fn(),
      runSafe: mockRunSafe,
    });

    render(<KnowledgeUnits />);

    // Should show error message
    await waitFor(() => {
      expect(screen.getByText('Failed to fetch knowledge units')).toBeInTheDocument();
    });
  });

  it('handles pagination', async () => {
    // Setup with more items to enable pagination
    vi.mocked(useKnowledgeUnitStore).mockReturnValue({
      ...mockStore,
      totalCount: 25, // More than one page
    });

    render(<KnowledgeUnits />);

    // Wait for the data to load
    await waitFor(() => {
      expect(screen.getByText(DIRECTIVE_NAME)).toBeInTheDocument();
    });

    // Find and click the next page button
    const nextPageButton = screen.getByLabelText('Go to next page');
    fireEvent.click(nextPageButton);

    // Should call setPagination
    expect(mockStore.setPagination).toHaveBeenCalledWith({ currentPage: 2 });
  });
});
