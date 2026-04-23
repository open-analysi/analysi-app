import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';

import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { useSearchParams } from 'react-router';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { KdgNode, KdgGraph, getNodeConfig } from '../../types/kdg';

import GraphFilters from './graph/GraphFilters';
import GraphLegend from './graph/GraphLegend';
import KnowledgeGraphVisualization from './graph/KnowledgeGraphVisualization';

interface KnowledgeGraphProps {
  hideTitle?: boolean;
}

export const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ hideTitle = false }) => {
  const [loading, setLoading] = useState(false);
  const [originalGraphData, setOriginalGraphData] = useState<KdgGraph>();
  const [filteredGraphData, setFilteredGraphData] = useState<KdgGraph>();
  const { runSafe } = useErrorHandler('KnowledgeGraph');
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedNodeData, setSelectedNodeData] = useState<KdgNode>();
  const [showLegend, setShowLegend] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [layoutAlgorithm, setLayoutAlgorithm] = useState('concentric');

  // Node-centric exploration state — persisted in URL for anchor support
  const centerNodeId = searchParams.get('node') || null;
  const depth = Number(searchParams.get('depth') || '2');

  const setCenterNodeId = useCallback(
    (id: string | null) => {
      setSearchParams(
        (prev) => {
          if (id) {
            prev.set('node', id);
          } else {
            prev.delete('node');
          }
          return prev;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const setDepth = useCallback(
    (d: number) => {
      setSearchParams(
        (prev) => {
          if (d === 2) {
            prev.delete('depth');
          } else {
            prev.set('depth', String(d));
          }
          return prev;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<KdgNode[]>([]);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  // Extract unique node and edge types from the graph data
  const { nodeTypes, edgeTypes } = useMemo(() => {
    if (!originalGraphData) return { nodeTypes: [], edgeTypes: [] };

    const nodeTypes = [...new Set(originalGraphData.nodes.map((node) => node.type))];
    const edgeTypes = [...new Set(originalGraphData.edges.map((edge) => edge.type))];

    return { nodeTypes, edgeTypes };
  }, [originalGraphData]);

  // Filter states
  const [selectedNodeTypes, setSelectedNodeTypes] = useState<string[]>(nodeTypes);
  const [selectedEdgeTypes, setSelectedEdgeTypes] = useState<string[]>(edgeTypes);

  // Update filters when graph data changes
  useEffect(() => {
    setSelectedNodeTypes(nodeTypes);
    setSelectedEdgeTypes(edgeTypes);
  }, [nodeTypes, edgeTypes]);

  // Apply filters to the graph data
  useEffect(() => {
    if (!originalGraphData) return;

    // Filter nodes by type
    const filteredNodes = originalGraphData.nodes.filter((node) =>
      selectedNodeTypes.includes(node.type)
    );

    // Get the IDs of the filtered nodes
    const filteredNodeIds = new Set(filteredNodes.map((node) => node.id));

    // Filter edges that connect filtered nodes and match selected edge types
    const filteredEdges = originalGraphData.edges.filter(
      (edge) =>
        selectedEdgeTypes.includes(edge.type) &&
        filteredNodeIds.has(edge.source) &&
        filteredNodeIds.has(edge.target)
    );

    setFilteredGraphData({
      nodes: filteredNodes,
      edges: filteredEdges,
    });
  }, [originalGraphData, selectedNodeTypes, selectedEdgeTypes]);

  // Search for nodes with debounce
  // Skip search if we already have a center node (query was set programmatically)
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      setShowSearchResults(false);
      return;
    }

    // Don't search if we already have a center node selected
    // (the search query was set programmatically from double-click or selection)
    if (centerNodeId) {
      setShowSearchResults(false);
      return;
    }

    const searchTimer = setTimeout(() => {
      void (async () => {
        setIsSearching(true);
        try {
          const [results, error] = await runSafe(
            backendApi.listKdgNodes({ q: searchQuery, limit: 20 }),
            'searchNodes',
            { action: 'searching nodes' }
          );
          if (results && !error) {
            setSearchResults(results);
            setShowSearchResults(true);
          }
        } finally {
          setIsSearching(false);
        }
      })();
    }, 300);

    return () => clearTimeout(searchTimer);
  }, [searchQuery, runSafe, centerNodeId]);

  // Close search results when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(event.target as Node)
      ) {
        setShowSearchResults(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Fetch graph data - node-centric only (no global graph dump)
  useEffect(() => {
    const fetchGraphData = async () => {
      if (!centerNodeId) return;

      setLoading(true);

      try {
        const [response, error] = await runSafe(
          backendApi.getNodeGraph(centerNodeId, depth),
          'fetchNodeGraph',
          { action: 'fetching node subgraph', entityId: centerNodeId }
        );

        if (error) {
          console.error('Knowledge graph fetch error:', String(error));
          return;
        }

        if (response) {
          setOriginalGraphData(response);
          setFilteredGraphData(response);
        }
      } catch (error) {
        console.error('Failed to load knowledge graph data', error);
      } finally {
        setLoading(false);
      }
    };

    void fetchGraphData();
  }, [runSafe, centerNodeId, depth]);

  // Sync search query from URL-loaded center node
  useEffect(() => {
    if (centerNodeId && originalGraphData && !searchQuery) {
      const node = originalGraphData.nodes.find((n) => n.id === centerNodeId);
      if (node) {
        setSearchQuery(node.label || node.data.name);
      }
    }
  }, [centerNodeId, originalGraphData, searchQuery]);

  // Handle selecting a node from search results
  const handleSelectCenterNode = useCallback(
    (node: KdgNode) => {
      setCenterNodeId(node.id);
      setSearchQuery(node.label || node.data.name);
      setShowSearchResults(false);
      setSelectedNodeData(node);
    },
    [setCenterNodeId]
  );

  // Handle clearing the center node
  const handleClearCenterNode = useCallback(() => {
    setSearchParams(
      (prev) => {
        prev.delete('node');
        prev.delete('depth');
        return prev;
      },
      { replace: true }
    );
    setSearchQuery('');
    setSelectedNodeData(undefined);
  }, [setSearchParams]);

  // Handle clicking on a node in the graph - navigate to it
  const handleNodeSelect = useCallback(
    (nodeId: string) => {
      if (nodeId === '' || !nodeId) {
        setSelectedNodeData(undefined);
        return;
      }

      if (originalGraphData) {
        const node = originalGraphData.nodes.find((n) => n.id === nodeId);
        if (node) {
          setSelectedNodeData(node);
        } else {
          setSelectedNodeData(undefined);
        }
      }
    },
    [originalGraphData]
  );

  // Handle double-click to navigate to a node
  const handleNodeDoubleClick = useCallback(
    (nodeId: string) => {
      if (nodeId) {
        setCenterNodeId(nodeId);
        // Update search field with the node name
        if (originalGraphData) {
          const node = originalGraphData.nodes.find((n) => n.id === nodeId);
          if (node) {
            setSearchQuery(node.label || node.data.name);
          }
        }
      }
    },
    [originalGraphData, setCenterNodeId]
  );

  const toggleLegend = () => setShowLegend((prev) => !prev);
  const toggleFilters = () => setShowFilters((prev) => !prev);

  // Center node info for display
  const centerNode = useMemo(() => {
    if (!centerNodeId || !originalGraphData) return null;
    return originalGraphData.nodes.find((n) => n.id === centerNodeId);
  }, [centerNodeId, originalGraphData]);

  return (
    <div className="flex flex-col h-[calc(100vh-12rem)]">
      {/* Header with controls */}
      <div className="mb-4 flex justify-between items-start gap-4">
        {!hideTitle && (
          <div className="shrink-0">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
              Knowledge Dependency Graph
            </h2>
            {centerNodeId ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Exploring {depth} hop{depth === 1 ? '' : 's'} from center node
              </p>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Select a node to explore its relationships
              </p>
            )}
          </div>
        )}

        {/* Node Selector and Controls */}
        <div className="flex items-center gap-4 flex-wrap">
          {/* Node Search */}
          <div ref={searchContainerRef} className="relative">
            <div className="flex items-center">
              <div className="relative">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onFocus={() => searchResults.length > 0 && setShowSearchResults(true)}
                  placeholder="Search for a node..."
                  className="pl-9 pr-8 py-1.5 w-64 text-sm bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md border border-gray-300 dark:border-gray-600 focus:outline-hidden focus:ring-2 focus:ring-primary focus:border-transparent"
                />
                {(searchQuery || centerNodeId) && (
                  <button
                    onClick={handleClearCenterNode}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                  >
                    <XMarkIcon className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>

            {/* Search Results Dropdown */}
            {showSearchResults && searchResults.length > 0 && (
              <div className="absolute z-50 mt-1 w-80 max-h-64 overflow-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg">
                {searchResults.map((node) => {
                  const config = getNodeConfig(node.type);
                  return (
                    <button
                      key={node.id}
                      onClick={() => handleSelectCenterNode(node)}
                      className="w-full px-3 py-2 text-left hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2 border-b border-gray-100 dark:border-gray-700 last:border-b-0"
                    >
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: config.color }}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                          {node.label || node.data.name}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
                          <span>{config.label}</span>
                          {node.data.description && (
                            <>
                              <span>•</span>
                              <span className="truncate">{node.data.description}</span>
                            </>
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            {/* Loading indicator */}
            {isSearching && (
              <div className="absolute z-50 mt-1 w-80 p-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg flex items-center justify-center">
                <div className="animate-spin rounded-full h-5 w-5 border-t-2 border-b-2 border-primary"></div>
                <span className="ml-2 text-sm text-gray-500">Searching...</span>
              </div>
            )}
          </div>

          {/* Depth Control */}
          <div className="flex items-center gap-2">
            <label htmlFor="depth-select" className="text-sm text-gray-600 dark:text-gray-400">
              Depth:
            </label>
            <select
              id="depth-select"
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
              disabled={!centerNodeId}
              className="px-3 py-1 text-sm bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors border border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <option value={1}>1 hop</option>
              <option value={2}>2 hops</option>
              <option value={3}>3 hops</option>
              <option value={4}>4 hops</option>
              <option value={5}>5 hops</option>
            </select>
          </div>

          {/* Layout Algorithm Dropdown */}
          <div className="flex items-center gap-2">
            <label htmlFor="layout-select" className="text-sm text-gray-600 dark:text-gray-400">
              Layout:
            </label>
            <select
              id="layout-select"
              value={layoutAlgorithm}
              onChange={(e) => setLayoutAlgorithm(e.target.value)}
              className="px-3 py-1 text-sm bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors border border-gray-300 dark:border-gray-600"
            >
              <option value="dagre">Dagre (Hierarchical)</option>
              <option value="breadthfirst">Breadth First</option>
              <option value="circle">Circle</option>
              <option value="concentric">Concentric</option>
              <option value="cose">CoSE (Force-Directed)</option>
              <option value="grid">Grid</option>
              <option value="random">Random</option>
              <option value="preset">Preset</option>
            </select>
          </div>

          <button
            onClick={toggleLegend}
            className="px-3 py-1 text-sm bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            {showLegend ? 'Hide Legend' : 'Show Legend'}
          </button>
          <button
            onClick={toggleFilters}
            className="px-3 py-1 text-sm bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-md hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            {showFilters ? 'Hide Filters' : 'Show Filters'}
          </button>
        </div>
      </div>

      {/* Center Node Info Bar */}
      {centerNode && (
        <div className="mb-2 px-3 py-2 bg-cyan-50 dark:bg-cyan-900/30 border border-cyan-300 dark:border-cyan-700 rounded-lg flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className="w-3 h-3 rounded-full ring-2 ring-cyan-400 ring-offset-1 ring-offset-cyan-50 dark:ring-offset-gray-900"
              style={{ backgroundColor: getNodeConfig(centerNode.type).color }}
            />
            <span className="text-sm font-medium text-cyan-900 dark:text-cyan-100">
              Centered on: {centerNode.label || centerNode.data.name}
            </span>
            <span className="text-xs text-cyan-600 dark:text-cyan-400">
              ({getNodeConfig(centerNode.type).label})
            </span>
          </div>
          <div className="text-xs text-cyan-600 dark:text-cyan-400">
            Double-click any node to re-center • {originalGraphData?.nodes.length || 0} nodes,{' '}
            {originalGraphData?.edges.length || 0} edges
          </div>
        </div>
      )}

      <div className="flex flex-1 h-full">
        {/* Filters panel */}
        {showFilters && (
          <div className="w-48 mr-2">
            <GraphFilters
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              selectedNodeTypes={selectedNodeTypes}
              selectedEdgeTypes={selectedEdgeTypes}
              onNodeTypeFilterChange={setSelectedNodeTypes}
              onEdgeTypeFilterChange={setSelectedEdgeTypes}
            />
          </div>
        )}

        {/* Main graph area */}
        <div className="flex-1 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden flex flex-col">
          {/* Top Legend */}
          {showLegend && (
            <div className="border-b border-gray-200 dark:border-gray-700 p-2 bg-white dark:bg-gray-800">
              <GraphLegend className="mx-auto max-w-3xl" />
            </div>
          )}

          {/* Graph visualization */}
          <div className="flex-1">
            {loading && (
              <div className="flex items-center justify-center w-full h-full">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
              </div>
            )}
            {!loading && filteredGraphData && (
              <div className="w-full h-full">
                <KnowledgeGraphVisualization
                  data={filteredGraphData}
                  onNodeSelect={handleNodeSelect}
                  onNodeDoubleClick={handleNodeDoubleClick}
                  selectedNodeData={selectedNodeData}
                  layoutAlgorithm={layoutAlgorithm}
                  centerNodeId={centerNodeId || undefined}
                />
              </div>
            )}
            {!loading && !filteredGraphData && (
              <div className="flex flex-col items-center justify-center w-full h-full gap-3">
                <MagnifyingGlassIcon className="w-12 h-12 text-gray-300 dark:text-gray-600" />
                <p className="text-gray-500 dark:text-gray-400 text-sm font-medium">
                  Search for a node to begin exploring
                </p>
                <p className="text-gray-400 dark:text-gray-500 text-xs">
                  Type a task, skill, or document name in the search bar above
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default KnowledgeGraph;
