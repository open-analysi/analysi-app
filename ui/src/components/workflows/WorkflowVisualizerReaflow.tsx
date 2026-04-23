import React, { useState, useCallback, useRef, useEffect, lazy, Suspense } from 'react';

import {
  MagnifyingGlassPlusIcon,
  MagnifyingGlassMinusIcon,
  ArrowPathIcon,
  PlayIcon,
  ArrowTopRightOnSquareIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router';
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
import { Task } from '../../types/knowledge';
import { Workflow, WorkflowNode as WorkflowNodeType } from '../../types/workflow';

import { WorkflowExecutionDialog } from './WorkflowExecutionDialog';
import WorkflowNode, { getNodeHeight } from './WorkflowNode';

import './WorkflowVisualizerReaflow.css';

/* eslint-disable @typescript-eslint/no-explicit-any */
const LazyAceEditor = lazy(async (): Promise<{ default: React.ComponentType<any> }> => {
  try {
    // ace core must load before mode/theme side-effect imports
    const aceModule = await import('ace-builds/src-noconflict/ace');
    // Ensure ace is on the global scope before loading mode/theme
    if (typeof window !== 'undefined' && !(window as any).ace) {
      (window as any).ace = aceModule.default || aceModule;
    }
    await Promise.all([
      import('ace-builds/src-noconflict/mode-python'),
      import('ace-builds/src-noconflict/theme-terminal'),
    ]);
    return import('react-ace') as Promise<{ default: React.ComponentType<any> }>;
  } catch {
    // If ace fails to load, return a plain-text fallback
    const Fallback: React.FC<{ value?: string }> = ({ value }) => (
      <pre className="cy-script-block">
        <code>{value || ''}</code>
      </pre>
    );
    return { default: Fallback as React.ComponentType<any> };
  }
});
/* eslint-enable @typescript-eslint/no-explicit-any */

interface WorkflowVisualizerReaflowProps {
  workflow: Workflow;
  onNodeSelect?: (nodeId: string) => void;
  onExecuteWorkflow?: () => void;
  className?: string;
}

const WorkflowVisualizerReaflow: React.FC<WorkflowVisualizerReaflowProps> = ({
  workflow,
  onNodeSelect,
  onExecuteWorkflow,
  className = '',
}) => {
  const navigate = useNavigate();
  const canvasRef = useRef<CanvasRef | null>(null);
  const transRef = useRef<ReactZoomPanPinchRef | null>(null);
  const detailsPanelRef = useRef<HTMLDivElement | null>(null);

  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [edges, setEdges] = useState<EdgeData[]>([]);
  const [selections, setSelections] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<WorkflowNodeType | null>(null);
  const [clickedNodeRect, setClickedNodeRect] = useState<DOMRect | null>(null);
  const [selectedTaskDetails, setSelectedTaskDetails] = useState<Task | null>(null);
  const [loadingTaskDetails, setLoadingTaskDetails] = useState(false);
  const [direction] = useState<'UP' | 'DOWN' | 'LEFT' | 'RIGHT'>('RIGHT');
  const [canvasSize, setCanvasSize] = useState({ width: 2000, height: 1500 });
  const [infoPanelCollapsed, setInfoPanelCollapsed] = useState(true);
  const [taskDescriptions, setTaskDescriptions] = useState<Map<string, string>>(new Map());

  const [executionDialog, setExecutionDialog] = useState<{
    isOpen: boolean;
    loading: boolean;
  }>({
    isOpen: false,
    loading: false,
  });

  const { runSafe } = useErrorHandler('WorkflowVisualizerReaflow');

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

  // Transform static workflow to Reaflow format
  React.useEffect(() => {
    if (!workflow) return;

    const reaflowNodes: NodeData[] = workflow.nodes.map((node) => {
      // Check if this is a template node (transformation with node_template_id)
      const isTemplateNode = node.kind === 'transformation' && node.node_template_id;

      // Count incoming and outgoing edges for this node
      const incomingCount = workflow.edges.filter((e) => e.to_node_uuid === node.id).length;
      const outgoingCount = workflow.edges.filter((e) => e.from_node_uuid === node.id).length;

      // Create ports for the node to allow edges to connect at different positions
      const ports = [];

      // Add input ports on the WEST side (multiple ports for multiple incoming edges)
      // Ports are ordered from top to bottom (index 0 = top, increasing = lower)
      for (let i = 0; i < Math.max(incomingCount, 1); i++) {
        ports.push({
          id: `${node.id}-in-${i}`,
          side: 'WEST' as const,
          width: 10,
          height: 10,
        });
      }

      // Add output ports on the EAST side (multiple ports for multiple outgoing edges)
      for (let i = 0; i < Math.max(outgoingCount, 1); i++) {
        ports.push({
          id: `${node.id}-out-${i}`,
          side: 'EAST' as const,
          width: 10,
          height: 10,
        });
      }

      const baseWidth = 180;
      const baseHeight = 100;

      return {
        id: node.id,
        text: node.name,
        width: isTemplateNode ? 60 : baseWidth,
        height: isTemplateNode ? 60 : getNodeHeight(node.name, baseWidth, baseHeight),
        ports,
        data: {
          kind: node.kind,
          status: 'static', // Static nodes don't have execution status
          nodeData: node,
          instanceData: null,
          taskDescription: node.task_id ? taskDescriptions.get(node.task_id) : undefined,
        },
      };
    });

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

    const reaflowEdges: EdgeData[] = workflow.edges.map((edge) => {
      // Get or initialize port index for source node
      const sourceOutIndex = nodeOutgoingPortIndex.get(edge.from_node_uuid) || 0;
      nodeOutgoingPortIndex.set(edge.from_node_uuid, sourceOutIndex + 1);

      // Get port index for target node based on sorted position
      const targetEdges = edgesByTarget.get(edge.to_node_uuid)!;
      const targetInIndex = targetEdges.indexOf(edge);

      return {
        id: edge.id,
        from: edge.from_node_uuid,
        to: edge.to_node_uuid,
        fromPort: `${edge.from_node_uuid}-out-${sourceOutIndex}`,
        toPort: `${edge.to_node_uuid}-in-${targetInIndex}`,
        text: edge.alias || '',
        data: {
          status: 'static',
          edgeData: edge,
        },
      };
    });

    setNodes(reaflowNodes);
    setEdges(reaflowEdges);
  }, [workflow, taskDescriptions]);

  // Fetch task details when a task node is selected
  useEffect(() => {
    const fetchTaskDetails = async () => {
      if (!selectedNode || selectedNode.kind !== 'task' || !selectedNode.task_id) {
        setSelectedTaskDetails(null);
        return;
      }

      setLoadingTaskDetails(true);
      try {
        const [response] = await runSafe(
          backendApi.getTask(selectedNode.task_id),
          'fetchTaskDetails',
          { action: 'fetching task details', entityId: selectedNode.task_id }
        );

        if (response) {
          setSelectedTaskDetails(response);
        }
      } catch (error) {
        console.error('Failed to fetch task details:', error);
        setSelectedTaskDetails(null);
      } finally {
        setLoadingTaskDetails(false);
      }
    };

    void fetchTaskDetails();
  }, [selectedNode, runSafe]);

  // Position details panel next to the clicked node
  useEffect(() => {
    if (!detailsPanelRef.current || !selectedNode || !clickedNodeRect) return;

    const panel = detailsPanelRef.current;
    const container = document.querySelector('.static-workflow-container');
    if (!container) return;

    const containerRect = container.getBoundingClientRect();
    const panelWidth = 420;
    const gap = 16;
    const margin = 16;

    // Calculate node position relative to the container
    const nodeLeft = clickedNodeRect.left - containerRect.left;
    const nodeRight = clickedNodeRect.right - containerRect.left;
    const nodeTop = clickedNodeRect.top - containerRect.top;

    // Try placing to the right of the node
    let left = nodeRight + gap;

    // If it overflows the container's right edge, try to the left of the node
    if (left + panelWidth > containerRect.width - margin) {
      left = nodeLeft - panelWidth - gap;
    }

    // If it still overflows, clamp to fit within the container
    left = Math.max(margin, Math.min(left, containerRect.width - panelWidth - margin));

    let top = nodeTop;
    // Ensure panel fits vertically
    const panelHeight = panel.offsetHeight;
    top = Math.max(margin, Math.min(top, containerRect.height - panelHeight - margin));

    panel.style.right = '';
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    panel.style.bottom = '';
  }, [selectedNode, selectedTaskDetails, clickedNodeRect]);

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

  // Handle node click
  const onNodeClick = useCallback(
    (_event: any, node: NodeData) => {
      setSelectedNode(node.data?.nodeData);
      setSelections([node.id]);

      // Capture clicked node's screen position for panel placement
      const g = document.getElementById(`ref-1-node-${node.id}`);
      if (g) {
        setClickedNodeRect(g.getBoundingClientRect());
      }

      if (onNodeSelect) {
        onNodeSelect(node.id);
      }
    },
    [onNodeSelect]
  );

  // Handle canvas click
  const onCanvasClick = useCallback(() => {
    setSelectedNode(null);
    setSelections([]);
  }, []);

  // Handle opening task in workbench
  const handleOpenInWorkbench = useCallback(() => {
    if (selectedNode?.task_id) {
      // Open in new tab
      window.open(`/workbench?taskId=${selectedNode.task_id}`, '_blank');
    }
  }, [selectedNode]);

  // Handle layout change
  const onLayoutChange = useCallback((layout: ElkRoot) => {
    if (layout.width && layout.height) {
      // Set canvas size based on the actual graph size with minimal padding
      const canvasPadding = 100;
      const width = layout.width + canvasPadding;
      const height = layout.height + canvasPadding;
      setCanvasSize({ width, height });

      // After layout is set, position the view for best readability
      setTimeout(() => {
        if (transRef.current) {
          const container = document.querySelector('.static-workflow-container');
          if (container && layout.height) {
            const containerRect = container.getBoundingClientRect();
            const graphHeight = layout.height;

            // Calculate scale that would fit height with good margins
            const verticalMargin = 60;
            const availableHeight = containerRect.height - verticalMargin * 2;
            const scaleToFitHeight = availableHeight / graphHeight;

            // Use a scale that prioritizes readability - fit height, allow horizontal pan
            // Cap between 0.5 (minimum readable) and 1.0 (don't over-zoom)
            const scale = Math.min(Math.max(scaleToFitHeight, 0.5), 1.0);

            // Position: center vertically, start from left with small offset
            const scaledHeight = graphHeight * scale;
            const y = (containerRect.height - scaledHeight) / 2;
            // Start from left side with padding for the collapsed info panel
            const x = 80;

            // Set transform
            transRef.current.setTransform(x, y, scale, 0);
          }
        }
      }, 250);
    }
  }, []);

  // Handle workflow execution
  const handleExecuteClick = () => {
    if (onExecuteWorkflow) {
      onExecuteWorkflow();
    } else {
      setExecutionDialog({ isOpen: true, loading: false });
    }
  };

  const handleExecuteWorkflow = async (inputData: Record<string, any>) => {
    setExecutionDialog((prev) => ({ ...prev, loading: true }));

    try {
      const [result] = await runSafe(
        backendApi.executeWorkflow(workflow.id, { input_data: inputData }),
        'executeWorkflow',
        { action: 'executing workflow', entityId: workflow.id, params: inputData }
      );

      if (result) {
        setExecutionDialog({ isOpen: false, loading: false });
        // Navigate to the dedicated workflow run page
        void navigate(`/workflow-runs/${result.workflow_run_id}`);
      }
    } catch (error) {
      console.error('Failed to execute workflow:', error);
    } finally {
      setExecutionDialog((prev) => ({ ...prev, loading: false }));
    }
  };

  const closeExecutionDialog = () => {
    setExecutionDialog({ isOpen: false, loading: false });
  };

  return (
    <>
      <div className={`static-workflow-container ${className}`}>
        <TransformWrapper
          centerOnInit={false}
          ref={transRef}
          minScale={0.05}
          maxScale={4}
          limitToBounds={false}
          initialScale={0.5}
          wheel={{ step: 0.08 }}
          zoomAnimation={{ animationType: 'easeOutQuad' }}
          doubleClick={{ disabled: true }}
          panning={{ excluded: [], velocityDisabled: true }}
          onPanning={(ref) => ref.instance.wrapperComponent?.classList.add('dragging')}
          onPanningStop={(ref) => ref.instance.wrapperComponent?.classList.remove('dragging')}
        >
          {({ zoomIn, zoomOut, resetTransform: _resetTransform }) => (
            <>
              {/* Controls */}
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
                      const container = document.querySelector('.static-workflow-container');
                      if (container && canvasSize.width && canvasSize.height) {
                        const containerRect = container.getBoundingClientRect();
                        // Use the graph dimensions (canvas minus padding)
                        const graphWidth = canvasSize.width - 100;
                        const graphHeight = canvasSize.height - 100;

                        // Leave some margin around the graph
                        const margin = 40;
                        const availableWidth = containerRect.width - margin * 2;
                        const availableHeight = containerRect.height - margin * 2;

                        // Calculate scale to fit graph in available space
                        const scaleX = availableWidth / graphWidth;
                        const scaleY = availableHeight / graphHeight;
                        // Pick smaller scale to fit both dimensions, cap at 1.0
                        const scale = Math.min(scaleX, scaleY, 1.0);

                        // Calculate position to center the graph
                        const scaledWidth = graphWidth * scale;
                        const scaledHeight = graphHeight * scale;
                        const x = (containerRect.width - scaledWidth) / 2;
                        const y = (containerRect.height - scaledHeight) / 2;

                        // Set transform to center and scale the view
                        transRef.current.setTransform(x, y, scale, 300);
                      }
                    }
                  }}
                  className="workflow-control-btn"
                  title="Fit to View"
                >
                  <ArrowPathIcon className="w-4 h-4" />
                </button>
                <button
                  onClick={handleExecuteClick}
                  className="workflow-control-btn workflow-execute-btn"
                  title="Execute Workflow"
                >
                  <PlayIcon className="w-4 h-4" />
                </button>
              </div>

              {/* Workflow Info Panel - Collapsible */}
              <div className={`workflow-info-panel ${infoPanelCollapsed ? 'collapsed' : ''}`}>
                <button
                  className="workflow-info-header"
                  onClick={() => setInfoPanelCollapsed(!infoPanelCollapsed)}
                  title={infoPanelCollapsed ? 'Expand panel' : 'Collapse panel'}
                >
                  <h3 className="workflow-info-title">{workflow.name}</h3>
                  {infoPanelCollapsed ? (
                    <ChevronDownIcon className="w-4 h-4 collapse-icon" />
                  ) : (
                    <ChevronUpIcon className="w-4 h-4 collapse-icon" />
                  )}
                </button>
                {!infoPanelCollapsed && (
                  <div className="workflow-info-content">
                    {workflow.description && (
                      <p className="workflow-info-description">{workflow.description}</p>
                    )}
                    <div className="workflow-info-stats">
                      <div className="workflow-stat">
                        <span>Nodes:</span>
                        <span>{workflow.nodes.length}</span>
                      </div>
                      <div className="workflow-stat">
                        <span>Edges:</span>
                        <span>{workflow.edges.length}</span>
                      </div>
                      <div className="workflow-stat">
                        <span>Type:</span>
                        <span>{workflow.is_dynamic ? 'Dynamic' : 'Static'}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Selected Node Details */}
              {selectedNode && (
                <div className="workflow-node-details" ref={detailsPanelRef}>
                  <div className="node-details-header">
                    <h4>Node Details</h4>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {selectedNode.kind === 'task' && selectedNode.task_id && (
                        <button
                          onClick={handleOpenInWorkbench}
                          className="open-workbench-btn"
                          title="Open in Workbench (new tab)"
                        >
                          <ArrowTopRightOnSquareIcon className="w-4 h-4" />
                          <span>Open in Workbench</span>
                        </button>
                      )}
                      <button
                        onClick={onCanvasClick}
                        className="workflow-control-btn"
                        title="Close panel"
                        style={{ width: '28px', height: '28px' }}
                      >
                        <XMarkIcon className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  <div className="node-detail-item">
                    <span>ID:</span>
                    <span>{selectedNode.node_id}</span>
                  </div>
                  <div className="node-detail-item">
                    <span>Name:</span>
                    <span>{selectedNode.name}</span>
                  </div>
                  <div className="node-detail-item">
                    <span>Type:</span>
                    <span className={`node-kind-${selectedNode.kind}`}>{selectedNode.kind}</span>
                  </div>

                  {/* Show Cy Script for task nodes */}
                  {selectedNode.kind === 'task' && (
                    <div className="node-detail-code">
                      <span className="code-label">Cy Script:</span>
                      {(() => {
                        if (loadingTaskDetails) {
                          return <div className="code-loading">Loading script...</div>;
                        }
                        if (selectedTaskDetails?.script) {
                          return (
                            <Suspense
                              fallback={
                                <pre className="cy-script-block">
                                  <code>{selectedTaskDetails.script}</code>
                                </pre>
                              }
                            >
                              <LazyAceEditor
                                mode="python"
                                theme="terminal"
                                value={selectedTaskDetails.script}
                                readOnly
                                highlightActiveLine={false}
                                showGutter={false}
                                showPrintMargin={false}
                                maxLines={Infinity}
                                wrapEnabled
                                width="100%"
                                fontSize={11}
                                style={{
                                  borderRadius: '6px',
                                  border: '1px solid rgba(182, 133, 255, 0.3)',
                                }}
                                setOptions={{
                                  useWorker: false,
                                  showFoldWidgets: false,
                                  tabSize: 2,
                                }}
                              />
                            </Suspense>
                          );
                        }
                        return <div className="code-empty">No script available</div>;
                      })()}
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
                  className="static-workflow-canvas"
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
                  onLayoutChange={onLayoutChange}
                  onCanvasClick={onCanvasClick}
                  defaultPosition={CanvasPosition.TOP}
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
                  }}
                  edge={(props) => {
                    const { key, ...restProps } = props as any;
                    return (
                      <Edge
                        key={key}
                        {...restProps}
                        className="static-workflow-edge"
                        style={{ stroke: 'rgba(182, 133, 255, 0.4)' }}
                      />
                    );
                  }}
                  node={(props) => {
                    const { key, ...restProps } = props as any;
                    const isSelected = selections.includes(restProps.id);
                    return (
                      <WorkflowNode
                        key={key}
                        {...restProps}
                        onClick={onNodeClick}
                        isSelected={isSelected}
                      />
                    );
                  }}
                />
              </TransformComponent>
            </>
          )}
        </TransformWrapper>
      </div>

      {/* Execution Dialog */}
      {executionDialog.isOpen && (
        <WorkflowExecutionDialog
          workflow={workflow}
          isOpen={executionDialog.isOpen}
          loading={executionDialog.loading}
          onClose={closeExecutionDialog}
          onExecute={(inputData) => void handleExecuteWorkflow(inputData)}
        />
      )}
    </>
  );
};

export default WorkflowVisualizerReaflow;
