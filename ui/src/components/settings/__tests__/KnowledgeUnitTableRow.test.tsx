import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import { KnowledgeUnitTableRow } from '../KnowledgeUnitTableRow';

// Mock the API
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getDirective: vi.fn(),
    getTable: vi.fn(),
    getDocument: vi.fn(),
    getKnowledgeUnit: vi.fn(),
    getKnowledgeUnitTasks: vi.fn(),
  },
}));

// Mock the user display hook to return the userId as-is
vi.mock('../../../hooks/useUserDisplay', () => ({
  useUserDisplay: (userId: string | undefined) => userId || 'Unknown',
}));

// Mock the knowledge unit store
vi.mock('../../../store/knowledgeUnitStore', () => ({
  useKnowledgeUnitStore: vi.fn((selector: (state: Record<string, string>) => string) => {
    const state = { searchTerm: '' };
    return selector(state);
  }),
}));

// Mock the error handler hook
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: vi.fn(() => ({
    runSafe: vi.fn(async (promise) => {
      try {
        const result = await promise;
        return [result, undefined];
      } catch (error) {
        return [undefined, error];
      }
    }),
    error: null,
    handleError: vi.fn(),
    clearError: vi.fn(),
    createContext: vi.fn(),
  })),
}));

describe('KnowledgeUnitTableRow Component', () => {
  const MOCK_TIMESTAMP = '2025-04-24T17:32:36.048157';
  const TABLE_CONTENT_LABEL = 'Table Content:';
  const TEST_TIMESTAMP = '2024-01-01T00:00:00Z';

  // Real-world inspired sample data matching our API
  const mockDirective = {
    id: '00000001-0000-0000-0000-000000000001',
    name: 'Company Default',
    description: 'Default company directive for all analyses',
    type: 'directive',
    created_by: 'system',
    visibility: 'public',
    tags: [],
    source_document_id: null,
    version: '1.0.0',
    status: 'active',
    editable: true,
    content:
      'When analyzing any security event for our company, prioritize critical assets and consider the business impact first. Always check against our approved security baseline.',
    created_at: MOCK_TIMESTAMP,
    updated_at: MOCK_TIMESTAMP,
    usage_stats: {
      count: 0,
      last_used: null,
    },
    dependencies: [],
    embedding_vector: null,
    referenced_tables: [],
    referenced_documents: [],
  } as any;

  const mockTable = {
    id: '00000002-0000-0000-0000-000000000001',
    name: 'Crown Jewels',
    description: 'List of critical assets and systems for the company',
    type: 'table',
    created_by: 'system',
    visibility: 'public',
    tags: [],
    source_document_id: null,
    version: '1.0.0',
    status: 'active',
    editable: true,
    data_type: 'tabular',
    content: {
      data: [
        ['Primary Database Cluster', '10.0.1.10-10.0.1.15', 'Critical', 'Database Team'],
        // eslint-disable-next-line sonarjs/no-hardcoded-ip
        ['Customer Data Warehouse', '10.0.2.20', 'Critical', 'Data Science'],
      ],
      columns: ['Asset Name', 'IP Address', 'Criticality', 'Owner'],
    },
    embedding_metadata: null,
    created_at: MOCK_TIMESTAMP,
    updated_at: MOCK_TIMESTAMP,
    usage_stats: {
      count: 0,
      last_used: null,
    },
    dependencies: [],
    embedding_vector: null,
  } as any;

  const mockTool = {
    id: '00000003-0000-0000-0000-000000000001',
    name: 'CVE Getter',
    description: 'Tool for retrieving CVE information from the National Vulnerability Database',
    type: 'tool',
    created_by: 'system',
    visibility: 'public',
    tags: [],
    source_document_id: null,
    version: '1.0.0',
    status: 'active',
    editable: true,
    mcp_endpoint: 'https://api.example.com/mcp/cve-lookup',
    integration_id: null,
    created_at: MOCK_TIMESTAMP,
    updated_at: MOCK_TIMESTAMP,
    usage_stats: {
      count: 0,
      last_used: null,
    },
    dependencies: [],
    embedding_vector: null,
  } as any;

  const mockDocument = {
    id: '00000004-0000-0000-0000-000000000001',
    name: 'Palo Alto THREAT Logs Doc',
    description: 'Documentation for Palo Alto THREAT log format and interpretation',
    type: 'document',
    created_by: 'system',
    visibility: 'public',
    tags: [],
    source_document_id: null,
    version: '1.0.0',
    status: 'active',
    editable: true,
    document_type: 'markdown',
    content:
      '# Palo Alto THREAT Log Format\n\nThis document describes the format of Palo Alto THREAT logs and how to interpret them.',
    content_source: 'manual',
    source_url: null,
    embedding_metadata: null,
    vectorized: false,
    created_at: MOCK_TIMESTAMP,
    updated_at: MOCK_TIMESTAMP,
    usage_stats: {
      count: 0,
      last_used: null,
    },
    dependencies: [],
    embedding_vector: null,
  } as any;

  // Mock tasks that use a knowledge unit
  const mockDependentTasks = [
    {
      id: '00000005-0000-0000-0000-000000000001',
      name: 'Long Analysis Report to Summary',
      description: 'Convert a detailed step-by-step analysis report into a concise summary',
      function: 'summarization',
      scope: 'processing',
      status: 'active',
    },
    {
      id: '00000005-0000-0000-0000-000000000002',
      name: 'Palo Alto Threat Event Summarizer',
      description: 'Summarize Palo Alto THREAT events in a clear, actionable format',
      function: 'summarization',
      scope: 'processing',
      status: 'active',
    },
  ] as any;

  const mockProps = {
    expanded: false,
    onRowClick: vi.fn(),
    onToggleExpand: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();

    // Mock the getKnowledgeUnitTasks endpoint
    vi.mocked(backendApi.getKnowledgeUnitTasks).mockResolvedValue(mockDependentTasks);
  });

  it('renders the collapsed row correctly for a directive', () => {
    render(
      <table>
        <tbody>
          <KnowledgeUnitTableRow knowledgeUnit={mockDirective} {...mockProps} />
        </tbody>
      </table>
    );

    expect(screen.getByText('Company Default')).toBeInTheDocument();
    expect(screen.getByText('Default company directive for all analyses')).toBeInTheDocument();
    expect(screen.getByText('directive')).toBeInTheDocument();
    expect(screen.getByText('system')).toBeInTheDocument();
    expect(screen.getByText('active')).toBeInTheDocument();
    expect(screen.getByText('1.0.0')).toBeInTheDocument();
  });

  it.skip('expands the row when clicked and fetches detailed information for a directive', async () => {
    // Mock the directive fetch response with format matching real API
    vi.mocked(backendApi.getDirective).mockResolvedValue(mockDirective);

    render(
      <table>
        <tbody>
          <KnowledgeUnitTableRow knowledgeUnit={mockDirective} {...mockProps} expanded={true} />
        </tbody>
      </table>
    );

    // Should show loading initially
    expect(screen.getByRole('status')).toBeInTheDocument();

    // Wait for content to load
    await waitFor(() => {
      expect(screen.getByText('Directive Content:')).toBeInTheDocument();
      const content = screen.getByText(/When analyzing any security event for our company/);
      expect(content).toBeInTheDocument();
    });

    // Should also show dependent tasks
    await waitFor(() => {
      expect(screen.getByText('Tasks using this Knowledge Unit:')).toBeInTheDocument();
      expect(screen.getByText('Long Analysis Report to Summary')).toBeInTheDocument();
    });
  });

  it.skip('expands the row when clicked and fetches detailed information for a table', async () => {
    // Mock the table fetch response
    vi.mocked(backendApi.getTable).mockResolvedValue(mockTable);

    render(
      <table>
        <tbody>
          <KnowledgeUnitTableRow knowledgeUnit={mockTable} {...mockProps} expanded={true} />
        </tbody>
      </table>
    );

    // Wait for content to load
    await waitFor(() => {
      expect(screen.getByText(TABLE_CONTENT_LABEL)).toBeInTheDocument();
      expect(screen.getByText('Asset Name')).toBeInTheDocument();
      expect(screen.getByText('IP Address')).toBeInTheDocument();
      expect(screen.getByText('Primary Database Cluster')).toBeInTheDocument();
      expect(screen.getByText('10.0.1.10-10.0.1.15')).toBeInTheDocument();
    });
  });

  it('expands tool row using list data without making API call', async () => {
    render(
      <table>
        <tbody>
          <KnowledgeUnitTableRow knowledgeUnit={mockTool} {...mockProps} expanded={true} />
        </tbody>
      </table>
    );

    // Wait for content to load — should use knowledgeUnit prop directly
    await waitFor(() => {
      expect(screen.getByText('Tool Details:')).toBeInTheDocument();
      expect(screen.getByText('https://api.example.com/mcp/cve-lookup')).toBeInTheDocument();
    });

    // Should NOT have called any API since tool type uses list data directly
    expect(backendApi.getDirective).not.toHaveBeenCalled();
    expect(backendApi.getTable).not.toHaveBeenCalled();
    expect(backendApi.getDocument).not.toHaveBeenCalled();
  });

  it.skip('expands the row when clicked and fetches detailed information for a document', async () => {
    // Mock the document fetch response
    vi.mocked(backendApi.getDocument).mockResolvedValue(mockDocument);

    render(
      <table>
        <tbody>
          <KnowledgeUnitTableRow knowledgeUnit={mockDocument} {...mockProps} expanded={true} />
        </tbody>
      </table>
    );

    // Wait for content to load
    await waitFor(() => {
      expect(screen.getByText('Document Details:')).toBeInTheDocument();
      expect(screen.getByText('manual')).toBeInTheDocument();
      expect(screen.getByText(/This document describes the format/)).toBeInTheDocument();
    });
  });

  it('triggers onToggleExpand when expand/collapse button is clicked', () => {
    render(
      <table>
        <tbody>
          <KnowledgeUnitTableRow knowledgeUnit={mockDirective} {...mockProps} />
        </tbody>
      </table>
    );

    // Find and click the expand button
    const expandButton = screen.getByLabelText('Expand row');
    fireEvent.click(expandButton);

    // Should call the onToggleExpand callback
    expect(mockProps.onToggleExpand).toHaveBeenCalled();
  });

  it('triggers onRowClick when row is clicked', () => {
    render(
      <table>
        <tbody>
          <KnowledgeUnitTableRow knowledgeUnit={mockDirective} {...mockProps} />
        </tbody>
      </table>
    );

    // Find and click the row
    const row = screen.getByText('Company Default').closest('tr');
    fireEvent.click(row as HTMLElement);

    // Should call the onRowClick callback
    expect(mockProps.onRowClick).toHaveBeenCalled();
  });

  describe('Table dual-format rendering in expanded rows', () => {
    it('should render table content in Format 1 (columns + data arrays)', async () => {
      const tableFormat1 = {
        id: 'table-format1',
        name: 'Feedback Table',
        description: 'Format 1 table',
        type: 'table',
        content: {
          columns: ['test', 'one', 'two'],
          data: [
            ['val1', 'val2', 'val3'],
            ['val4', 'val5', 'val6'],
          ],
        },
        row_count: 2,
        column_count: 3,
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      };

      vi.mocked(backendApi.getTable).mockResolvedValue(tableFormat1 as any);

      render(
        <table>
          <tbody>
            <KnowledgeUnitTableRow
              knowledgeUnit={tableFormat1 as any}
              {...mockProps}
              expanded={true}
            />
          </tbody>
        </table>
      );

      // Wait for table content to load
      await waitFor(() => {
        expect(screen.getByText(TABLE_CONTENT_LABEL)).toBeInTheDocument();
        expect(screen.getByText('(2 rows, 3 columns)')).toBeInTheDocument();
      });

      // Check column headers are rendered
      expect(screen.getByText('test')).toBeInTheDocument();
      expect(screen.getByText('one')).toBeInTheDocument();
      expect(screen.getByText('two')).toBeInTheDocument();

      // Check data cells are rendered
      expect(screen.getByText('val1')).toBeInTheDocument();
      expect(screen.getByText('val2')).toBeInTheDocument();
      expect(screen.getByText('val3')).toBeInTheDocument();
      expect(screen.getByText('val4')).toBeInTheDocument();
      expect(screen.getByText('val5')).toBeInTheDocument();
      expect(screen.getByText('val6')).toBeInTheDocument();
    });

    it('should render table content in Format 2 (rows as objects)', async () => {
      const tableFormat2 = {
        id: 'table-format2',
        name: 'Threat Actor Database',
        description: 'Format 2 table',
        type: 'table',
        content: {
          rows: [
            { name: 'Lazarus Group', ttps: '["spear-phishing"]', type: 'nation-state' },
            { name: 'FIN7', ttps: '["pos-malware"]', type: 'criminal' },
          ],
        },
        row_count: 2,
        column_count: 3,
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      };

      vi.mocked(backendApi.getTable).mockResolvedValue(tableFormat2 as any);

      render(
        <table>
          <tbody>
            <KnowledgeUnitTableRow
              knowledgeUnit={tableFormat2 as any}
              {...mockProps}
              expanded={true}
            />
          </tbody>
        </table>
      );

      // Wait for table content to load
      await waitFor(() => {
        expect(screen.getByText(TABLE_CONTENT_LABEL)).toBeInTheDocument();
        expect(screen.getByText('(2 rows, 3 columns)')).toBeInTheDocument();
      });

      // Check column headers extracted from rows
      expect(screen.getByText('name')).toBeInTheDocument();
      expect(screen.getByText('ttps')).toBeInTheDocument();
      expect(screen.getByText('type')).toBeInTheDocument();

      // Check data cells are rendered
      expect(screen.getByText('Lazarus Group')).toBeInTheDocument();
      expect(screen.getByText('["spear-phishing"]')).toBeInTheDocument();
      expect(screen.getByText('nation-state')).toBeInTheDocument();
      expect(screen.getByText('FIN7')).toBeInTheDocument();
      expect(screen.getByText('["pos-malware"]')).toBeInTheDocument();
      expect(screen.getByText('criminal')).toBeInTheDocument();
    });

    it('should show "No table data available" when table has no content', async () => {
      const emptyTable = {
        id: 'table-empty',
        name: 'Empty Table',
        description: 'Table with no content',
        type: 'table',
        content: {},
        row_count: 0,
        column_count: 0,
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      };

      vi.mocked(backendApi.getTable).mockResolvedValue(emptyTable as any);

      render(
        <table>
          <tbody>
            <KnowledgeUnitTableRow
              knowledgeUnit={emptyTable as any}
              {...mockProps}
              expanded={true}
            />
          </tbody>
        </table>
      );

      // Wait for content to load
      await waitFor(() => {
        expect(screen.getByText(TABLE_CONTENT_LABEL)).toBeInTheDocument();
      });

      // Should show "No table data available"
      expect(screen.getByText('No table data available')).toBeInTheDocument();
    });

    it('should show "No table data available" when Format 1 has empty columns', async () => {
      const emptyFormat1Table = {
        id: 'table-empty-format1',
        name: 'Empty Format 1 Table',
        description: 'Format 1 table with empty columns',
        type: 'table',
        content: {
          columns: [],
          data: [],
        },
        row_count: 0,
        column_count: 0,
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      };

      vi.mocked(backendApi.getTable).mockResolvedValue(emptyFormat1Table as any);

      render(
        <table>
          <tbody>
            <KnowledgeUnitTableRow
              knowledgeUnit={emptyFormat1Table as any}
              {...mockProps}
              expanded={true}
            />
          </tbody>
        </table>
      );

      // Wait for content to load
      await waitFor(() => {
        expect(screen.getByText(TABLE_CONTENT_LABEL)).toBeInTheDocument();
      });

      // Should show "No table data available"
      expect(screen.getByText('No table data available')).toBeInTheDocument();
    });

    it('should show "No table data available" when Format 2 has empty rows', async () => {
      const emptyFormat2Table = {
        id: 'table-empty-format2',
        name: 'Empty Format 2 Table',
        description: 'Format 2 table with empty rows',
        type: 'table',
        content: {
          rows: [],
        },
        row_count: 0,
        column_count: 0,
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      };

      vi.mocked(backendApi.getTable).mockResolvedValue(emptyFormat2Table as any);

      render(
        <table>
          <tbody>
            <KnowledgeUnitTableRow
              knowledgeUnit={emptyFormat2Table as any}
              {...mockProps}
              expanded={true}
            />
          </tbody>
        </table>
      );

      // Wait for content to load
      await waitFor(() => {
        expect(screen.getByText(TABLE_CONTENT_LABEL)).toBeInTheDocument();
      });

      // Should show "No table data available"
      expect(screen.getByText('No table data available')).toBeInTheDocument();
    });

    it('should handle Format 1 tables with data but no columns gracefully', async () => {
      const format1NoColumns = {
        id: 'table-format1-no-columns',
        name: 'Format 1 No Columns',
        description: 'Format 1 table with data but no columns',
        type: 'table',
        content: {
          columns: [],
          data: [['val1', 'val2']],
        },
        row_count: 1,
        column_count: 0,
        status: 'active',
        version: '1.0.0',
        created_by: 'test-user',
        created_at: TEST_TIMESTAMP,
        updated_at: TEST_TIMESTAMP,
        editable: true,
      };

      vi.mocked(backendApi.getTable).mockResolvedValue(format1NoColumns as any);

      render(
        <table>
          <tbody>
            <KnowledgeUnitTableRow
              knowledgeUnit={format1NoColumns as any}
              {...mockProps}
              expanded={true}
            />
          </tbody>
        </table>
      );

      // Wait for content to load
      await waitFor(() => {
        expect(screen.getByText(TABLE_CONTENT_LABEL)).toBeInTheDocument();
      });

      // Should show "No table data available" when columns are empty
      expect(screen.getByText('No table data available')).toBeInTheDocument();
    });
  });
});
