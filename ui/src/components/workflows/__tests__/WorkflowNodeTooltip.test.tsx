import { render, screen, act, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import { Workflow } from '../../../types/workflow';
import WorkflowVisualizerReaflow from '../WorkflowVisualizerReaflow';

// Mock react-router
vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}));

// Mock dependencies
vi.mock('../../../services/backendApi');
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
    runSafe: async (promise: Promise<any>) => {
      try {
        const result = await promise;
        return [result, null];
      } catch (error) {
        return [null, error];
      }
    },
  }),
}));

// Mock react-zoom-pan-pinch
vi.mock('react-zoom-pan-pinch', () => ({
  TransformWrapper: ({ children }: any) => (
    <div data-testid="transform-wrapper">
      {typeof children === 'function'
        ? children({
            zoomIn: vi.fn(),
            zoomOut: vi.fn(),
            resetTransform: vi.fn(),
          })
        : children}
    </div>
  ),
  TransformComponent: ({ children }: any) => (
    <div data-testid="transform-component">{children}</div>
  ),
}));

// Track the last rendered node data for tooltip assertions
let lastNodeData: Record<string, any> = {};

// Mock reaflow - expose node data so we can verify taskDescription is passed through
vi.mock('reaflow', () => ({
  Canvas: ({ nodes, edges, node, edge, onNodeClick }: any) => (
    <div data-testid="reaflow-canvas">
      {nodes.map((n: any) => {
        // Store the node data for inspection
        lastNodeData[n.id] = n.data;
        return (
          <div key={n.id} data-testid={`node-${n.id}`}>
            {node?.({
              properties: n,
              key: n.id,
              onClick: onNodeClick,
            })}
          </div>
        );
      })}
      {edges.map((e: any) => (
        <div key={e.id} data-testid={`edge-${e.id}`}>
          {edge?.({ ...e, key: e.id })}
        </div>
      ))}
    </div>
  ),
  MarkerArrow: () => <div data-testid="marker-arrow" />,
  Edge: ({ children }: any) => <div data-testid="edge">{children}</div>,
  CanvasPosition: {
    CENTER: 'CENTER',
  },
}));

// Mock WorkflowNode to expose tooltip-relevant props
vi.mock('../WorkflowNode', () => ({
  default: (props: any) => {
    const taskDesc = props.properties?.data?.taskDescription;
    return (
      <div
        data-testid={`workflow-node-${props.properties?.id}`}
        data-task-description={taskDesc || ''}
      >
        {props.properties?.text}
        {taskDesc && <span data-testid={`tooltip-desc-${props.properties?.id}`}>{taskDesc}</span>}
      </div>
    );
  },
  getNodeHeight: (_text: string, _baseWidth: number, baseHeight: number) => baseHeight,
}));

// Mock WorkflowExecutionDialog
vi.mock('../WorkflowExecutionDialog', () => ({
  WorkflowExecutionDialog: ({ isOpen }: any) =>
    isOpen ? <div data-testid="execution-dialog">Execution Dialog</div> : null,
}));

// Mock WorkflowExecutionReaflow
vi.mock('../WorkflowExecutionReaflow', () => ({
  default: ({ onClose }: any) => (
    <div data-testid="execution-view">
      <button onClick={onClose}>Close Execution View</button>
    </div>
  ),
}));

const WORKFLOW_ID = 'workflow-tooltip-test';
const TASK_UUID_1 = 'task-uuid-1';
const TASK_UUID_2 = 'task-uuid-2';
const TIMESTAMP = '2025-01-20T00:00:00Z';
const IP_ANALYSIS_TASK_NAME = 'IP Analysis Task';

