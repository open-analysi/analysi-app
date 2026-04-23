/**
 * Knowledge Dependency Graph (KDG) Types and Configuration
 *
 * This file is the single source of truth for all KDG node types, edge types,
 * and their visual configurations. All KDG-related components should import
 * from this file to ensure consistency.
 *
 * Node Type Hierarchy:
 * - Task: AI agent tasks with Cy script execution
 * - Knowledge Units (KUs): document, table, tool, index
 * - Knowledge Module: Groups KUs together
 * - Skill: Uses knowledge modules to provide capabilities
 *
 * Edge Types define relationships between nodes in the knowledge graph.
 */

// ============================================================================
// NODE TYPES
// ============================================================================

/**
 * All valid node types in the Knowledge Dependency Graph.
 *
 * Note: 'directive' is NOT a node type - it's a field on Task that stores
 * LLM system prompts.
 */
export const KDG_NODE_TYPES = [
  'task',
  'document',
  'table',
  'index',
  'tool',
  'knowledge_module',
  'skill',
] as const;

export type KdgNodeType = (typeof KDG_NODE_TYPES)[number];

// ============================================================================
// EDGE TYPES
// ============================================================================

/**
 * All valid edge/relationship types in the Knowledge Dependency Graph.
 */
export const KDG_EDGE_TYPES = [
  'uses', // Source uses/consumes target
  'calls', // Task calls another task
  'generates', // Source generates/produces target
  'updates', // Source modifies/updates target
  'transforms_into', // Source transforms into target
  'summarizes_into', // Source summarizes into target
  'indexes_into', // Source is indexed into target
  'derived_from', // Source is derived from target
  'enriches', // Source enriches/enhances target
  'contains', // Module/Skill contains child (KM contains KU, Skill contains KM)
  'includes', // Module includes another module (content inheritance)
  'depends_on', // Module depends on another module (capability dependency)
  'references', // Module references a document/KU
  'staged_for', // Document staged for future extraction into skill
] as const;

export type KdgEdgeType = (typeof KDG_EDGE_TYPES)[number];

// ============================================================================
// NODE TYPE CONFIGURATION
// ============================================================================

export interface NodeTypeConfig {
  /** Display label for the node type */
  label: string;
  /** Primary color (hex) */
  color: string;
  /** Gradient start color (hex) */
  gradientFrom: string;
  /** Gradient end color (hex) */
  gradientTo: string;
  /** Heroicon component name (24/solid) */
  icon: string;
  /** Emoji for simple legends */
  emoji: string;
  /** Description of this node type */
  description: string;
}

export const NODE_TYPE_CONFIG: Record<KdgNodeType, NodeTypeConfig> = {
  task: {
    label: 'Task',
    color: '#3b82f6',
    gradientFrom: '#3b82f6',
    gradientTo: '#1d4ed8',
    icon: 'Cog6ToothIcon',
    emoji: '⚙️',
    description: 'AI agent task with Cy script execution',
  },
  document: {
    label: 'Document',
    color: '#a855f7',
    gradientFrom: '#a855f7',
    gradientTo: '#7e22ce',
    icon: 'DocumentTextIcon',
    emoji: '📄',
    description: 'Unstructured text content (PDF, Markdown, HTML)',
  },
  table: {
    label: 'Table',
    color: '#f97316',
    gradientFrom: '#f97316',
    gradientTo: '#c2410c',
    icon: 'TableCellsIcon',
    emoji: '📊',
    description: 'Structured tabular data',
  },
  index: {
    label: 'Index',
    color: '#ec4899',
    gradientFrom: '#ec4899',
    gradientTo: '#be185d',
    icon: 'MagnifyingGlassIcon',
    emoji: '🔍',
    description: 'Semantic search index (vector/fulltext/hybrid)',
  },
  tool: {
    label: 'Tool',
    color: '#ef4444',
    gradientFrom: '#ef4444',
    gradientTo: '#b91c1c',
    icon: 'WrenchScrewdriverIcon',
    emoji: '🔧',
    description: 'MCP or native tool integration',
  },
  knowledge_module: {
    label: 'Knowledge Module',
    color: '#6366f1',
    gradientFrom: '#6366f1',
    gradientTo: '#4338ca',
    icon: 'CubeIcon',
    emoji: '📦',
    description: 'Groups knowledge units together',
  },
  skill: {
    label: 'Skill',
    color: '#14b8a6',
    gradientFrom: '#14b8a6',
    gradientTo: '#0d9488',
    icon: 'SparklesIcon',
    emoji: '✨',
    description: 'Reusable capability using knowledge modules',
  },
};

// ============================================================================
// EDGE TYPE CONFIGURATION
// ============================================================================

export interface EdgeTypeConfig {
  /** Display label for the edge type */
  label: string;
  /** Edge color (hex) */
  color: string;
  /** Line style */
  style: 'solid' | 'dashed' | 'dotted';
  /** Line width in pixels */
  width: number;
  /** Description of this relationship */
  description: string;
}

