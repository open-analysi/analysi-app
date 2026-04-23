import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const { mockGet, mockPost, mockPut, mockPatch, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPut: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock('axios', () => ({
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
}));

vi.mock('../../utils/errorHandler', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

import * as knowledgeApi from '../knowledgeApi';

// ---------------------------------------------------------------------------
// Shared constants (lint: extract strings used 4+ times)
// ---------------------------------------------------------------------------
const TEST_ID = 'abc-123';
const DIRECTIVE_TYPE = 'directive';
const TABLE_TYPE = 'table';
const TOOL_TYPE = 'tool';

describe('knowledgeApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // =========================================================================
  // getKnowledgeUnits — CRITICAL data-transformation tests
  // =========================================================================
  describe('getKnowledgeUnits', () => {
    it('maps ku_type to type and applies default fields', async () => {
      const rawKU = {
        id: 'ku-1',
        name: 'Test KU',
        ku_type: DIRECTIVE_TYPE,
        created_by: 'user-uuid-1',
        description: 'A test directive',
      };

      mockGet.mockResolvedValueOnce({
        data: { data: [rawKU], meta: { total: 1, limit: 10, offset: 0 } },
      });

      const result = await knowledgeApi.getKnowledgeUnits();
      const ku = result.knowledge_units[0];

      // Core mapping: ku_type -> type
      expect(ku.type).toBe(DIRECTIVE_TYPE);

      // Original fields preserved
      expect(ku.id).toBe('ku-1');
      expect(ku.name).toBe('Test KU');
      expect((ku as any).ku_type).toBe(DIRECTIVE_TYPE);
      expect(ku.description).toBe('A test directive');

      // Default fields
      expect(ku.status).toBe('active');
      expect(ku.version).toBe('1.0.0');
      expect(ku.created_by).toBe('user-uuid-1');
      expect(ku.visibility).toBe('public');
      expect(ku.tags).toEqual([]);
      expect(ku.source_document_id).toBeUndefined();
      expect(ku.editable).toBe(true);
      expect(ku.usage_stats).toEqual({ count: 0, last_used: undefined });
      expect(ku.dependencies).toEqual([]);
      expect(ku.embedding_vector).toBeUndefined();

      // Pagination passthrough
      expect(result.total).toBe(1);
      expect(result.page).toBe(1);
      expect(result.page_size).toBe(10);
      expect(result.total_pages).toBe(1);
      expect(result.execution_time).toBe(0);
    });

    it('filters out null/undefined entries and entries without id', async () => {
      const rawKUs = [
        { id: 'ku-1', name: 'Valid', ku_type: TABLE_TYPE },
        null,
        undefined,
        { name: 'No ID', ku_type: TABLE_TYPE }, // missing id
        { id: 'ku-2', name: 'Also valid', ku_type: TOOL_TYPE },
      ];

      mockGet.mockResolvedValueOnce({
        data: { data: rawKUs, meta: { total: 5 } },
      });

      const result = await knowledgeApi.getKnowledgeUnits();

      expect(result.knowledge_units).toHaveLength(2);
      expect(result.knowledge_units[0].id).toBe('ku-1');
      expect(result.knowledge_units[1].id).toBe('ku-2');
    });

    it('uses fallback values when pagination fields are missing', async () => {
      mockGet.mockResolvedValueOnce({
        data: {
          data: [
            { id: 'ku-1', ku_type: DIRECTIVE_TYPE },
            { id: 'ku-2', ku_type: DIRECTIVE_TYPE },
          ],
          meta: {},
        },
      });

      const result = await knowledgeApi.getKnowledgeUnits();

      // Fallback: total = mappedKUs.length
      expect(result.total).toBe(2);
      // Fallback: page = 1
      expect(result.page).toBe(1);
      // Fallback: page_size = mappedKUs.length
      expect(result.page_size).toBe(2);
      // Fallback: total_pages = 1
      expect(result.total_pages).toBe(1);
      // Fallback: execution_time = 0
      expect(result.execution_time).toBe(0);
    });

    it('throws on API error', async () => {
      const apiError = new Error('Network error');
      mockGet.mockRejectedValueOnce(apiError);

      await expect(knowledgeApi.getKnowledgeUnits()).rejects.toThrow('Network error');
    });
  });

  // =========================================================================
  // getDirective — ku_type -> type mapping
  // =========================================================================
  describe('getDirective', () => {
    it('maps ku_type to type when type is missing', async () => {
      mockGet.mockResolvedValueOnce({
        data: {
          data: {
            id: TEST_ID,
            name: 'My Directive',
            ku_type: DIRECTIVE_TYPE,
            // no `type` field — backend doesn't send it
          },
          meta: { request_id: 'test' },
        },
      });

      const result = await knowledgeApi.getDirective(TEST_ID);

      // fetchOne unwraps envelope, returns DirectiveKU directly
      expect(result.id).toBe(TEST_ID);
      expect(result.type).toBe(DIRECTIVE_TYPE);
      expect((result as any).ku_type).toBe(DIRECTIVE_TYPE);

      // Verify correct endpoint
      expect(mockGet).toHaveBeenCalledWith(`/knowledge-units/directives/${TEST_ID}`);
    });
  });

  // =========================================================================
  // getTable — ku_type -> type mapping
  // =========================================================================
  describe('getTable', () => {
    it('maps ku_type to type', async () => {
      mockGet.mockResolvedValueOnce({
        data: {
          data: { id: TEST_ID, name: 'My Table', ku_type: TABLE_TYPE },
          meta: { request_id: 'test' },
        },
      });

      const result = await knowledgeApi.getTable(TEST_ID);

      expect(result.type).toBe(TABLE_TYPE);
      expect((result as any).ku_type).toBe(TABLE_TYPE);
      expect(mockGet).toHaveBeenCalledWith(`/knowledge-units/tables/${TEST_ID}`);
    });
  });

  // =========================================================================
  // listKdgNodes — backend NodeResponse -> KdgNode mapping
  // =========================================================================
  describe('listKdgNodes', () => {
    it('maps backend NodeResponse to KdgNode format', async () => {
      const backendNodes = [
        {
          id: 'node-1',
          type: 'task',
          name: 'Enrichment Task',
          description: 'Enriches alerts',
          status: 'active',
          created_at: '2025-01-01T00:00:00Z',
          updated_at: '2025-06-01T00:00:00Z',
        },
        {
          id: 'node-2',
          type: 'document',
          name: 'Policy Doc',
          // description omitted — should default to ''
        },
      ];

      mockGet.mockResolvedValueOnce({
        data: { data: backendNodes, meta: { request_id: 'test' } },
      });

      const result = await knowledgeApi.listKdgNodes({ type: 'task' });

      expect(result).toHaveLength(2);

      // First node: full mapping
      expect(result[0].id).toBe('node-1');
      expect(result[0].type).toBe('task');
      expect(result[0].label).toBe('Enrichment Task');
      expect(result[0].data.name).toBe('Enrichment Task');
      expect(result[0].data.description).toBe('Enriches alerts');
      expect(result[0].data.status).toBe('active');
      expect(result[0].data.created_at).toBe('2025-01-01T00:00:00Z');
      expect(result[0].data.updated_at).toBe('2025-06-01T00:00:00Z');

      // Second node: missing description defaults to ''
      expect(result[1].label).toBe('Policy Doc');
      expect(result[1].data.description).toBe('');

      expect(mockGet).toHaveBeenCalledWith('/kdg/nodes', { params: { type: 'task' } });
    });
  });

  // =========================================================================
  // getNodeGraph — nodes AND edges mapping
  // =========================================================================
  describe('getNodeGraph', () => {
    it('maps nodes and edges from backend format to frontend format', async () => {
      const backendGraph = {
        nodes: [
          {
            id: 'n1',
            type: 'task',
            name: 'Task Alpha',
            description: 'Does alpha things',
            status: 'active',
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-02-01T00:00:00Z',
          },
          {
            id: 'n2',
            type: 'document',
            name: 'Doc Beta',
          },
        ],
        edges: [
          {
            source_node: { id: 'n1' },
            target_node: { id: 'n2' },
            relationship_type: 'uses',
            metadata: { purpose: 'enrichment' },
          },
          {
            source_node: { id: 'n2' },
            target_node: { id: 'n1' },
            relationship_type: 'generates',
            // metadata omitted
          },
        ],
      };

      mockGet.mockResolvedValueOnce({
        data: { data: backendGraph, meta: { request_id: 'test' } },
      });

      const result = await knowledgeApi.getNodeGraph('n1', 3);

      // Node mapping: name -> label, nested data object
      expect(result.nodes).toHaveLength(2);
      expect(result.nodes[0].id).toBe('n1');
      expect(result.nodes[0].label).toBe('Task Alpha');
      expect(result.nodes[0].data.name).toBe('Task Alpha');
      expect(result.nodes[0].data.description).toBe('Does alpha things');
      expect(result.nodes[0].data.created_by).toBe('');

      // Second node: missing description defaults to ''
      expect(result.nodes[1].label).toBe('Doc Beta');
      expect(result.nodes[1].data.description).toBe('');

      // Edge mapping: source_node.id -> source, target_node.id -> target
      expect(result.edges).toHaveLength(2);
      expect(result.edges[0].source).toBe('n1');
      expect(result.edges[0].target).toBe('n2');
      expect(result.edges[0].type).toBe('uses');
      expect(result.edges[0].data).toEqual({ purpose: 'enrichment' });

      // Missing metadata defaults to {}
      expect(result.edges[1].source).toBe('n2');
      expect(result.edges[1].target).toBe('n1');
      expect(result.edges[1].type).toBe('generates');
      expect(result.edges[1].data).toEqual({});

      expect(mockGet).toHaveBeenCalledWith('/kdg/nodes/n1/graph', { params: { depth: 3 } });
    });
  });

  // =========================================================================
  // updateDirective — PATCH endpoint
  // =========================================================================
  describe('updateDirective', () => {
    it('sends PATCH to /knowledge-units/directives/:id', async () => {
      const updateData = { name: 'Updated Directive', content: 'New content' };
      const responseData = { id: TEST_ID, ...updateData };

      mockPatch.mockResolvedValueOnce({
        data: { data: responseData, meta: { request_id: 'test' } },
      });

      const result = await knowledgeApi.updateDirective(TEST_ID, updateData);

      expect(mockPatch).toHaveBeenCalledWith(`/knowledge-units/directives/${TEST_ID}`, updateData);
      expect(result).toEqual(responseData);
    });
  });

  // =========================================================================
  // deleteDocument — DELETE endpoint
  // =========================================================================
  describe('deleteDocument', () => {
    it('sends DELETE to /knowledge-units/documents/:id', async () => {
      mockDelete.mockResolvedValueOnce({ data: {} });

      await knowledgeApi.deleteDocument(TEST_ID);

      expect(mockDelete).toHaveBeenCalledWith(`/knowledge-units/documents/${TEST_ID}`);
    });
  });
});