const createWorkflow = (): Workflow => ({
  id: WORKFLOW_ID,
  tenant_id: 'test-tenant',
  name: 'Tooltip Test Workflow',
  description: 'A workflow to test tooltip behavior',
  is_dynamic: false,
  io_schema: {
    input: { type: 'object', properties: {} },
    output: { type: 'object', properties: {} },
  },
  status: 'enabled',
  created_by: 'test-user',
  created_at: TIMESTAMP,
  planner_id: null,
  nodes: [
    {
      id: 'node-1',
      node_id: 'n-task-1',
      kind: 'task',
      name: IP_ANALYSIS_TASK_NAME,
      task_id: TASK_UUID_1,
      node_template_id: null,
      foreach_config: null,
      is_start_node: false,
      schemas: { input: { type: 'object' }, output_result: { type: 'object' } },
      created_at: TIMESTAMP,
    },
    {
      id: 'node-2',
      node_id: 'n-task-2',
      kind: 'task',
      name: 'Alert Summary',
      task_id: TASK_UUID_2,
      node_template_id: null,
      foreach_config: null,
      is_start_node: false,
      schemas: { input: { type: 'object' }, output_result: { type: 'object' } },
      created_at: TIMESTAMP,
    },
    {
      id: 'node-3',
      node_id: 'n-transform-1',
      kind: 'transformation',
      name: 'system_merge',
      task_id: null,
      node_template_id: 'template-merge',
      foreach_config: null,
      is_start_node: false,
      schemas: { input: { type: 'object' }, output_result: { type: 'object' } },
      created_at: TIMESTAMP,
    },
  ],
  edges: [
    {
      id: 'edge-1',
      edge_id: 'e1',
      from_node_uuid: 'node-1',
      to_node_uuid: 'node-3',
      alias: 'result1',
      created_at: TIMESTAMP,
    },
    {
      id: 'edge-2',
      edge_id: 'e2',
      from_node_uuid: 'node-2',
      to_node_uuid: 'node-3',
      alias: 'result2',
      created_at: TIMESTAMP,
    },
  ],
});

