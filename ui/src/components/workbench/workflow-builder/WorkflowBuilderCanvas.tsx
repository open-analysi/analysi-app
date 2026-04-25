/**
 * WorkflowBuilderCanvas - Interactive canvas for workflow editing
 *
 * Structure-first approach: ELK handles all positioning automatically.
 * Users add nodes by clicking in palette, connect by selecting nodes.
 */
import React, { useCallback, useRef, useEffect, useState, useMemo } from 'react';

import './WorkflowBuilderCanvas.css';

import {
  MagnifyingGlassPlusIcon,
  MagnifyingGlassMinusIcon,
  ArrowPathIcon,
  TrashIcon,
  LinkIcon,
  ArrowRightIcon,
  ArrowsPointingInIcon,
  InboxStackIcon,
  CodeBracketIcon,
} from '@heroicons/react/24/outline';
import {
  Canvas,
  CanvasPosition,
  CanvasRef,
  Edge,
  EdgeData,
  NodeData,
  Node,
  MarkerArrow,
  ElkRoot,
  Port,
} from 'reaflow';

import { backendApi } from '../../../services/backendApi';
import { useWorkflowBuilderStore } from '../../../store/workflowBuilderStore';
import type { Task } from '../../../types/knowledge';
import type { CanvasNodeData, CanvasEdgeData } from '../../../types/workflowBuilder';

interface WorkflowBuilderCanvasProps {
  className?: string;
}

/**
 * Convert store nodes to Reaflow format
 * Simple 2-port system: WEST (input) and EAST (output)
 * @param nodes - Canvas nodes from store
 * @param taskDescriptions - Map of taskId to description for fallback lookup
 */
function nodesToReaflow(
  nodes: CanvasNodeData[],
  taskDescriptions: Map<string, string>
): NodeData[] {
  return nodes.map((node) => {
    // Check if this is a template node (transformation with nodeTemplateId)
    const isTemplateNode = node.kind === 'transformation' && node.nodeTemplateId;

    const nodeWidth = isTemplateNode ? 60 : 180;
    const nodeHeight = isTemplateNode ? 60 : 100;

    // Simple 2-port system for left-to-right flow
    const ports = [
      {
        id: `${node.id}-in`,
        side: 'WEST' as const,
        width: 10,
        height: 10,
      },
      {
        id: `${node.id}-out`,
        side: 'EAST' as const,
        width: 10,
        height: 10,
      },
    ];

    // Use stored description, or fall back to task description lookup
    const description =
      node.description || (node.taskId ? taskDescriptions.get(node.taskId) : undefined);

    return {
      id: node.id,
      text: node.text,
      width: nodeWidth,
      height: nodeHeight,
      ports,
      data: {
        kind: node.kind,
        taskId: node.taskId,
        nodeTemplateId: node.nodeTemplateId,
        foreachConfig: node.foreachConfig,
        description,
      },
    };
  });
}

/**
 * Convert store edges to Reaflow format
 * Simple: always connect from EAST (output) to WEST (input)
 */
function edgesToReaflow(edges: CanvasEdgeData[]): EdgeData[] {
  return edges.map((edge) => ({
    id: edge.id,
    from: edge.from,
    to: edge.to,
    fromPort: `${edge.from}-out`,
    toPort: `${edge.to}-in`,
    text: edge.text || '',
  }));
}

/**
 * Get node colors based on kind and state
 */
function getNodeColors(
  kind: string,
  isSelected: boolean,
  isConnectSource: boolean
): { bg: string; border: string; text: string } {
  // Helper to get border color based on selection/connection state
  const getBorderColor = (
    connectColor: string,
    selectedColor: string,
    defaultColor: string
  ): string => {
    if (isConnectSource) return connectColor;
    if (isSelected) return selectedColor;
    return defaultColor;
  };

  const baseColors = {
    task: {
      bg: isConnectSource ? 'rgba(59, 130, 246, 0.3)' : 'rgba(59, 130, 246, 0.15)',
      border: getBorderColor('#60a5fa', '#f472b6', '#3b82f6'),
      text: '#93c5fd',
    },
    transformation: {
      bg: isConnectSource ? 'rgba(16, 185, 129, 0.3)' : 'rgba(16, 185, 129, 0.15)',
      border: getBorderColor('#34d399', '#f472b6', '#10b981'),
      text: '#6ee7b7',
    },
    foreach: {
      bg: isConnectSource ? 'rgba(249, 115, 22, 0.3)' : 'rgba(249, 115, 22, 0.15)',
      border: getBorderColor('#fb923c', '#f472b6', '#f97316'),
      text: '#fdba74',
    },
  };

  return baseColors[kind as keyof typeof baseColors] || baseColors.task;
}

