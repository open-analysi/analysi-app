import React, { useEffect, useRef, useState } from 'react';

import cytoscape, { NodeSingular, LayoutOptions, Core } from 'cytoscape';
import dagre from 'cytoscape-dagre';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import {
  Workflow,
  WorkflowNode,
  WorkflowEdge,
  CytoscapeElements,
  NODE_KIND_COLORS,
  WorkflowNodeKind,
} from '../../types/workflow';

import { WorkflowExecutionDialog } from './WorkflowExecutionDialog';
import WorkflowExecutionReaflow from './WorkflowExecutionReaflow';

interface WorkflowVisualizerProps {
  workflow: Workflow;
  onNodeSelect?: (nodeId: string) => void;
  onExecuteWorkflow?: () => void;
  className?: string;
}

const WorkflowVisualizer: React.FC<WorkflowVisualizerProps> = ({
  workflow,
  onNodeSelect,
  onExecuteWorkflow,
  className = '',
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [executionDialog, setExecutionDialog] = useState<{
    isOpen: boolean;
    loading: boolean;
  }>({
    isOpen: false,
    loading: false,
  });
  const [executionView, setExecutionView] = useState<{
    isActive: boolean;
    workflowRunId: string | null;
  }>({
    isActive: false,
    workflowRunId: null,
  });

  const { runSafe } = useErrorHandler('WorkflowVisualizer');

  // Register the dagre extension
  useEffect(() => {
    if (!Object.prototype.hasOwnProperty.call(cytoscape.prototype, 'dagre')) {
      cytoscape.use(dagre);
    }
  }, []);

  // Transform workflow data to Cytoscape format
  const transformWorkflowToCytoscape = (workflow: Workflow): CytoscapeElements => {
    const nodes = workflow.nodes.map((node: WorkflowNode) => ({
      data: {
        id: node.id,
        label: node.name,
        kind: node.kind as WorkflowNodeKind,
        nodeData: node,
      },
    }));

    const edges = workflow.edges.map((edge: WorkflowEdge) => ({
      data: {
        id: edge.id,
        source: edge.from_node_uuid,
        target: edge.to_node_uuid,
        label: edge.alias || '',
        edgeData: edge,
      },
    }));

    return { nodes, edges };
  };

  // Initialize and update cytoscape
  useEffect(() => {
    if (!containerRef.current || !workflow) return;

    // Clean up existing instance
    if (cyRef.current) {
      cyRef.current.destroy();
    }

    const elements = transformWorkflowToCytoscape(workflow);
    const allElements = [...elements.nodes, ...elements.edges];

    // Create cytoscape instance
    cyRef.current = cytoscape({
      container: containerRef.current,
      elements: allElements,
      style: [
        // Base node style
        {
          selector: 'node',
          style: {
            width: 120,
            height: 80,
            shape: 'round-rectangle',
            'background-color': '#4b5563',
            'border-width': 3,
            'border-color': '#e5e7eb',
            label: 'data(label)',
            'text-valign': 'center',
            'text-halign': 'center',
            color: '#ffffff',
            'font-size': 18,
            'font-weight': 'bold',
            'text-wrap': 'wrap',
            'text-max-width': 100 as any,
            'text-background-color': '#1f2937',
            'text-background-opacity': 0.8,
            'text-background-padding': 4 as any,
            'text-background-shape': 'roundrectangle',
          },
        },
        // Task nodes (blue)
        {
          selector: 'node[kind = "task"]',
          style: {
            'background-color': NODE_KIND_COLORS.task,
            shape: 'round-rectangle',
          },
        },
        // Transformation nodes (green, diamond)
        {
          selector: 'node[kind = "transformation"]',
          style: {
            'background-color': NODE_KIND_COLORS.transformation,
            shape: 'diamond',
            width: 100,
            height: 100,
          },
        },
        // Foreach nodes (orange, hexagon)
        {
          selector: 'node[kind = "foreach"]',
          style: {
            'background-color': NODE_KIND_COLORS.foreach,
            shape: 'hexagon',
            width: 110,
            height: 90,
          },
        },
        // Selected/highlighted node
        {
          selector: 'node.highlighted',
          style: {
            'border-color': '#fbbf24',
            'border-width': 4,
            'border-opacity': 1,
          },
        },
        // Base edge style
        {
          selector: 'edge',
          style: {
            'curve-style': 'bezier',
            width: 3,
            'line-color': '#6b7280',
            'target-arrow-color': '#6b7280',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 1.2,
            label: 'data(label)',
            'font-size': 14,
            'font-weight': 'bold',
            color: '#374151',
            'text-background-color': '#f9fafb',
            'text-background-opacity': 0.8,
            'text-background-padding': 3 as any,
            'text-background-shape': 'roundrectangle',
          },
        },
        // Highlighted edge
        {
          selector: 'edge.highlighted',
          style: {
            'line-color': '#fbbf24',
            'target-arrow-color': '#fbbf24',
            width: 4,
          },
        },
      ],
      layout: {
        name: 'dagre',
        directed: true,
        rankDir: 'TB', // Top to bottom
        nodeSep: 50,
        edgeSep: 20,
        rankSep: 100,
        animate: true,
        animationDuration: 500,
        animationEasing: 'ease-in-out',
      } as LayoutOptions,
      minZoom: 0.3,
      maxZoom: 3,
      zoomingEnabled: true,
      userZoomingEnabled: true,
      panningEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      selectionType: 'single',
      touchTapThreshold: 8,
      desktopTapThreshold: 4,
      wheelSensitivity: 0.1,
    });

    const cy = cyRef.current;

    // Event handlers
    cy.on('tap', 'node', (evt) => {
      const node = evt.target as NodeSingular;
      const nodeId = node.id();

      // Clear previous highlights
      cy.elements().removeClass('highlighted');

      // Highlight selected node and connected edges
      node.addClass('highlighted');
      node.connectedEdges().addClass('highlighted');

      if (onNodeSelect) {
        onNodeSelect(nodeId);
      }
    });

    // Clear selection on background click
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass('highlighted');
        if (onNodeSelect) {
          onNodeSelect('');
        }
      }
    });

    // Cleanup
    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [workflow, onNodeSelect]);

  // Handle window resize to refresh layout
  useEffect(() => {
    const handleResize = () => {
      if (cyRef.current) {
        cyRef.current.resize();
        cyRef.current.fit();
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Handle execution dialog
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
        // Close dialog and switch to execution view
        setExecutionDialog({ isOpen: false, loading: false });
        setExecutionView({
          isActive: true,
          workflowRunId: result.workflow_run_id,
        });
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

  const closeExecutionView = () => {
    setExecutionView({ isActive: false, workflowRunId: null });
  };

  // Show execution visualizer when execution is active
  if (executionView.isActive && executionView.workflowRunId) {
    return (
      <WorkflowExecutionReaflow
        workflow={workflow}
        workflowRunId={executionView.workflowRunId}
        onClose={closeExecutionView}
        className={className}
      />
    );
  }

  return (
    <div className={`relative ${className}`}>
      {/* Graph Container */}
      <div
        ref={containerRef}
        className="w-full h-full bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700"
        style={{ minHeight: '500px' }}
      />

      {/* Floating Controls */}
      <div className="absolute top-4 right-4 flex flex-col space-y-2">
        {/* Fit View Button */}
        <button
          onClick={() => cyRef.current?.fit()}
          className="px-3 py-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-xs text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary"
          title="Fit to view"
        >
          Fit
        </button>

        {/* Execute Button */}
        <button
          onClick={handleExecuteClick}
          className="px-3 py-2 bg-primary text-white rounded-md shadow-xs text-sm font-medium hover:bg-primary/90 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary"
          title="Execute workflow"
        >
          ⚡ Execute
        </button>
      </div>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 shadow-lg">
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-2">Node Types</h4>
        <div className="space-y-1 text-xs">
          <div className="flex items-center space-x-2">
            <div
              className="w-3 h-3 rounded-sm"
              style={{ backgroundColor: NODE_KIND_COLORS.task }}
            ></div>
            <span className="text-gray-700 dark:text-gray-300">Task</span>
          </div>
          <div className="flex items-center space-x-2">
            <div
              className="w-3 h-3"
              style={{
                backgroundColor: NODE_KIND_COLORS.transformation,
                clipPath: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)',
              }}
            ></div>
            <span className="text-gray-700 dark:text-gray-300">Transformation</span>
          </div>
          <div className="flex items-center space-x-2">
            <div
              className="w-3 h-3"
              style={{
                backgroundColor: NODE_KIND_COLORS.foreach,
                clipPath: 'polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)',
              }}
            ></div>
            <span className="text-gray-700 dark:text-gray-300">ForEach</span>
          </div>
        </div>
      </div>

      {/* Workflow Info */}
      <div className="absolute top-4 left-4 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 shadow-lg max-w-xs">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
          {workflow.name}
        </h3>
        <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">{workflow.description}</p>
        <div className="flex items-center space-x-4 text-xs text-gray-500 dark:text-gray-500">
          <span>{workflow.nodes.length} nodes</span>
          <span>{workflow.edges.length} edges</span>
          <span
            className={`px-2 py-1 rounded-full text-xs font-medium ${
              workflow.is_dynamic
                ? 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300'
                : 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300'
            }`}
          >
            {workflow.is_dynamic ? 'Dynamic' : 'Static'}
          </span>
        </div>
      </div>

      {/* Execution Dialog */}
      <WorkflowExecutionDialog
        isOpen={executionDialog.isOpen}
        workflow={workflow}
        onClose={closeExecutionDialog}
        onExecute={(inputData) => void handleExecuteWorkflow(inputData)}
        loading={executionDialog.loading}
      />
    </div>
  );
};

export default WorkflowVisualizer;