describe('Workflow Node Tooltips', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    lastNodeData = {};
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Task Description Fetching', () => {
    it('should fetch task descriptions and pass them to nodes', async () => {
      vi.mocked(backendApi.getTasks).mockResolvedValue({
        tasks: [
          {
            id: TASK_UUID_1,
            name: IP_ANALYSIS_TASK_NAME,
            description: 'Analyzes IP addresses for threat intelligence',
          },
          {
            id: TASK_UUID_2,
            name: 'Alert Summary',
            description: 'Generates alert summaries',
          },
        ] as any,
        total: 2,
      });

      render(<WorkflowVisualizerReaflow workflow={createWorkflow()} />);

      // Wait for the async task descriptions fetch to complete
      await waitFor(() => {
        expect(backendApi.getTasks).toHaveBeenCalledWith({ limit: 100 });
      });

      // Wait for the descriptions to be rendered via the mock
      await waitFor(() => {
        expect(screen.getByTestId('tooltip-desc-node-1')).toHaveTextContent(
          'Analyzes IP addresses for threat intelligence'
        );
        expect(screen.getByTestId('tooltip-desc-node-2')).toHaveTextContent(
          'Generates alert summaries'
        );
      });
    });

    it('should not pass taskDescription to template/transformation nodes', async () => {
      vi.mocked(backendApi.getTasks).mockResolvedValue({
        tasks: [
          {
            id: TASK_UUID_1,
            name: IP_ANALYSIS_TASK_NAME,
            description: 'Analyzes IP addresses',
          },
        ] as any,
        total: 1,
      });

      render(<WorkflowVisualizerReaflow workflow={createWorkflow()} />);

      await waitFor(() => {
        expect(backendApi.getTasks).toHaveBeenCalled();
      });

      // Template node should not have a tooltip description
      await waitFor(() => {
        const templateNode = screen.getByTestId('workflow-node-node-3');
        expect(templateNode.getAttribute('data-task-description')).toBe('');
      });
    });

    it('should handle getTasks API failure gracefully', async () => {
      vi.mocked(backendApi.getTasks).mockRejectedValue(new Error('API Error'));

      // Should render without errors even when fetch fails
      render(<WorkflowVisualizerReaflow workflow={createWorkflow()} />);

      await waitFor(() => {
        expect(backendApi.getTasks).toHaveBeenCalled();
      });

      // Nodes should still render, just without descriptions
      expect(screen.getByTestId('workflow-node-node-1')).toBeInTheDocument();
      expect(screen.getByTestId('workflow-node-node-2')).toBeInTheDocument();

      // No tooltip descriptions should be present
      expect(screen.queryByTestId('tooltip-desc-node-1')).not.toBeInTheDocument();
      expect(screen.queryByTestId('tooltip-desc-node-2')).not.toBeInTheDocument();
    });

    it('should not fetch tasks when workflow has no task nodes', async () => {
      const transformOnlyWorkflow: Workflow = {
        ...createWorkflow(),
        nodes: [
          {
            id: 'node-t1',
            node_id: 'n-t1',
            kind: 'transformation',
            name: 'system_identity',
            task_id: null,
            node_template_id: 'template-identity',
            foreach_config: null,
            is_start_node: false,
            schemas: { input: { type: 'object' }, output_result: { type: 'object' } },
            created_at: TIMESTAMP,
          },
        ],
        edges: [],
      };

      render(<WorkflowVisualizerReaflow workflow={transformOnlyWorkflow} />);

      // Give time for any async calls
      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });

      // getTasks should not have been called since there are no task nodes
      expect(backendApi.getTasks).not.toHaveBeenCalled();
    });

    it('should only include descriptions for tasks present in the workflow', async () => {
      vi.mocked(backendApi.getTasks).mockResolvedValue({
        tasks: [
          {
            id: TASK_UUID_1,
            name: IP_ANALYSIS_TASK_NAME,
            description: 'Analyzes IP addresses',
          },
          {
            id: 'unrelated-task-id',
            name: 'Unrelated Task',
            description: 'This task is not in the workflow',
          },
        ] as any,
        total: 2,
      });

      render(<WorkflowVisualizerReaflow workflow={createWorkflow()} />);

      await waitFor(() => {
        expect(backendApi.getTasks).toHaveBeenCalled();
      });

      // The unrelated task description should NOT appear
      await waitFor(() => {
        expect(screen.getByTestId('tooltip-desc-node-1')).toHaveTextContent(
          'Analyzes IP addresses'
        );
      });

      // Node 2 had no matching description in the response
      expect(screen.queryByTestId('tooltip-desc-node-2')).not.toBeInTheDocument();
    });
  });

  describe('Node Data Structure', () => {
    it('should include taskDescription in node data for task nodes', async () => {
      vi.mocked(backendApi.getTasks).mockResolvedValue({
        tasks: [
          {
            id: TASK_UUID_1,
            name: IP_ANALYSIS_TASK_NAME,
            description: 'Threat intel enrichment',
          },
        ] as any,
        total: 1,
      });

      render(<WorkflowVisualizerReaflow workflow={createWorkflow()} />);

      await waitFor(() => {
        // Verify the data passed to reaflow nodes includes taskDescription
        expect(lastNodeData['node-1']?.taskDescription).toBe('Threat intel enrichment');
      });
    });

    it('should set taskDescription to undefined for nodes without task_id', async () => {
      vi.mocked(backendApi.getTasks).mockResolvedValue({
        tasks: [] as any,
        total: 0,
      });

      render(<WorkflowVisualizerReaflow workflow={createWorkflow()} />);

      await waitFor(() => {
        expect(backendApi.getTasks).toHaveBeenCalled();
      });

      // Template node (node-3) has no task_id, so taskDescription should be undefined
      await act(async () => {
        await new Promise((r) => setTimeout(r, 50));
      });
      expect(lastNodeData['node-3']?.taskDescription).toBeUndefined();
    });
  });
});