/**
 * Template type for transformation nodes
 */
type TemplateType = 'identity' | 'merge' | 'collect' | null;

/**
 * Determine template type from node name for transformation nodes
 * Matches the logic used in WorkflowNode.tsx for consistency
 */
function getTemplateType(nodeName: string): TemplateType {
  const lowerName = nodeName.toLowerCase();
  if (lowerName.includes('collect')) return 'collect';
  if (lowerName.includes('merge')) return 'merge';
  if (lowerName.includes('identity')) return 'identity';
  return null;
}

/**
 * Get icon for template node type
 * Matches the icons used in WorkflowNode.tsx for visual consistency
 */
function getTemplateIcon(templateType: TemplateType): React.ReactElement {
  const iconClass = 'w-6 h-6';
  switch (templateType) {
    case 'identity':
      return <ArrowRightIcon className={iconClass} />;
    case 'merge':
      return <ArrowsPointingInIcon className={iconClass} />;
    case 'collect':
      return <InboxStackIcon className={iconClass} />;
    default:
      return <CodeBracketIcon className={iconClass} />;
  }
}

/**
 * Get colors specific to template types
 * Matches the color scheme from WorkflowNode.tsx
 */
function getTemplateColors(templateType: TemplateType): {
  border: string;
  text: string;
} {
  switch (templateType) {
    case 'identity':
      return { border: '#06b6d4', text: '#22d3ee' }; // cyan
    case 'merge':
      return { border: '#a855f7', text: '#c084fc' }; // purple
    case 'collect':
      return { border: '#f59e0b', text: '#fbbf24' }; // amber/orange
    default:
      return { border: '#10b981', text: '#6ee7b7' }; // green (default transformation)
  }
}

