import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// eslint-disable-next-line import/order -- types needed before vi.mock block
import { DirectiveKU, TableKU, DocumentKU } from '../../types/knowledge';

// Use vi.hoisted to ensure mocks are available before vi.mock runs
const { mockGet, mockPost, mockPut, mockPatch, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPut: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock('axios', () => {
  return {
    default: {
      create: vi.fn(() => ({
        get: mockGet,
        post: mockPost,
        put: mockPut,
        patch: mockPatch,
        delete: mockDelete,
        interceptors: {
          request: { use: vi.fn(), eject: vi.fn() },
          response: { use: vi.fn(), eject: vi.fn() },
        },
      })),
    },
  };
});

import { backendApi } from '../backendApi';

// Mock the logger
vi.mock('../../utils/logger', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

const MOCK_TIMESTAMP = '2026-04-26T00:00:00Z';

describe('backendApi - Knowledge Unit Update Methods', () => {
  beforeEach(() => {
    // Clear mock history but keep implementations
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('updateDirective', () => {
    const directiveId = 'directive-123';
    const updateData: Partial<DirectiveKU> = {
      name: 'Updated Directive',
      description: 'Updated description',
      content: 'Updated content',
    };

    const mockResponse = {
      id: directiveId,
      name: 'Updated Directive',
      description: 'Updated description',
      type: 'directive',
      content: 'Updated content',
      status: 'active',
      version: '1.0.1',
      created_by: 'user-123',
      created_at: MOCK_TIMESTAMP,
      updated_at: '2026-04-27T00:00:00Z',
      editable: true,
    } as DirectiveKU;

    it('should update a directive successfully', async () => {
      mockPatch.mockResolvedValue({
        data: { data: mockResponse, meta: { request_id: 'test' } },
      });

      const result = await backendApi.updateDirective(directiveId, updateData);

      expect(mockPatch).toHaveBeenCalledWith(
        `/knowledge-units/directives/${directiveId}`,
        updateData
      );
      expect(result).toEqual(mockResponse);
    });

    it('should handle directive update error', async () => {
      const error = new Error('Network error');
      mockPatch.mockRejectedValue(error);

      await expect(backendApi.updateDirective(directiveId, updateData)).rejects.toThrow(
        'Network error'
      );

      expect(mockPatch).toHaveBeenCalledWith(
        `/knowledge-units/directives/${directiveId}`,
        updateData
      );
    });

    it('should include proper error context on failure', async () => {
      const error = new Error('Update failed');
      mockPatch.mockRejectedValue(error);

      try {
        await backendApi.updateDirective(directiveId, updateData);
      } catch {
        // Error should be logged with context
        expect(mockPatch).toHaveBeenCalled();
      }
    });
  });

  describe('updateTable', () => {
    const tableId = 'table-456';
    const updateData: Partial<TableKU> = {
      name: 'Updated Table',
      description: 'Updated table description',
      content: {
        columns: ['Col1', 'Col2', 'Col3'],
        data: [
          ['A1', 'B1', 'C1'],
          ['A2', 'B2', 'C2'],
        ],
      },
    };

    const mockResponse = {
      id: tableId,
      name: 'Updated Table',
      description: 'Updated table description',
      type: 'table',
      content: {
        columns: ['Col1', 'Col2', 'Col3'],
        data: [
          ['A1', 'B1', 'C1'],
          ['A2', 'B2', 'C2'],
        ],
      },
      status: 'active',
      version: '1.0.1',
      created_by: 'user-456',
      created_at: MOCK_TIMESTAMP,
      updated_at: '2026-04-27T00:00:00Z',
      editable: true,
    } as TableKU;

    it('should update a table successfully', async () => {
      mockPut.mockResolvedValue({
        data: { data: mockResponse, meta: { request_id: 'test' } },
      });

      const result = await backendApi.updateTable(tableId, updateData);

      expect(mockPut).toHaveBeenCalledWith(`/knowledge-units/tables/${tableId}`, updateData);
      expect(result).toEqual(mockResponse);
    });

    it('should handle empty table data', async () => {
      const emptyTableUpdate: Partial<TableKU> = {
        name: 'Empty Table',
        content: {
          columns: [],
          data: [],
        },
      };

      mockPut.mockResolvedValue({
        data: { data: { ...mockResponse, ...emptyTableUpdate }, meta: { request_id: 'test' } },
      });

      const result = await backendApi.updateTable(tableId, emptyTableUpdate);

      expect(mockPut).toHaveBeenCalledWith(`/knowledge-units/tables/${tableId}`, emptyTableUpdate);
      expect(result.content.columns).toEqual([]);
      expect(result.content.data).toEqual([]);
    });

    it('should handle table update error', async () => {
      const error = new Error('Database error');
      mockPut.mockRejectedValue(error);

      await expect(backendApi.updateTable(tableId, updateData)).rejects.toThrow('Database error');

      expect(mockPut).toHaveBeenCalledWith(`/knowledge-units/tables/${tableId}`, updateData);
    });

    it('should handle complex table structures', async () => {
      const complexTableData: Partial<TableKU> = {
        content: {
          columns: ['ID', 'Name', 'Value', 'Status', 'Date'],
          data: [
            [1, 'Item A', 100.5, true, '2026-04-26'],
            [2, 'Item B', 200.75, false, '2026-04-27'],
            [3, 'Item C', 300.25, true, '2026-04-28'],
          ],
        },
      };

      mockPut.mockResolvedValue({
        data: { data: { ...mockResponse, ...complexTableData }, meta: { request_id: 'test' } },
      });

      const result = await backendApi.updateTable(tableId, complexTableData);

      expect(result.content.columns).toHaveLength(5);
      expect(result.content.data).toHaveLength(3);
      expect(result.content.data[0]).toContain(100.5);
    });
  });

  describe('updateDocument', () => {
    const documentId = 'doc-789';
    const updateData: Partial<DocumentKU> = {
      name: 'Updated Document',
      description: 'Updated document description',
      content: '# Updated Document\n\nThis is the updated content.',
    };

    const mockResponse = {
      id: documentId,
      name: 'Updated Document',
      description: 'Updated document description',
      type: 'document',
      content: '# Updated Document\n\nThis is the updated content.',
      status: 'active',
      version: '2.0.0',
      created_by: 'user-789',
      created_at: MOCK_TIMESTAMP,
      updated_at: '2026-04-27T00:00:00Z',
      editable: true,
    } as DocumentKU;

    it('should update a document successfully', async () => {
      mockPut.mockResolvedValue({
        data: { data: mockResponse, meta: { request_id: 'test' } },
      });

      const result = await backendApi.updateDocument(documentId, updateData);

      expect(mockPut).toHaveBeenCalledWith(`/knowledge-units/documents/${documentId}`, updateData);
      expect(result).toEqual(mockResponse);
    });

    it('should handle document update with large content', async () => {
      const largeContent = 'x'.repeat(10_000);
      const largeUpdateData: Partial<DocumentKU> = {
        content: largeContent,
      };

      mockPut.mockResolvedValue({
        data: { data: { ...mockResponse, content: largeContent }, meta: { request_id: 'test' } },
      });

      const result = await backendApi.updateDocument(documentId, largeUpdateData);

      expect(mockPut).toHaveBeenCalledWith(
        `/knowledge-units/documents/${documentId}`,
        largeUpdateData
      );
      expect(result.content).toHaveLength(10_000);
    });

    it('should handle document update error', async () => {
      const error = new Error('Validation error');
      mockPut.mockRejectedValue(error);

      await expect(backendApi.updateDocument(documentId, updateData)).rejects.toThrow(
        'Validation error'
      );

      expect(mockPut).toHaveBeenCalledWith(`/knowledge-units/documents/${documentId}`, updateData);
    });

    it('should handle partial document updates', async () => {
      const partialUpdate: Partial<DocumentKU> = {
        description: 'Only updating description',
      };

      mockPut.mockResolvedValue({
        data: { data: { ...mockResponse, ...partialUpdate }, meta: { request_id: 'test' } },
      });

      const result = await backendApi.updateDocument(documentId, partialUpdate);

      expect(mockPut).toHaveBeenCalledWith(
        `/knowledge-units/documents/${documentId}`,
        partialUpdate
      );
      expect(result.description).toBe('Only updating description');
    });
  });

  describe('Error handling across all update methods', () => {
    it('should handle 404 errors', async () => {
      const error = {
        response: {
          status: 404,
          data: { message: 'Knowledge unit not found' },
        },
      };
      mockPatch.mockRejectedValue(error);

      await expect(backendApi.updateDirective('non-existent', {})).rejects.toMatchObject(error);
    });

    it('should handle 403 forbidden errors', async () => {
      const error = {
        response: {
          status: 403,
          data: { message: 'Not authorized to edit this knowledge unit' },
        },
      };
      mockPut.mockRejectedValue(error);

      await expect(backendApi.updateTable('protected-table', {})).rejects.toMatchObject(error);
    });

    it('should handle 422 validation errors', async () => {
      const error = {
        response: {
          status: 422,
          data: {
            message: 'Validation failed',
            errors: {
              name: ['Name is required'],
              content: ['Content cannot be empty'],
            },
          },
        },
      };
      mockPut.mockRejectedValue(error);

      await expect(backendApi.updateDocument('doc-123', { name: '' })).rejects.toMatchObject(error);
    });

    it('should handle network errors', async () => {
      const error = new Error('Network Error');
      (error as any).code = 'ECONNREFUSED';
      mockPatch.mockRejectedValue(error);

      await expect(backendApi.updateDirective('directive-123', {})).rejects.toThrow(
        'Network Error'
      );
    });

    it('should handle timeout errors', async () => {
      const error = new Error('timeout of 30000ms exceeded');
      (error as any).code = 'ECONNABORTED';
      mockPut.mockRejectedValue(error);

      await expect(backendApi.updateTable('table-123', {})).rejects.toThrow('timeout');
    });
  });

  describe('Concurrent updates', () => {
    it('should handle multiple concurrent updates', async () => {
      const directive1 = { id: 'dir-1', name: 'Directive 1' };
      const table1 = { id: 'tab-1', name: 'Table 1' };
      const document1 = { id: 'doc-1', name: 'Document 1' };

      // Mock patch for directives only
      mockPatch.mockImplementation((url) => {
        if (url.includes('directives')) {
          return Promise.resolve({ data: { data: directive1, meta: { request_id: 'test' } } });
        }
        return Promise.reject(new Error('Unknown endpoint'));
      });

      // Mock put for tables and documents
      mockPut.mockImplementation((url) => {
        if (url.includes('tables')) {
          return Promise.resolve({ data: { data: table1, meta: { request_id: 'test' } } });
        } else if (url.includes('documents')) {
          return Promise.resolve({ data: { data: document1, meta: { request_id: 'test' } } });
        }
        return Promise.reject(new Error('Unknown endpoint'));
      });

      const [directiveResult, tableResult, documentResult] = await Promise.all([
        backendApi.updateDirective('dir-1', { name: 'Directive 1' }),
        backendApi.updateTable('tab-1', { name: 'Table 1' }),
        backendApi.updateDocument('doc-1', { name: 'Document 1' }),
      ]);

      expect(directiveResult).toEqual(directive1);
      expect(tableResult).toEqual(table1);
      expect(documentResult).toEqual(document1);
      expect(mockPatch).toHaveBeenCalledTimes(1); // directives only
      expect(mockPut).toHaveBeenCalledTimes(2); // tables and documents
    });
  });
});

describe('backendApi - Knowledge Unit GET Methods with Field Mapping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getDirective', () => {
    const directiveId = 'directive-123';

    it('should map ku_type to type when type field is missing', async () => {
      const mockDirectiveWithKuType = {
        id: directiveId,
        name: 'Test Directive',
        description: 'Test description',
        ku_type: 'directive', // Backend returns ku_type
        // no type field
        content: 'Test content',
        status: 'active',
        version: '1.0.0',
        created_by: 'user-123',
        created_at: MOCK_TIMESTAMP,
        updated_at: MOCK_TIMESTAMP,
        editable: true,
      };

      mockGet.mockResolvedValue({
        data: { data: mockDirectiveWithKuType, meta: { request_id: 'test' } },
      });

      const result = await backendApi.getDirective(directiveId);

      expect(mockGet).toHaveBeenCalledWith(`/knowledge-units/directives/${directiveId}`);
      expect(result.type).toBe('directive'); // Should have type field mapped from ku_type
      expect(result.id).toBe(directiveId);
    });

    it('should not override existing type field', async () => {
      const mockDirectiveWithBothFields = {
        id: directiveId,
        name: 'Test Directive',
        type: 'directive',
        ku_type: 'different_value',
        content: 'Test content',
      };

      mockGet.mockResolvedValue({
        data: { data: mockDirectiveWithBothFields, meta: { request_id: 'test' } },
      });

      const result = await backendApi.getDirective(directiveId);

      expect(result.type).toBe('directive'); // Should keep existing type field
    });

    it('should handle getDirective error', async () => {
      const error = new Error('Not found');
      mockGet.mockRejectedValue(error);

      await expect(backendApi.getDirective(directiveId)).rejects.toThrow('Not found');
      expect(mockGet).toHaveBeenCalledWith(`/knowledge-units/directives/${directiveId}`);
    });
  });

  describe('getTable', () => {
    const tableId = 'table-456';

    it('should map ku_type to type when type field is missing', async () => {
      const mockTableWithKuType = {
        id: tableId,
        name: 'Test Table',
        description: 'Test table description',
        ku_type: 'table',
        content: {
          columns: ['col1', 'col2'],
          data: [['val1', 'val2']],
        },
        status: 'active',
        version: '1.0.0',
      };

      mockGet.mockResolvedValue({
        data: { data: mockTableWithKuType, meta: { request_id: 'test' } },
      });

      const result = await backendApi.getTable(tableId);

      expect(mockGet).toHaveBeenCalledWith(`/knowledge-units/tables/${tableId}`);
      expect(result.type).toBe('table');
      expect(result.content).toBeDefined();
    });

    it('should handle table with rows format (Format 2)', async () => {
      const mockTableWithRows = {
        id: tableId,
        name: 'Threat Actor Database',
        ku_type: 'table',
        content: {
          rows: [
            { name: 'Lazarus Group', type: 'APT' },
            { name: 'FIN7', type: 'Ransomware' },
          ],
        },
      };

      mockGet.mockResolvedValue({
        data: { data: mockTableWithRows, meta: { request_id: 'test' } },
      });

      const result = await backendApi.getTable(tableId);

      expect(result.type).toBe('table');
      expect((result.content as any).rows).toHaveLength(2);
    });

    it('should handle getTable error', async () => {
      const error = new Error('Table not found');
      mockGet.mockRejectedValue(error);

      await expect(backendApi.getTable(tableId)).rejects.toThrow('Table not found');
    });
  });

  describe('getDocument', () => {
    const documentId = 'doc-789';

    it('should map ku_type to type when type field is missing', async () => {
      const mockDocumentWithKuType = {
        id: documentId,
        name: 'Test Document',
        description: 'Test document description',
        ku_type: 'document',
        content: '# Test Document\n\nContent here.',
        status: 'active',
        version: '1.0.0',
      };

      mockGet.mockResolvedValue({
        data: { data: mockDocumentWithKuType, meta: { request_id: 'test' } },
      });

      const result = await backendApi.getDocument(documentId);

      expect(mockGet).toHaveBeenCalledWith(`/knowledge-units/documents/${documentId}`);
      expect(result.type).toBe('document');
      expect(result.content).toContain('# Test Document');
    });

    it('should handle getDocument error', async () => {
      const error = new Error('Document not found');
      mockGet.mockRejectedValue(error);

      await expect(backendApi.getDocument(documentId)).rejects.toThrow('Document not found');
    });
  });

  describe('Field mapping edge cases', () => {
    it('should handle null ku_type gracefully', async () => {
      const mockData = {
        id: 'test-1',
        name: 'Test',
        ku_type: null,
        content: 'test',
      };

      mockGet.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await backendApi.getDirective('test-1');

      // Should not have type field if ku_type is null
      expect((result as any).ku_type).toBeNull();
    });

    it('should handle undefined ku_type gracefully', async () => {
      const mockData = {
        id: 'test-2',
        name: 'Test',
        content: 'test',
      };

      mockGet.mockResolvedValue({ data: { data: mockData, meta: { request_id: 'test' } } });

      const result = await backendApi.getTable('test-2');

      // Should work without errors
      expect(result.id).toBe('test-2');
    });
  });
});
