// Common types for all Knowledge Units
export type KnowledgeUnitType = 'directive' | 'table' | 'tool' | 'document';
export type KnowledgeUnitStatus = 'active' | 'deprecated' | 'experimental';

export interface KnowledgeUnitBase {
  id: string;
  name: string;
  description: string;
  type: KnowledgeUnitType;
  created_by: string;
  updated_by?: string;
  visibility: string;
  tags: string[];
  source_document_id: string | null;
  version: string;
  status: KnowledgeUnitStatus;
  editable: boolean;
  created_at: string;
  updated_at: string;
  usage_stats: {
    count: number;
    last_used: string | null;
  };
  dependencies: string[];
  embedding_vector: number[] | undefined;
}

// Directive-specific fields
export interface DirectiveKU extends KnowledgeUnitBase {
  type: 'directive';
  content: string;
  referenced_tables: { id: string; name: string }[];
  referenced_documents: { id: string; name: string }[];
}

// Type alias for table cell values
export type TableCellValue = string | number | boolean;

// Backend rows-format content: { rows: [{col1: val, col2: val}, ...] }
export interface TableRowContent {
  rows: Record<string, TableCellValue>[];
}

// Table column schema definition
export interface ColumnSchema {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'date' | 'datetime' | 'json';
  description?: string;
  required?: boolean;
  unique?: boolean;
  default?: TableCellValue;
  format?: string; // For dates, numbers, etc.
  enum?: TableCellValue[]; // For restricted values
}

// Table schema definition
export interface TableSchema {
  columns: ColumnSchema[];
  primaryKey?: string | string[];
  description?: string;
  version?: string;
}

// Table-specific fields
export interface TableKU extends KnowledgeUnitBase {
  type: 'table';
  data_type: 'tabular' | 'vector-based';
  content: {
    data: TableCellValue[][];
    columns: string[];
  };
  schema?: TableSchema | Record<string, unknown>; // Support both structured and flexible schema
  row_count?: number;
  column_count?: number;
  embedding_metadata: Record<string, unknown> | undefined;
}

// Tool-specific fields
export interface ToolKU extends KnowledgeUnitBase {
  type: 'tool';
  mcp_endpoint: string;
  integration_id: string | null;
}

// Document-specific fields
export interface DocumentKU extends KnowledgeUnitBase {
  type: 'document';
  document_type: 'pdf' | 'markdown' | 'html' | 'plaintext';
  content: string;
  content_source: 'manual' | 'API' | 'integration';
  source_url: string | null;
  embedding_metadata: Record<string, unknown> | undefined;
  vectorized: boolean;
}

// Union type for all Knowledge Unit types
export type KnowledgeUnit = DirectiveKU | TableKU | ToolKU | DocumentKU;

// Task type — re-exported from generated types (backed by TaskResponse schema)
export type { Task } from './api';

// Knowledge Module type
export interface KnowledgeModule {
  id: string;
  name: string;
  description: string;
  owner: string;
  version: string;
  created_at: string;
  updated_at: string;
}

// Task Execution Run
export interface TaskExecutionRun {
  id: string;
  task_id: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  duration: number;
  started_at: string;
  completed_at: string;
  status: 'running' | 'completed' | 'failed' | 'stopped';
  feedback: {
    thumbs_up: boolean | null;
    comments: string | null;
  };
}

// API response metadata (Project Sifnos — unified envelope)
// Single-item meta: { request_id }
// List meta: { total, request_id, limit, offset, has_next }
export interface ApiMeta {
  request_id: string;
  total?: number;
  limit?: number;
  offset?: number;
  has_next?: boolean;
}

// Generic API response — matches backend's {data, meta} envelope (Project Sifnos)
export interface ApiResponse<T> {
  data: T;
  meta: ApiMeta;
}

// Convenience alias for list responses
export type ApiListResponse<T> = ApiResponse<T[]>;

// Query parameters for Knowledge Unit list API
export interface KnowledgeUnitQueryParams {
  type?: KnowledgeUnitType;
  status?: KnowledgeUnitStatus;
  search?: string;
  sort?: string;
  order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
  task_id?: string;
  categories?: string[];
}

// Query parameters for Task list API
export interface TaskQueryParams {
  function?: string;
  scope?: string;
  status?: 'active' | 'deprecated' | 'experimental';
  search?: string;
  sort?: string;
  order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
  ku_id?: string;
  km_id?: string;
  categories?: string[];
}