export const WorkflowBuilderCanvas: React.FC<WorkflowBuilderCanvasProps> = ({ className = '' }) => {
  const store = useWorkflowBuilderStore();
  const canvasRef = useRef<CanvasRef | null>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 2000, height: 1500 });
  const [connectMode, _setConnectMode] = useState(false);
  const [connectSourceId, _setConnectSourceId] = useState<string | null>(null);

  // Refs to avoid stale closures in Reaflow callbacks.
  // Reaflow internally caches node onClick handlers and may not pick up
  // new function references when parent state changes. We update refs
  // synchronously in the setter wrappers (not useEffect) to eliminate
  // the race window between DOM update and ref update.
  const connectModeRef = useRef(false);
  const connectSourceIdRef = useRef<string | null>(null);
  const setConnectMode = useCallback((value: boolean) => {
    connectModeRef.current = value;
    _setConnectMode(value);
  }, []);
  const setConnectSourceId = useCallback((value: string | null) => {
    connectSourceIdRef.current = value;
    _setConnectSourceId(value);
  }, []);

  // Hover tooltip state
  const [hoveredNode, setHoveredNode] = useState<{
    id: string;
    name: string;
    description: string;
    x: number;
    y: number;
  } | null>(null);
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Task descriptions lookup for existing nodes that don't have descriptions stored
  const [tasks, setTasks] = useState<Task[]>([]);

  // Fetch tasks on mount to get descriptions
  useEffect(() => {
    const fetchTasks = async () => {
      try {
        const response = await backendApi.getTasks({ limit: 100 });

        setTasks(response.tasks);
      } catch (err) {
        console.error('Failed to fetch tasks for descriptions:', err);
      }
    };
    void fetchTasks();
  }, []);

  // Create task description lookup map
  const taskDescriptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const task of tasks) {
      if (task.description) {
        map.set(task.id, task.description);
      }
    }
    return map;
  }, [tasks]);

  // Convert store data to Reaflow format
  const reaflowNodes = nodesToReaflow(store.nodes, taskDescriptions);
  const reaflowEdges = edgesToReaflow(store.edges);

  // Handle layout changes - adjust canvas size based on content
  const onLayoutChange = useCallback((layout: ElkRoot) => {
    if (layout.width !== undefined && layout.height !== undefined) {
      const newWidth = Math.min(Math.max(layout.width + 400, 1200), 4000);
      const newHeight = Math.min(Math.max(layout.height + 300, 800), 3000);
      setCanvasSize((prev) => {
        if (prev.width !== newWidth || prev.height !== newHeight) {
          return { width: newWidth, height: newHeight };
        }
        return prev;
      });
    }
  }, []);

  // Handle node click for selection or connecting.
  // Reads connect state from refs because Reaflow caches the onClick handler
  // and may not pick up new function references after state changes.
  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, nodeData: NodeData) => {
      if (connectModeRef.current) {
        if (!connectSourceIdRef.current) {
          // First click - set source node
          setConnectSourceId(nodeData.id);
          store.setSelections([nodeData.id]);
        } else if (connectSourceIdRef.current !== nodeData.id) {
          // Second click - create edge and exit connect mode
          store.addEdge(connectSourceIdRef.current, nodeData.id);
          setConnectSourceId(null);
          setConnectMode(false);
          store.setSelections([]);
        }
      } else {
        store.setSelections([nodeData.id]);
      }
    },
    [store]
  );

  // Start connect mode with selected node as source
  const startConnectMode = useCallback(() => {
    const selectedNode = store.selections.find((id) => store.nodes.some((n) => n.id === id));
    if (selectedNode) {
      setConnectMode(true);
      setConnectSourceId(selectedNode);
    } else if (store.nodes.length > 0) {
      setConnectMode(true);
      setConnectSourceId(null);
    }
  }, [store.selections, store.nodes]);

  // Cancel connect mode
  const cancelConnectMode = useCallback(() => {
    setConnectMode(false);
    setConnectSourceId(null);
  }, []);

  // Handle delete button click
  const handleDeleteClick = useCallback(
    (nodeId: string, event: React.MouseEvent) => {
      event.stopPropagation();
      store.removeNode(nodeId);
    },
    [store]
  );

  // Handle connect button click - starts connect mode from this node
  const handleConnectClick = useCallback(
    (nodeId: string, event: React.MouseEvent) => {
      event.stopPropagation();
      setConnectMode(true);
      setConnectSourceId(nodeId);
      store.setSelections([nodeId]);
    },
    [store]
  );

  // Handle canvas click to clear selection or cancel connect mode.
  // Uses ref for the same stale closure reason as handleNodeClick.
  const handleCanvasClick = useCallback(() => {
    if (connectModeRef.current) {
      cancelConnectMode();
    } else {
      store.clearSelections();
    }
  }, [store, cancelConnectMode]);

  // Check if a link is valid before creating it
  const handleNodeLinkCheck = useCallback(
    (_event: React.MouseEvent, fromNode: NodeData, toNode: NodeData): boolean => {
      // Prevent self-loops
      if (fromNode.id === toNode.id) return false;

      // Prevent duplicate edges
      const exists = store.edges.some((e) => e.from === fromNode.id && e.to === toNode.id);
      if (exists) return false;

      return true;
    },
    [store.edges]
  );

  // Handle new edge creation (for both drag-to-connect and connect mode)
  const handleNodeLink = useCallback(
    (_event: React.MouseEvent, fromNode: NodeData, toNode: NodeData) => {
      store.addEdge(fromNode.id, toNode.id);
    },
    [store]
  );

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Don't handle if user is typing in an input
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }

      // Escape - cancel connect mode
      if (event.key === 'Escape') {
        if (connectMode) {
          event.preventDefault();
          cancelConnectMode();
        }
        return;
      }

      // Delete/Backspace - remove selected items
      if (event.key === 'Delete' || event.key === 'Backspace') {
        event.preventDefault();
        store.selections.forEach((id) => {
          // eslint-disable-next-line sonarjs/no-nested-functions -- arrow function in .some()
          const isNode = store.nodes.some((n) => n.id === id);
          if (isNode) {
            store.removeNode(id);
          } else {
            store.removeEdge(id);
          }
        });
      }

      // C key - start connect mode
      if (event.key === 'c' && !event.ctrlKey && !event.metaKey) {
        if (store.nodes.length >= 1) {
          event.preventDefault();
          startConnectMode();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [store, connectMode, cancelConnectMode, startConnectMode]);

  // Cleanup hover timeout on unmount
  useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) {
        clearTimeout(hoverTimeoutRef.current);
      }
    };
  }, []);

  return (
    <div className={`workflow-builder-canvas-wrapper h-full relative ${className}`}>
      {/* Fixed UI overlay - stays in place when scrolling */}
      <div className="absolute inset-0 pointer-events-none z-10">
        {/* Connect Mode Indicator */}
        {connectMode && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-blue-600 text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-2 pointer-events-auto">
            <LinkIcon className="w-4 h-4" />
            <span className="text-sm font-medium">
              {connectSourceId ? 'Click target node to connect' : 'Click source node first'}
            </span>
            <button
              onClick={cancelConnectMode}
              className="ml-2 text-blue-200 hover:text-white text-xs"
            >
              (Esc to cancel)
            </button>
          </div>
        )}

        {/* Zoom Controls - fixed in top-right corner */}
        <div className="absolute top-3 right-3 flex flex-col gap-1 bg-dark-800 rounded-lg border border-gray-700 p-1 pointer-events-auto">
          <button
            onClick={() => canvasRef.current?.zoomIn?.()}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-dark-700 rounded-sm"
            title="Zoom In"
          >
            <MagnifyingGlassPlusIcon className="w-4 h-4" />
          </button>
          <button
            onClick={() => canvasRef.current?.zoomOut?.()}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-dark-700 rounded-sm"
            title="Zoom Out"
          >
            <MagnifyingGlassMinusIcon className="w-4 h-4" />
          </button>
          <button
            onClick={() => canvasRef.current?.fitCanvas?.()}
            className="p-1.5 text-gray-400 hover:text-white hover:bg-dark-700 rounded-sm"
            title="Fit to View"
          >
            <ArrowPathIcon className="w-4 h-4" />
          </button>
          <div className="border-t border-gray-600 my-1" />
          <button
            onClick={connectMode ? cancelConnectMode : startConnectMode}
            disabled={store.nodes.length < 1}
            className={`p-1.5 rounded ${
              connectMode
                ? 'text-blue-400 bg-blue-900/50 hover:bg-blue-900/70'
                : 'text-gray-400 hover:text-white hover:bg-dark-700'
            } disabled:opacity-30 disabled:cursor-not-allowed`}
            title="Connect Nodes (C)"
          >
            <LinkIcon className="w-4 h-4" />
          </button>
          {store.selections.length > 0 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                const selectionsToDelete = [...store.selections];
                selectionsToDelete.forEach((id) => {
                  const isNode = store.nodes.some((n) => n.id === id);
                  if (isNode) {
                    store.removeNode(id);
                  } else {
                    store.removeEdge(id);
                  }
                });
              }}
              className="p-1.5 text-red-400 hover:text-red-300 hover:bg-dark-700 rounded-sm"
              title="Delete Selected (Del)"
            >
              <TrashIcon className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Hover Tooltip */}
        {hoveredNode && (
          <div
            className="fixed bg-dark-800 border border-gray-600 rounded-lg shadow-xl p-3 max-w-xs z-50 pointer-events-none"
            style={{
              left: hoveredNode.x,
              top: hoveredNode.y,
            }}
          >
            <div className="text-sm font-medium text-white mb-1">{hoveredNode.name}</div>
            <div className="text-xs text-gray-400 leading-relaxed">{hoveredNode.description}</div>
          </div>
        )}

        {/* Empty State - also in overlay */}
        {store.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <div className="text-6xl mb-4 opacity-50">+</div>
              <h3 className="text-lg font-medium text-gray-400 mb-2">Start Building</h3>
              <p className="text-sm text-gray-500 max-w-xs">
                Click components from the palette to add nodes. Click the + button on a node to
                connect it to another. Select nodes or edges to delete them.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Scrollable Canvas Container */}
      <div className="workflow-builder-canvas-container h-full bg-dark-900">
        {/* Canvas - ELK auto-layout always active */}
        <Canvas
          ref={canvasRef}
          className="workflow-builder-canvas"
          fit={true}
          nodes={reaflowNodes}
          edges={reaflowEdges}
          direction="RIGHT"
          selections={store.selections}
          animated={true}
          readonly={false}
          zoomable={true}
          pannable={true}
          maxHeight={canvasSize.height}
          maxWidth={canvasSize.width}
          onLayoutChange={onLayoutChange}
          onCanvasClick={handleCanvasClick}
          onNodeLinkCheck={handleNodeLinkCheck}
          onNodeLink={handleNodeLink}
          defaultPosition={CanvasPosition.CENTER}
          arrow={<MarkerArrow style={{ fill: '#b685ff' }} />}
          layoutOptions={{
            'elk.algorithm': 'layered',
            'elk.direction': 'RIGHT',
            'elk.edgeRouting': 'ORTHOGONAL',
            'elk.layered.spacing.nodeNodeBetweenLayers': '100',
            'elk.layered.spacing.edgeNodeBetweenLayers': '50',
            'elk.spacing.nodeNode': '60',
            'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
            'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
            'elk.portConstraints': 'FIXED_SIDE',
          }}
          edge={(props) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-assignment
            const { key, ...restProps } = props as any;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
            const edgeId = restProps.id as string;
            const isSelected = store.selections.includes(edgeId);
            return (
              <Edge
                // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                key={key}
                {...restProps}
                className={`workflow-builder-edge ${isSelected ? 'selected' : ''}`}
                style={{
                  stroke: isSelected ? '#f472b6' : '#b685ff',
                  strokeWidth: isSelected ? 4 : 3,
                }}
                onClick={(event: React.MouseEvent, edge: EdgeData) => {
                  event.stopPropagation();
                  store.setSelections([edge.id]);
                }}
                removable={true}
                onRemove={(_event: React.MouseEvent, edge: EdgeData) => {
                  store.removeEdge(edge.id);
                }}
              />
            );
          }}
          node={(props) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any, @typescript-eslint/no-unsafe-assignment
            const { key, ...restProps } = props as any;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
            const nodeData = (restProps.properties?.data || {}) as Record<string, unknown>;
            // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
            const nodeId = restProps.id as string;
            const isSelected = store.selections.includes(nodeId);
            const isConnectSource = connectMode && connectSourceId === nodeId;
            const isTemplateNode =
              nodeData.kind === 'transformation' && Boolean(nodeData.nodeTemplateId);
            // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
            const nodeText = (restProps.properties?.text || 'Node') as string;
            const nodeDescription = (nodeData.description as string) || '';
            // Determine template type from node name for transformation nodes
            const templateType = isTemplateNode ? getTemplateType(nodeText) : null;
            const templateColors = templateType ? getTemplateColors(templateType) : null;
            const colors = getNodeColors(
              (nodeData.kind as string) || 'task',
              isSelected,
              isConnectSource
            );

            // Use template-specific colors for border if this is a template node
            const borderColor =
              templateColors && !isSelected && !isConnectSource
                ? templateColors.border
                : colors.border;
            const textColor = templateColors ? templateColors.text : colors.text;

            // Hover handlers for tooltip
            const handleMouseEnter = (event: React.MouseEvent) => {
              if (!nodeDescription) return;
              // Clear any existing timeout
              if (hoverTimeoutRef.current) {
                clearTimeout(hoverTimeoutRef.current);
              }
              // Show tooltip after a short delay
              hoverTimeoutRef.current = setTimeout(() => {
                const rect = (event.target as SVGElement).getBoundingClientRect();
                setHoveredNode({
                  id: nodeId,
                  name: nodeText,
                  description: nodeDescription,
                  x: rect.right + 10,
                  y: rect.top,
                });
              }, 300);
            };

            const handleMouseLeave = () => {
              if (hoverTimeoutRef.current) {
                clearTimeout(hoverTimeoutRef.current);
                hoverTimeoutRef.current = null;
              }
              setHoveredNode(null);
            };

            return (
              <Node
                // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
                key={key}
                {...restProps}
                // Note: draggable must be true for edge-dragging to work
                // ELK will still auto-layout, but the user can initiate edge drags
                draggable={true}
                linkable={true}
                label={null}
                style={{
                  fill: colors.bg,
                  stroke: borderColor,
                  // eslint-disable-next-line sonarjs/no-nested-conditional
                  strokeWidth: isConnectSource ? 4 : isSelected ? 3 : 2,
                  rx: isTemplateNode ? 30 : 12,
                  ry: isTemplateNode ? 30 : 12,
                  cursor: connectMode ? 'crosshair' : 'pointer',
                }}
                removable={false}
                port={
                  <Port
                    style={{
                      fill: '#b685ff',
                      stroke: '#fff',
                      strokeWidth: 2,
                    }}
                    rx={10}
                    ry={10}
                  />
                }
                onClick={handleNodeClick}
                onEnter={handleMouseEnter}
                onLeave={handleMouseLeave}
              >
                {(nodeProps: { width: number; height: number }) => {
                  const { width, height } = nodeProps;
                  // Show action buttons when selected (not in connect mode)
                  const showActionButtons = isSelected && !connectMode;

                  return (
                    <>
                      {/* Action buttons - shown when selected */}
                      {showActionButtons && (
                        <>
                          {/* Delete Button - top left */}
                          <g
                            transform="translate(4, 4)"
                            style={{ cursor: 'pointer' }}
                            onClick={(e) => handleDeleteClick(nodeId, e)}
                          >
                            <circle r={10} fill="#ef4444" stroke="#fff" strokeWidth={1.5} />
                            <g transform="translate(-5, -5)">
                              <path
                                d="M3 3L7 7M7 3L3 7"
                                stroke="#fff"
                                strokeWidth={2}
                                strokeLinecap="round"
                              />
                            </g>
                          </g>

                          {/* Connect Button - bottom right */}
                          <g
                            transform={`translate(${width - 4}, ${height - 4})`}
                            style={{ cursor: 'pointer' }}
                            onClick={(e) => handleConnectClick(nodeId, e)}
                          >
                            <circle r={10} fill="#6366f1" stroke="#fff" strokeWidth={1.5} />
                            <text
                              textAnchor="middle"
                              dominantBaseline="central"
                              fill="#fff"
                              fontSize="14"
                              fontWeight="bold"
                              style={{ pointerEvents: 'none' }}
                            >
                              +
                            </text>
                          </g>
                        </>
                      )}

                      <foreignObject
                        width={width}
                        height={height}
                        style={{ overflow: 'visible', pointerEvents: 'none' }}
                      >
                        <div
                          style={{
                            width: '100%',
                            height: '100%',
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            padding: isTemplateNode ? '8px' : '12px',
                            color: textColor,
                            fontFamily: 'system-ui, -apple-system, sans-serif',
                            pointerEvents: 'none',
                          }}
                        >
                          {/* Icon for template nodes - matching view mode */}
                          {isTemplateNode && (
                            <div
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: textColor,
                              }}
                            >
                              {getTemplateIcon(templateType)}
                            </div>
                          )}

                          {/* Node name (for non-template nodes only) */}
                          {!isTemplateNode && (
                            <div
                              style={{
                                fontSize: '13px',
                                fontWeight: 500,
                                textAlign: 'center',
                                lineHeight: 1.3,
                                maxWidth: '100%',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                display: '-webkit-box',
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: 'vertical',
                              }}
                            >
                              {nodeText}
                            </div>
                          )}

                          {/* Kind badge (for non-template nodes) */}
                          {!isTemplateNode && (
                            <div
                              style={{
                                marginTop: '6px',
                                fontSize: '10px',
                                textTransform: 'uppercase',
                                letterSpacing: '0.5px',
                                opacity: 0.6,
                              }}
                            >
                              {typeof nodeData.kind === 'string' ? nodeData.kind : 'task'}
                            </div>
                          )}
                        </div>
                      </foreignObject>
                    </>
                  );
                }}
              </Node>
            );
          }}
        />
      </div>
    </div>
  );
};

export default WorkflowBuilderCanvas;