export const EDGE_TYPE_CONFIG: Record<KdgEdgeType, EdgeTypeConfig> = {
  uses: {
    label: 'Uses',
    color: '#60a5fa',
    style: 'solid',
    width: 2,
    description: 'Source uses or consumes the target',
  },
  calls: {
    label: 'Calls',
    color: '#a78bfa',
    style: 'solid',
    width: 2,
    description: 'Task calls another task',
  },
  generates: {
    label: 'Generates',
    color: '#34d399',
    style: 'solid',
    width: 2,
    description: 'Source generates or produces the target',
  },
  updates: {
    label: 'Updates',
    color: '#fbbf24',
    style: 'solid',
    width: 2,
    description: 'Source modifies or updates the target',
  },
  transforms_into: {
    label: 'Transforms Into',
    color: '#f472b6',
    style: 'dashed',
    width: 2,
    description: 'Source transforms into the target',
  },
  summarizes_into: {
    label: 'Summarizes Into',
    color: '#c084fc',
    style: 'dashed',
    width: 2,
    description: 'Source summarizes into the target',
  },
  indexes_into: {
    label: 'Indexes Into',
    color: '#f472b6',
    style: 'dotted',
    width: 1,
    description: 'Source is indexed into the target index',
  },
  derived_from: {
    label: 'Derived From',
    color: '#94a3b8',
    style: 'dashed',
    width: 1,
    description: 'Source is derived from the target',
  },
  enriches: {
    label: 'Enriches',
    color: '#10b981',
    style: 'solid',
    width: 1,
    description: 'Source enriches or enhances the target',
  },
  contains: {
    label: 'Contains',
    color: '#8b5cf6',
    style: 'solid',
    width: 2,
    description: 'Module or skill contains the target (KM contains KU)',
  },
  includes: {
    label: 'Includes',
    color: '#6366f1',
    style: 'dashed',
    width: 2,
    description: 'Module includes another module (content inheritance)',
  },
  depends_on: {
    label: 'Depends On',
    color: '#f59e0b',
    style: 'dashed',
    width: 2,
    description: 'Module depends on another module (capability dependency)',
  },
  references: {
    label: 'References',
    color: '#64748b',
    style: 'dotted',
    width: 1,
    description: 'Module references a document or KU',
  },
  staged_for: {
    label: 'Staged For',
    color: '#fb923c',
    style: 'dotted',
    width: 1,
    description: 'Document staged for future extraction into skill',
  },
};

// ============================================================================
// DATA INTERFACES
// ============================================================================

/**
 * Node data structure as returned by the KDG API
 */
export interface KdgNode {
  id: string;
  type: KdgNodeType;
  label: string;
  data: {
    name: string;
    description: string;
    status?: string;
    created_at: string;
    updated_at: string;
    created_by: string;
    updated_by?: string;
    visibility?: string;
    function?: string;
    scopes?: string[];
    visible?: boolean;
    version?: string;
    // Task-specific fields
    directive?: string;
    script?: string;
    // Document-specific fields
    document_type?: string;
    content?: string;
    // Table-specific fields
    schema?: Record<string, unknown>;
    row_count?: number;
    // Index-specific fields
    index_type?: string;
    embedding_model?: string;
    // Tool-specific fields
    tool_type?: string;
    mcp_endpoint?: string;
  };
}

/**
 * Edge data structure as returned by the KDG API
 */
export interface KdgEdge {
  source: string;
  target: string;
  type: KdgEdgeType;
  data?: {
    is_required?: boolean;
    execution_order?: number;
    purpose?: string;
    namespace_path?: string;
    [key: string]: unknown;
  };
}

/**
 * Complete graph structure from the KDG API
 */
export interface KdgGraph {
  nodes: KdgNode[];
  edges: KdgEdge[];
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Get configuration for a node type, with fallback to 'task' for unknown types
 */
export const getNodeConfig = (type: string): NodeTypeConfig => {
  return NODE_TYPE_CONFIG[type as KdgNodeType] || NODE_TYPE_CONFIG.task;
};

/**
 * Get configuration for an edge type, with fallback for unknown types
 */
export const getEdgeConfig = (type: string): EdgeTypeConfig => {
  return (
    EDGE_TYPE_CONFIG[type as KdgEdgeType] || {
      label: type,
      color: '#6b7280',
      style: 'solid' as const,
      width: 1,
      description: 'Unknown relationship type',
    }
  );
};

/**
 * Check if a string is a valid node type
 */
export const isValidNodeType = (type: string): type is KdgNodeType => {
  return KDG_NODE_TYPES.includes(type as KdgNodeType);
};

/**
 * Check if a string is a valid edge type
 */
export const isValidEdgeType = (type: string): type is KdgEdgeType => {
  return KDG_EDGE_TYPES.includes(type as KdgEdgeType);
};

/**
 * Get all node types as an array (useful for filters)
 */
export const getAllNodeTypes = (): KdgNodeType[] => [...KDG_NODE_TYPES];

/**
 * Get all edge types as an array (useful for filters)
 */
export const getAllEdgeTypes = (): KdgEdgeType[] => [...KDG_EDGE_TYPES];

/**
 * Get node type label for display
 */
export const getNodeTypeLabel = (type: string): string => {
  return getNodeConfig(type).label;
};

/**
 * Get edge type label for display
 */
export const getEdgeTypeLabel = (type: string): string => {
  return getEdgeConfig(type).label;
};

// ============================================================================
// VISUALIZATION HELPERS
// ============================================================================

/**
 * Get Cytoscape.js compatible color for a node type
 */
export const getCytoscapeNodeColor = (type: string): string => {
  return getNodeConfig(type).color;
};

/**
 * Get Cytoscape.js compatible edge style
 */
export const getCytoscapeEdgeStyle = (
  type: string
): {
  lineColor: string;
  lineStyle: string;
  width: number;
} => {
  const config = getEdgeConfig(type);
  return {
    lineColor: config.color,
    lineStyle: config.style,
    width: config.width,
  };
};
