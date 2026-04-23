import React, { useEffect, useRef, useState, useCallback } from 'react';

import {
  MagnifyingGlassPlusIcon,
  MagnifyingGlassMinusIcon,
  ArrowPathIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { ReactZoomPanPinchRef, TransformComponent, TransformWrapper } from 'react-zoom-pan-pinch';
import {
  Canvas,
  CanvasPosition,
  CanvasRef,
  Edge,
  EdgeData,
  NodeData,
  MarkerArrow,
  ElkRoot,
} from 'reaflow';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { Workflow, WorkflowExecutionGraph, WorkflowNodeInstance } from '../../types/workflow';

import WorkflowNode, { getNodeHeight } from './WorkflowNode';
import { getWorkflowStatusDisplay } from './workflowUtils';

import './WorkflowExecutionReaflow.css';

/**
 * Render the HITL (Human-in-the-Loop) detail panel for a paused workflow node.
 * Returns JSX when the node is paused with valid HITL JSON in error_message,
 * otherwise returns null.
 */
export function renderHitlDetail(
  status: string | undefined,
  errorMessage: string | undefined | null
): React.ReactElement | null {
  if (status !== 'paused' || !errorMessage) return null;
  try {
    const hitl = JSON.parse(errorMessage) as {
      hitl?: boolean;
      question?: string;
      channel?: string;
      options?: string;
    };
    if (!hitl?.hitl) return null;
    const options =
      typeof hitl.options === 'string'
        ? hitl.options
            .split(',')
            .map((o: string) => o.trim())
            .filter(Boolean)
        : [];
    return (
      <div className="node-detail-hitl">
        <div className="node-detail-hitl-header">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          Waiting for Human Response
        </div>
        {hitl.question && <div className="node-detail-hitl-question">{hitl.question}</div>}
        <div className="node-detail-hitl-meta">
          {hitl.channel && <span>Channel: {hitl.channel}</span>}
          {options.length > 0 && (
            <div className="node-detail-hitl-options">
              {options.map((opt: string) => (
                <span key={opt} className="node-detail-hitl-option">
                  {opt}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  } catch {
    // error_message is not valid JSON — not an HITL node
    return null;
  }
}

interface WorkflowExecutionReaflowProps {
  workflow: Workflow;
  workflowRunId: string;
  onClose?: () => void;
  className?: string;
}

// Build the WEST/EAST port list for a node based on its edge connectivity.
// When `center` is true, ports are aligned to the centre of the node side
// (useful for small connector nodes so edges don't attach below the circle).
function buildNodePorts(nodeId: string, inCount: number, outCount: number, center?: boolean) {
  const ports = [];
  const alignment = center ? ('CENTER' as const) : undefined;
  for (let i = 0; i < Math.max(inCount, 1); i++) {
    ports.push({
      id: `${nodeId}-in-${i}`,
      side: 'WEST' as const,
      width: 10,
      height: 10,
      alignment,
    });
  }
  for (let i = 0; i < Math.max(outCount, 1); i++) {
    ports.push({
      id: `${nodeId}-out-${i}`,
      side: 'EAST' as const,
      width: 10,
      height: 10,
      alignment,
    });
  }
  return ports;
}

// Determine edge status based on source/target node execution statuses.
function deriveEdgeStatus(sourceStatus: string, targetStatus: string): string {
  const activeTargetStatuses = ['running', 'completed', 'failed'];
  return sourceStatus === 'completed' && activeTargetStatuses.includes(targetStatus)
    ? 'active'
    : 'inactive';
}

const WorkflowExecutionReaflow: React.FC<WorkflowExecutionReaflowProps> = ({
  workflow,
  workflowRunId,
  onClose,
  className = '',
}) => {
  const canvasRef = useRef<CanvasRef | null>(null);
  const transRef = useRef<ReactZoomPanPinchRef | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollCountRef = useRef<number>(0);
  const lastPollTimeRef = useRef<number>(0);
  // Keep workflowRunId in a ref so the polling callback always sees the latest
  // value without needing to be recreated (avoids stale-closure bugs).
  const workflowRunIdRef = useRef<string>(workflowRunId);
  useEffect(() => {
    workflowRunIdRef.current = workflowRunId;
    // Reset positioning flag when workflow changes so new workflow gets positioned
    initialPositionDoneRef.current = false;
  }, [workflowRunId]);

  // When the user manually pans, we stop auto-following so we don't fight them.
  const userHasPannedRef = useRef<boolean>(false);
  // Track if initial positioning has been done to prevent re-positioning loops
  const initialPositionDoneRef = useRef<boolean>(false);

  const [executionGraph, setExecutionGraph] = useState<WorkflowExecutionGraph | undefined>();
  const [isPolling, setIsPolling] = useState(false);
  const [pollingStalled, setPollingStalled] = useState(false);
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [edges, setEdges] = useState<EdgeData[]>([]);
  const [selections, setSelections] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<WorkflowNodeInstance | null>(null);
  const [direction] = useState<'UP' | 'DOWN' | 'LEFT' | 'RIGHT'>('RIGHT');
  const [canvasSize, setCanvasSize] = useState({ width: 2000, height: 1500 });
  const [taskDescriptions, setTaskDescriptions] = useState<Map<string, string>>(new Map());
  // Track previous node count to avoid unnecessary ELK re-layouts on status-only updates
  const prevNodeCountRef = useRef<number>(0);

  useErrorHandler('WorkflowExecutionReaflow');

  // Batch-fetch task descriptions for hover tooltips
  useEffect(() => {
    if (!workflow) return;
    const taskIds = workflow.nodes
      .filter((n) => n.kind === 'task' && n.task_id)
      .map((n) => n.task_id as string);
    if (taskIds.length === 0) return;

    const uniqueIds = [...new Set(taskIds)];
    void (async () => {
      try {
        const { tasks } = await backendApi.getTasks({ limit: 100 });
        const descMap = new Map<string, string>();
        for (const task of tasks) {
          if (uniqueIds.includes(task.id) && task.description) {
            descMap.set(task.id, task.description);
          }
        }
        setTaskDescriptions(descMap);
      } catch {
        // Tooltips are non-critical; silently ignore fetch failures
      }
    })();
  }, [workflow]);

  // Schedule the next poll. Centralising this avoids duplicating the setTimeout
  // call and ensures we never leave the chain without a scheduled follow-up.
  const scheduleNextPoll = useCallback((delayMs: number) => {
    if (pollIntervalRef.current) {
      clearTimeout(pollIntervalRef.current);
    }
    pollIntervalRef.current = setTimeout(() => {
      void fetchExecutionGraphRef.current();
    }, delayMs);
  }, []); // no deps — only uses refs

  // Fetch execution graph data.
  // Bug fixes applied here:
  //   #1: Use workflowRunIdRef instead of closing over workflowRunId prop so
  //       the callback never goes stale when workflowRunId changes.
  //   #2: The 500ms too-fast guard now reschedules instead of bare-returning,
  //       so the polling chain is never silently killed.
  //   #3: The 1000-poll hard limit is raised to 18 000 (~5 hours at 1 s/poll)
  //       and surfaces a visible "stalled" state instead of silently freezing.
  const fetchExecutionGraph = useCallback(async () => {
    const now = Date.now();
    const currentRunId = workflowRunIdRef.current;

    if (!currentRunId) {
      return;
    }

    // Bug #2 fix: if called too soon after the previous poll, reschedule
    // rather than returning without booking a follow-up.
    if (now - lastPollTimeRef.current < 500) {
      scheduleNextPoll(500 - (now - lastPollTimeRef.current));
      return;
    }

    // Bug #3 fix: raised limit with visible UI feedback instead of silent stop.
    if (pollCountRef.current > 18000) {
      setIsPolling(false);
      setPollingStalled(true);
      if (pollIntervalRef.current) {
        clearTimeout(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      return;
    }

    lastPollTimeRef.current = now;
    pollCountRef.current += 1;

    try {
      const result = await backendApi.getWorkflowExecutionGraph(currentRunId);
      setExecutionGraph(result);

      // Stop polling if execution is complete
      if (result.is_complete) {
        setIsPolling(false);
        if (pollIntervalRef.current) {
          clearTimeout(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
        return;
      }

      scheduleNextPoll(1000);
    } catch (error) {
      console.error('Error fetching execution graph:', error);
      scheduleNextPoll(3000);
    }
  }, [scheduleNextPoll]); // Bug #1 fix: no workflowRunId dep — uses ref instead

  // Keep a stable ref to fetchExecutionGraph so scheduleNextPoll can always
  // call the latest version without capturing a stale closure.
  const fetchExecutionGraphRef = useRef(fetchExecutionGraph);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/immutability
    fetchExecutionGraphRef.current = fetchExecutionGraph;
  }, [fetchExecutionGraph]);

  // Transform data for Reaflow

  const transformToReaflowFormat = useCallback(
    (
      workflow: Workflow,
      executionGraph: WorkflowExecutionGraph
    ): { nodes: NodeData[]; edges: EdgeData[] } => {
      const reaflowNodes: NodeData[] = [];
      const reaflowEdges: EdgeData[] = [];

      // Create a map of execution instances for quick lookup
      const executionInstances = new Map(
        executionGraph.nodes?.map((instance) => [instance.node_uuid, instance]) || []
      );

      // Process ALL static workflow nodes (not just instantiated ones)
      // This ensures the graph structure remains constant during execution
      for (const staticNode of workflow.nodes) {
        const nodeInstance = executionInstances.get(staticNode.id);

        // Check if this is a template node (transformation with node_template_id)
        const isTemplateNode = staticNode.kind === 'transformation' && staticNode.node_template_id;

        // Count incoming and outgoing edges for this node
        const incomingCount = workflow.edges.filter((e) => e.to_node_uuid === staticNode.id).length;
        const outgoingCount = workflow.edges.filter(
          (e) => e.from_node_uuid === staticNode.id
        ).length;

        // Build WEST/EAST ports using the module-level helper
        // Centre-align ports on small connector nodes so edges attach at the middle
        const ports = buildNodePorts(staticNode.id, incomingCount, outgoingCount, !!isTemplateNode);

        reaflowNodes.push({
          id: staticNode.id,
          text: staticNode.name,
          // Template nodes are smaller circles (60x60), regular nodes are rectangles
          width: isTemplateNode ? 60 : 220,
          height: isTemplateNode ? 60 : getNodeHeight(staticNode.name, 220, 120),
          ports,
          data: {
            kind: staticNode.kind,
            status: nodeInstance?.status || 'waiting',
            nodeData: staticNode,
            instanceData: nodeInstance || null,
            taskDescription: staticNode.task_id
              ? taskDescriptions.get(staticNode.task_id)
              : undefined,
          },
        });
      }

      // Group edges by target node to assign ports in a meaningful order
      const edgesByTarget = new Map<string, typeof workflow.edges>();
      workflow.edges.forEach((edge) => {
        if (!edgesByTarget.has(edge.to_node_uuid)) {
          edgesByTarget.set(edge.to_node_uuid, []);
        }
        edgesByTarget.get(edge.to_node_uuid)!.push(edge);
      });

      // Sort edges to each target by source node ID to maintain consistent ordering
      edgesByTarget.forEach((edges) => {
        edges.sort((a, b) => a.from_node_uuid.localeCompare(b.from_node_uuid));
      });

      const nodeOutgoingPortIndex = new Map<string, number>();

      // Create edges
      for (const edge of workflow.edges) {
        const sourceId = reaflowNodes.find((n) => n.data?.nodeData?.id === edge.from_node_uuid)?.id;

        const targetId = reaflowNodes.find((n) => n.data?.nodeData?.id === edge.to_node_uuid)?.id;

        if (sourceId && targetId) {
          const sourceNode = reaflowNodes.find((n) => n.id === sourceId);
          const targetNode = reaflowNodes.find((n) => n.id === targetId);

          const edgeStatus = deriveEdgeStatus(
            sourceNode?.data?.status || '',
            targetNode?.data?.status || ''
          );

          // Get or initialize port index for source node
          const sourceOutIndex = nodeOutgoingPortIndex.get(edge.from_node_uuid) || 0;
          nodeOutgoingPortIndex.set(edge.from_node_uuid, sourceOutIndex + 1);

          // Get port index for target node based on sorted position
          const targetEdges = edgesByTarget.get(edge.to_node_uuid)!;
          const targetInIndex = targetEdges.indexOf(edge);

          reaflowEdges.push({
            id: edge.id,
            from: sourceId,
            to: targetId,
            fromPort: `${edge.from_node_uuid}-out-${sourceOutIndex}`,
            toPort: `${edge.to_node_uuid}-in-${targetInIndex}`,
            text: edge.alias || '',
            data: {
              status: edgeStatus,
              edgeData: edge,
            },
          });
        }
      }

      return { nodes: reaflowNodes, edges: reaflowEdges };
    },
    [taskDescriptions]
  );

  // Start polling when workflowRunId is set or changes.
  // We intentionally do NOT include fetchExecutionGraph here — it is accessed
  // via fetchExecutionGraphRef so this effect only re-runs when the run ID
  // actually changes, not on every render cycle.
  useEffect(() => {
    if (!workflowRunId) return;

    pollCountRef.current = 0;
    lastPollTimeRef.current = 0;
    prevNodeCountRef.current = 0;
    userHasPannedRef.current = false;
    setIsPolling(true);
    setPollingStalled(false);
    setExecutionGraph(undefined);

    void fetchExecutionGraphRef.current();

    return () => {
      if (pollIntervalRef.current) {
        clearTimeout(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      setIsPolling(false);
    };
  }, [workflowRunId]); // only workflowRunId — fetchExecutionGraph accessed via ref

  // Pan the viewport to keep the running nodes centred.
  // Uses actual DOM bounding rects to avoid ELK coordinate space mismatches.
  // Only runs while the user hasn't manually panned away.
  const panToRunningNodes = useCallback((currentNodes: NodeData[]) => {
    if (userHasPannedRef.current || !transRef.current) return;

    const runningIds = new Set(
      currentNodes.filter((n) => n.data?.status === 'running').map((n) => n.id)
    );
    if (runningIds.size === 0) return;

    const container = document.querySelector('.workflow-execution-container');
    if (!container) return;
    const containerRect = container.getBoundingClientRect();

    // Reaflow renders each node as a <g id="ref-N-node-{nodeId}">. We match
    // node elements by checking if their id contains one of the running node UUIDs.
    // We exclude port elements (their id contains the node id twice).
    const allNodeGs = container.querySelectorAll('g[id*="node-"]');
    const runningRects: DOMRect[] = [];
    allNodeGs.forEach((el) => {
      const elId = el.id;
      // Port elements have the pattern "ref-N-node-UUID-port-UUID", skip them
      if (elId.includes('-port-')) return;
      // Extract the node UUID: everything after "node-" (first 36 chars = UUID)
      const nodePrefix = elId.indexOf('node-');
      if (nodePrefix === -1) return;
      const nodeId = elId.slice(nodePrefix + 5, nodePrefix + 41);
      if (runningIds.has(nodeId)) {
        runningRects.push(el.getBoundingClientRect());
      }
    });

    if (runningRects.length === 0) return;

    // Centroid of running nodes in screen space
    const screenCx =
      runningRects.reduce((s, r) => s + r.left + r.width / 2, 0) / runningRects.length;
    const screenCy =
      runningRects.reduce((s, r) => s + r.top + r.height / 2, 0) / runningRects.length;

    // Convert screen centroid to container-relative coords
    const targetCx = screenCx - containerRect.left;
    const targetCy = screenCy - containerRect.top;

    const { scale, positionX, positionY } = transRef.current.instance.transformState;

    // Shift the current transform so the running centroid lands at the viewport centre.
    const newX = positionX + (containerRect.width / 2 - targetCx);
    const newY = positionY + (containerRect.height / 2 - targetCy);

    // Only animate if we need to move more than a small threshold.
    const dx = Math.abs(newX - positionX);
    const dy = Math.abs(newY - positionY);
    if (dx < 30 && dy < 30) return;

    transRef.current.setTransform(newX, newY, scale, 600, 'easeOut');
  }, []);

  // Update graph when execution data changes.
  // Perf fix: only replace the full nodes/edges arrays (which triggers an ELK
  // re-layout) when the graph *structure* changes (node count differs).
  // For status-only updates we mutate the existing node data in-place so
  // Reaflow re-renders the node colours without re-running the expensive
  // ELK layout pass.
  useEffect(() => {
    if (!workflow || !executionGraph) return;

    const { nodes: newNodes, edges: newEdges } = transformToReaflowFormat(workflow, executionGraph);
    const newNodeCount = newNodes.length;

    if (newNodeCount !== prevNodeCountRef.current) {
      // Structural change — replace arrays and let ELK re-layout.
      prevNodeCountRef.current = newNodeCount;
      setNodes(newNodes);
      setEdges(newEdges);
    } else {
      // Status-only change — update node data without replacing the array
      // reference so Reaflow doesn't trigger a full re-layout.
      const mergeNode = (existingNode: NodeData) => {
        const updated = newNodes.find((n) => n.id === existingNode.id);
        if (!updated) return existingNode;
        if (JSON.stringify(existingNode.data) === JSON.stringify(updated.data)) return existingNode;
        return { ...existingNode, data: updated.data };
      };
      const mergeEdge = (existingEdge: EdgeData) => {
        const updated = newEdges.find((e) => e.id === existingEdge.id);
        if (!updated) return existingEdge;
        if (JSON.stringify(existingEdge.data) === JSON.stringify(updated.data)) return existingEdge;
        return { ...existingEdge, data: updated.data };
      };
      setNodes((prev) => prev.map(mergeNode));
      // Edge statuses (active/inactive) may also change — update them too
      setEdges((prev) => prev.map(mergeEdge));
      // Auto-pan after state is committed (not during render).
      panToRunningNodes(newNodes);
    }
  }, [workflow, executionGraph, transformToReaflowFormat, panToRunningNodes]);

  // Handle node click
  const onNodeClick = useCallback((_event: any, node: NodeData) => {
    if (node.data?.instanceData) {
      setSelectedNode(node.data.instanceData);
      setSelections([node.id]);
    }
  }, []);

  // Handle canvas click
  const onCanvasClick = useCallback(() => {
    setSelectedNode(null);
    setSelections([]);
  }, []);

  // Handle Escape key to close details panel
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || event.key === 'Esc') {
        event.preventDefault();
        event.stopPropagation();

        // Check if details panel is open
        if (selectedNode) {
          setSelectedNode(null);
          setSelections([]);
        }
      }
    };

    // Use document with capture phase to catch event before other handlers
    document.addEventListener('keydown', handleEscape, true);
    return () => document.removeEventListener('keydown', handleEscape, true);
  }, [selectedNode]);

  // Handle layout change
  const onLayoutChange = useCallback((layout: ElkRoot) => {
    if (layout.width && layout.height) {
      // Set canvas size based on the actual graph size with padding
      const width = layout.width + 300;
      const height = layout.height + 300;
      setCanvasSize({ width, height });

      // Only do initial positioning once to prevent animation loops
      if (!initialPositionDoneRef.current) {
        // eslint-disable-next-line react-hooks/immutability -- ref mutation is intentional here
        initialPositionDoneRef.current = true;
        // After layout is set, position graph at left edge at full scale
        setTimeout(() => {
          if (transRef.current) {
            const container = document.querySelector('.workflow-execution-container');
            if (container) {
              const containerRect = container.getBoundingClientRect();
              // Position at left edge (x=20 for small padding) and vertically centered
              const verticalCenter = (containerRect.height - height) / 2;
              transRef.current.setTransform(20, Math.max(50, verticalCenter), 1.0, 0);
            }
          }
        }, 100);
      }
    }
  }, []);

  if (!executionGraph) {
    return (
      <div className={`workflow-execution-container ${className}`}>
        <div className="workflow-loading">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          <span className="ml-3">Loading workflow execution...</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`workflow-execution-container ${className}`}>
      <TransformWrapper
        centerOnInit={false}
        ref={transRef}
        minScale={0.05}
        maxScale={4}
        limitToBounds={false}
        initialScale={1}
        wheel={{ step: 0.08 }}
        zoomAnimation={{ animationType: 'easeOutQuad' }}
        doubleClick={{ disabled: true }}
        panning={{ excluded: [], velocityDisabled: true }}
        onPanningStart={() => {
          userHasPannedRef.current = true;
        }}
        onPanning={(ref) => ref.instance.wrapperComponent?.classList.add('dragging')}
        onPanningStop={(ref) => ref.instance.wrapperComponent?.classList.remove('dragging')}
      >
        {({ zoomIn, zoomOut, resetTransform: _resetTransform }) => (
          <>
            {/* Zoom Controls */}
            <div className="workflow-controls">
              <button onClick={() => zoomIn()} className="workflow-control-btn" title="Zoom In">
                <MagnifyingGlassPlusIcon className="w-4 h-4" />
              </button>
              <button onClick={() => zoomOut()} className="workflow-control-btn" title="Zoom Out">
                <MagnifyingGlassMinusIcon className="w-4 h-4" />
              </button>
              <button
                onClick={() => {
                  if (transRef.current) {
                    const container = document.querySelector('.workflow-execution-container');
                    if (container && canvasSize.height) {
                      const containerRect = container.getBoundingClientRect();
                      // Reset to left edge, vertically centered
                      const verticalCenter = (containerRect.height - canvasSize.height) / 2;
                      transRef.current.setTransform(20, Math.max(50, verticalCenter), 1.0, 300);
                    }
                  }
                }}
                className="workflow-control-btn"
                title="Reset View"
              >
                <ArrowPathIcon className="w-4 h-4" />
              </button>
              {onClose && (
                <button
                  onClick={onClose}
                  className="workflow-control-btn workflow-close-btn"
                  title="Close Execution View"
                >
                  <XMarkIcon className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Status Panel */}
            <div className="workflow-status-panel">
              <h3 className="workflow-status-title">{workflow.name}</h3>
              {executionGraph.summary && (
                <div className="workflow-summary">
                  <div className="workflow-summary-item">
                    <span>Status:</span>
                    <span className={getWorkflowStatusDisplay(executionGraph).colorClass}>
                      {getWorkflowStatusDisplay(executionGraph).label}
                    </span>
                  </div>
                  {executionGraph.summary.pending > 0 && (
                    <div className="workflow-summary-item">
                      <span>Pending:</span>
                      <span>{executionGraph.summary.pending}</span>
                    </div>
                  )}
                  {executionGraph.summary.running > 0 && (
                    <div className="workflow-summary-item">
                      <span>Running:</span>
                      <span className="text-blue">{executionGraph.summary.running}</span>
                    </div>
                  )}
                  {executionGraph.summary.completed > 0 && (
                    <div className="workflow-summary-item">
                      <span>Completed:</span>
                      <span className="text-green">{executionGraph.summary.completed}</span>
                    </div>
                  )}
                  {executionGraph.summary.failed > 0 && (
                    <div className="workflow-summary-item">
                      <span>Failed:</span>
                      <span className="text-red">{executionGraph.summary.failed}</span>
                    </div>
                  )}
                </div>
              )}
              {isPolling && (
                <div className="workflow-polling">
                  <div className="animate-spin rounded-full h-3 w-3 border-b border-current"></div>
                  <span>Live updates</span>
                </div>
              )}
              {pollingStalled && (
                <div className="workflow-polling" style={{ color: '#f59e0b' }}>
                  <span>⚠ Updates paused — </span>
                  <button
                    onClick={() => {
                      pollCountRef.current = 0;
                      lastPollTimeRef.current = 0;
                      setPollingStalled(false);
                      setIsPolling(true);
                      void fetchExecutionGraphRef.current();
                    }}
                    style={{ textDecoration: 'underline', cursor: 'pointer' }}
                  >
                    Resume
                  </button>
                </div>
              )}
            </div>

            {/* Node Details Panel */}
            {selectedNode && (
              <div className="workflow-node-details">
                <h4>Node Details</h4>
                <div className="node-detail-item">
                  <span>ID:</span>
                  <span>{selectedNode.node_id}</span>
                </div>
                <div className="node-detail-item">
                  <span>Status:</span>
                  <span className={`status-${selectedNode.status}`}>{selectedNode.status}</span>
                </div>
                {selectedNode.started_at && (
                  <div className="node-detail-item">
                    <span>Started:</span>
                    <span>{new Date(selectedNode.started_at).toLocaleTimeString()}</span>
                  </div>
                )}
                {selectedNode.completed_at && (
                  <div className="node-detail-item">
                    <span>Ended:</span>
                    <span>{new Date(selectedNode.completed_at).toLocaleTimeString()}</span>
                  </div>
                )}
                {selectedNode.started_at && selectedNode.completed_at && (
                  <div className="node-detail-item">
                    <span>Duration:</span>
                    <span>
                      {Math.round(
                        (new Date(selectedNode.completed_at).getTime() -
                          new Date(selectedNode.started_at).getTime()) /
                          1000
                      )}
                      s
                    </span>
                  </div>
                )}
                {selectedNode.created_at && (
                  <div className="node-detail-item">
                    <span>Created:</span>
                    <span>{new Date(selectedNode.created_at).toLocaleTimeString()}</span>
                  </div>
                )}
                {selectedNode.updated_at && (
                  <div className="node-detail-item">
                    <span>Updated:</span>
                    <span>{new Date(selectedNode.updated_at).toLocaleTimeString()}</span>
                  </div>
                )}
                {!!selectedNode.input_data &&
                  typeof selectedNode.input_data === 'object' &&
                  Object.keys(selectedNode.input_data as Record<string, unknown>).length > 0 && (
                    <div className="node-detail-data">
                      <span>Input Data:</span>
                      <pre className="node-data-json">
                        {JSON.stringify(selectedNode.input_data, null, 2)}
                      </pre>
                    </div>
                  )}
                {selectedNode.output_data && (
                  <div className="node-detail-data">
                    <span>Output Data:</span>
                    {selectedNode.output_data.result != null && (
                      <div className="node-data-section">
                        <span className="node-data-label">Result:</span>
                        <pre className="node-data-json">
                          {JSON.stringify(selectedNode.output_data.result, null, 2)}
                        </pre>
                      </div>
                    )}
                    {selectedNode.output_data.context != null && (
                      <div className="node-data-section">
                        <span className="node-data-label">Context:</span>
                        <pre className="node-data-json">
                          {JSON.stringify(selectedNode.output_data.context, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
                {renderHitlDetail(selectedNode.status, selectedNode.error_message)}
                {selectedNode.error_message && selectedNode.status !== 'paused' && (
                  <div className="node-detail-error">
                    <span>Error:</span>
                    <span>{selectedNode.error_message}</span>
                  </div>
                )}
              </div>
            )}

            {/* Canvas */}
            <TransformComponent
              wrapperStyle={{
                width: '100%',
                height: '100%',
                overflow: 'hidden',
              }}
            >
              <Canvas
                ref={canvasRef}
                className="workflow-canvas"
                fit={false}
                nodes={nodes}
                edges={edges}
                direction={direction}
                selections={selections}
                animated={true}
                readonly={true}
                zoomable={false}
                maxHeight={canvasSize.height}
                maxWidth={canvasSize.width}
                pannable={true}
                defaultPosition={CanvasPosition.CENTER}
                onLayoutChange={onLayoutChange}
                onCanvasClick={onCanvasClick}
                arrow={<MarkerArrow style={{ fill: '#b685ff' }} />}
                layoutOptions={{
                  'elk.algorithm': 'layered',
                  'elk.direction': 'RIGHT',
                  'elk.edgeRouting': 'ORTHOGONAL',
                  'elk.layered.spacing.nodeNodeBetweenLayers': '100',
                  'elk.layered.spacing.edgeNodeBetweenLayers': '50',
                  'elk.spacing.nodeNode': '80',
                  'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
                  'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
                  'elk.portConstraints': 'FIXED_ORDER',
                  'elk.portAlignment.default': 'CENTER',
                }}
                edge={(props) => (
                  <Edge
                    {...props}
                    className={`workflow-edge ${(props as any).data?.status === 'active' ? 'edge-active' : ''}`}
                    style={{
                      stroke:
                        (props as any).data?.status === 'active'
                          ? '#62c4ff'
                          : 'rgba(182, 133, 255, 0.4)',
                    }}
                  />
                )}
                node={(props) => <WorkflowNode {...props} onClick={onNodeClick} />}
              />
            </TransformComponent>
          </>
        )}
      </TransformWrapper>
    </div>
  );
};

export default WorkflowExecutionReaflow;
