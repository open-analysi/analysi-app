import { KdgGraph, KdgNode } from '../types/kdg';
import {
  DirectiveKU,
  DocumentKU,
  KnowledgeModule,
  KnowledgeUnit,
  KnowledgeUnitQueryParams,
  TableKU,
  Task,
  ToolKU,
} from '../types/knowledge';

import {
  withApi,
  fetchOne,
  mutateOne,
  apiDelete,
  backendApiClient,
  type SifnosEnvelope,
} from './apiClient';

// Knowledge Units
export const getKnowledgeUnits = (
  params: KnowledgeUnitQueryParams = {}
): Promise<{
  knowledge_units: KnowledgeUnit[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  execution_time: number;
}> =>
  withApi('getKnowledgeUnits', 'fetching knowledge units', async () => {
    interface RawKU extends Record<string, unknown> {
      id: string;
      ku_type?: string;
      created_by?: string;
    }

    const response = await backendApiClient.get<SifnosEnvelope<RawKU[]>>('/knowledge-units', {
      params,
    });
    const { data: rawKUs, meta } = response.data;

    // Map backend fields to UI expected fields
    // Filter out any null/undefined entries first
    const mappedKUs = rawKUs
      .filter((ku) => ku != undefined && ku.id != undefined)
      .map((ku) => ({
        ...ku,
        type: ku.ku_type as string,
        status: 'active',
        version: '1.0.0',
        created_by: ku.created_by || 'System',
        visibility: 'public',
        tags: (ku.categories as string[]) || [],
        source_document_id: undefined,
        editable: true,
        usage_stats: { count: 0, last_used: undefined },
        dependencies: [],
        embedding_vector: undefined,
      }));

    const total = meta.total ?? mappedKUs.length;
    const limit = meta.limit ?? mappedKUs.length;
    const offset = meta.offset ?? 0;
    return {
      knowledge_units: mappedKUs as unknown as KnowledgeUnit[],
      total,
      page: offset ? Math.floor(offset / (limit || 50)) + 1 : 1,
      page_size: limit,
      total_pages: limit ? Math.ceil(total / limit) : 1,
      execution_time: 0,
    };
  });

export const getKnowledgeUnit = (id: string): Promise<KnowledgeUnit> =>
  fetchOne<KnowledgeUnit>(`/knowledge-units/${id}`);

// Directives
export const getDirectives = (params: KnowledgeUnitQueryParams = {}): Promise<DirectiveKU[]> =>
  fetchOne<DirectiveKU[]>('/knowledge-units/directives', { params });

export const getDirective = (id: string): Promise<DirectiveKU> =>
  withApi('getDirective', 'fetching directive', async () => {
    const directive = await fetchOne<DirectiveKU>(`/knowledge-units/directives/${id}`);
    // Backend returns ku_type; map to type for UI compatibility
    const raw = directive as DirectiveKU & { ku_type?: string };
    if (raw.ku_type && !directive.type) {
      directive.type = raw.ku_type as DirectiveKU['type'];
    }
    return directive;
  });

// Tables
export const getTables = (params: KnowledgeUnitQueryParams = {}): Promise<TableKU[]> =>
  fetchOne<TableKU[]>('/knowledge-units/tables', { params });

export const getTable = (id: string): Promise<TableKU> =>
  withApi('getTable', 'fetching table', async () => {
    const table = await fetchOne<TableKU>(`/knowledge-units/tables/${id}`);
    const raw = table as TableKU & { ku_type?: string };
    if (raw.ku_type && !table.type) {
      table.type = raw.ku_type as TableKU['type'];
    }
    return table;
  });

// Tools
export const getTools = (params: KnowledgeUnitQueryParams = {}): Promise<ToolKU[]> =>
  fetchOne<ToolKU[]>('/knowledge-units/tools', { params });

// Documents
export const getDocuments = (params: KnowledgeUnitQueryParams = {}): Promise<DocumentKU[]> =>
  fetchOne<DocumentKU[]>('/knowledge-units/documents', { params });

export const getDocument = (id: string): Promise<DocumentKU> =>
  withApi('getDocument', 'fetching document', async () => {
    const doc = await fetchOne<DocumentKU>(`/knowledge-units/documents/${id}`);
    const raw = doc as DocumentKU & { ku_type?: string };
    if (raw.ku_type && !doc.type) {
      doc.type = raw.ku_type as DocumentKU['type'];
    }
    return doc;
  });

// Knowledge Unit Dependencies
export const getKnowledgeUnitDependencies = (id: string): Promise<KnowledgeUnit[]> =>
  fetchOne<KnowledgeUnit[]>(`/knowledge-units/${id}/dependencies`);

// Update methods for Knowledge Units
export const updateDirective = (id: string, data: Partial<DirectiveKU>): Promise<DirectiveKU> =>
  mutateOne<DirectiveKU>('patch', `/knowledge-units/directives/${id}`, data);

export const updateTable = (id: string, data: Partial<TableKU>): Promise<TableKU> =>
  mutateOne<TableKU>('put', `/knowledge-units/tables/${id}`, data);

export const updateDocument = (id: string, data: Partial<DocumentKU>): Promise<DocumentKU> =>
  mutateOne<DocumentKU>('put', `/knowledge-units/documents/${id}`, data);

// Delete methods for Knowledge Units
export const deleteDirective = (id: string): Promise<void> =>
  apiDelete(`/knowledge-units/directives/${id}`);

export const deleteTable = (id: string): Promise<void> =>
  apiDelete(`/knowledge-units/tables/${id}`);

export const deleteDocument = (id: string): Promise<void> =>
  apiDelete(`/knowledge-units/documents/${id}`);

// Knowledge Unit Tasks
export const getKnowledgeUnitTasks = (id: string): Promise<Task[]> =>
  fetchOne<Task[]>(`/knowledge-units/${id}/tasks`);

// Knowledge Modules
export const getKnowledgeModules = (
  params: { search?: string; sort?: string; order?: string; limit?: number; offset?: number } = {}
): Promise<KnowledgeModule[]> => fetchOne<KnowledgeModule[]>('/knowledge-modules/', { params });

// Knowledge Graph
export const getKnowledgeGraph = (
  params: {
    include_tasks?: boolean;
    include_knowledge_units?: boolean;
    include_tools?: boolean;
    include_skills?: boolean;
    depth?: number;
    max_nodes?: number;
  } = {}
): Promise<KdgGraph> => fetchOne<KdgGraph>('/kdg/graph', { params });

// List/search KDG nodes (for node selector)
export const listKdgNodes = (
  params: {
    type?: string;
    q?: string;
    limit?: number;
    offset?: number;
  } = {}
): Promise<KdgNode[]> =>
  withApi('listKdgNodes', 'listing KDG nodes', async () => {
    interface RawNode {
      id: string;
      type: string;
      name: string;
      description?: string;
      status?: string;
      created_at?: string;
      updated_at?: string;
      created_by?: string;
    }

    const response = await backendApiClient.get<SifnosEnvelope<RawNode[]>>('/kdg/nodes', {
      params,
    });
    const rawNodes = response.data.data;
    return rawNodes.map((node) => ({
      id: node.id,
      type: node.type,
      label: node.name,
      data: {
        name: node.name,
        description: node.description || '',
        status: node.status,
        created_at: node.created_at,
        updated_at: node.updated_at,
        created_by: node.created_by || '',
      },
    })) as KdgNode[];
  });

// Get subgraph around a specific node
export const getNodeGraph = (nodeId: string, depth: number = 2): Promise<KdgGraph> =>
  withApi('getNodeGraph', 'fetching node subgraph', async () => {
    interface RawGraphNode {
      id: string;
      type: string;
      name: string;
      description?: string;
      status?: string;
      created_at?: string;
      updated_at?: string;
      created_by?: string;
    }
    interface RawGraphEdge {
      source_node: { id: string };
      target_node: { id: string };
      relationship_type: string;
      metadata?: Record<string, unknown>;
    }
    interface RawGraph {
      nodes: RawGraphNode[];
      edges: RawGraphEdge[];
    }

    const response = await backendApiClient.get<SifnosEnvelope<RawGraph>>(
      `/kdg/nodes/${nodeId}/graph`,
      {
        params: { depth },
      }
    );
    const graphData = response.data.data;
    const nodes = graphData.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      label: node.name,
      data: {
        name: node.name,
        description: node.description || '',
        status: node.status,
        created_at: node.created_at,
        updated_at: node.updated_at,
        created_by: node.created_by || '',
      },
    }));
    const edges = graphData.edges.map((edge) => ({
      source: edge.source_node.id,
      target: edge.target_node.id,
      type: edge.relationship_type,
      data: edge.metadata || {},
    }));
    return { nodes, edges } as KdgGraph;
  });

export const getKnowledgeModule = (id: string): Promise<KnowledgeModule> =>
  fetchOne<KnowledgeModule>(`/knowledge-modules/${id}`);

// Document Creation
export const createDocument = (body: {
  name: string;
  content: string;
  doc_format?: string;
  cy_name?: string;
}): Promise<{ id: string }> =>
  mutateOne<{ id: string }>('post', '/knowledge-units/documents', body);
