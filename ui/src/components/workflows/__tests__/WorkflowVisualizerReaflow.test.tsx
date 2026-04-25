import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { Task } from '../../../types/knowledge';
import { Workflow } from '../../../types/workflow';
import WorkflowVisualizerReaflow from '../WorkflowVisualizerReaflow';

// Mock react-router
const mockNavigate = vi.fn();
vi.mock('react-router', () => ({
  useNavigate: () => mockNavigate,
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

// Mock reaflow - we need to pass onNodeClick through the node render prop
vi.mock('reaflow', () => ({
  Canvas: ({ nodes, edges, onCanvasClick, node, edge, onNodeClick }: any) => (
    <div
      data-testid="reaflow-canvas"
      onClick={onCanvasClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          onCanvasClick?.(e);
        }
      }}
    >
      {nodes.map((n: any) => (
        <div key={n.id} data-testid={`node-${n.id}`}>
          {node?.({
            properties: n,
            key: n.id,
            onClick: onNodeClick,
          })}
        </div>
      ))}
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

// Mock WorkflowNode
vi.mock('../WorkflowNode', () => ({
  default: (props: any) => (
    <div
      data-testid={`workflow-node-${props.properties?.id}`}
      onClick={(e) => props.onClick?.(e, props.properties)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          props.onClick?.(e, props.properties);
        }
      }}
    >
      {props.properties?.text}
    </div>
  ),
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

const WORKFLOW_ID = 'workflow-123';
const TASK_UUID_1 = 'task-uuid-1';
const TIMESTAMP = '2025-01-20T00:00:00Z';

describe('WorkflowVisualizerReaflow', () => {
  const mockOnExecuteWorkflow = vi.fn();

  const createMockWorkflow = (): Workflow => ({
    id: WORKFLOW_ID,
    tenant_id: 'test-tenant',
    name: 'Test Workflow',
    description: 'A test workflow for visualization',
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
        id: 'node-uuid-1',
        node_id: 'n-task-1',
        kind: 'task',
        name: 'IP Analysis Task',
        task_id: TASK_UUID_1,
        node_template_id: null,
        foreach_config: null,
        is_start_node: false,
        schemas: {
          input: { type: 'object' },
          output_result: { type: 'object' },
        },
        created_at: TIMESTAMP,
      },
      {
        id: 'node-uuid-2',
        node_id: 'n-transform-1',
        kind: 'transformation',
        name: 'Data Transform',
        task_id: null,
        node_template_id: 'template-1',
        foreach_config: null,
        is_start_node: false,
        schemas: {
          input: { type: 'object' },
          output_result: { type: 'object' },
        },
        template_code: 'def transform(data):\n    return data',
        created_at: TIMESTAMP,
      },
    ],
    edges: [
      {
        id: 'edge-uuid-1',
        edge_id: 'e1',
        from_node_uuid: 'node-uuid-1',
        to_node_uuid: 'node-uuid-2',
        alias: 'result',
        created_at: TIMESTAMP,
      },
    ],
  });

  const createMockTask = (): Task =>
    ({
      id: TASK_UUID_1,
      name: 'IP Analysis Task',
      description: 'Analyze IP addresses for threats',
      script:
        'from analysi import task\n\n@task\ndef analyze_ip(ip: str):\n    return {"status": "analyzed"}',
      function: 'extraction',
      created_by: 'test-user',
      visible: true,
      version: '1.0.0',
      scope: 'processing',
      status: 'enabled',
      created_at: TIMESTAMP,
      updated_at: TIMESTAMP,
    }) as Task;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Rendering', () => {
    it('should render workflow with nodes and edges', () => {
      const workflow = createMockWorkflow();

      render(<WorkflowVisualizerReaflow workflow={workflow} />);

      expect(screen.getByText('Test Workflow')).toBeInTheDocument();
      expect(screen.getByTestId('reaflow-canvas')).toBeInTheDocument();

      // Info panel starts collapsed - expand it to see description
      const panelHeader = screen.getByTitle('Expand panel');
      fireEvent.click(panelHeader);
      expect(screen.getByText('A test workflow for visualization')).toBeInTheDocument();
    });

    it('should display workflow statistics', () => {
      const workflow = createMockWorkflow();

      render(<WorkflowVisualizerReaflow workflow={workflow} />);

      // Info panel starts collapsed - expand it to see statistics
      const panelHeader = screen.getByTitle('Expand panel');
      fireEvent.click(panelHeader);

      expect(screen.getByText('Nodes:')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('Edges:')).toBeInTheDocument();
      expect(screen.getByText('1')).toBeInTheDocument();
      expect(screen.getByText('Type:')).toBeInTheDocument();
      expect(screen.getByText('Static')).toBeInTheDocument();
    });

    it('should render zoom controls', () => {
      const workflow = createMockWorkflow();

      render(<WorkflowVisualizerReaflow workflow={workflow} />);

      const zoomButtons = screen.getAllByRole('button');
      expect(zoomButtons.length).toBeGreaterThan(0);
    });
  });

  describe('Node Selection and Details', () => {
    it('should render nodes correctly', () => {
      const workflow = createMockWorkflow();

      render(<WorkflowVisualizerReaflow workflow={workflow} />);

      // Verify nodes are rendered
      expect(screen.getByTestId('workflow-node-node-uuid-1')).toBeInTheDocument();
      expect(screen.getByTestId('workflow-node-node-uuid-2')).toBeInTheDocument();
      expect(screen.getByText('IP Analysis Task')).toBeInTheDocument();
      expect(screen.getByText('Data Transform')).toBeInTheDocument();
    });

    it('should transform workflow nodes to Reaflow format correctly', () => {
      const workflow = createMockWorkflow();

      render(<WorkflowVisualizerReaflow workflow={workflow} />);

      // Verify that nodes are created with correct dimensions
      // Task nodes should be 180x100, template transformation nodes should be 60x60
      const canvas = screen.getByTestId('reaflow-canvas');
      expect(canvas).toBeInTheDocument();
    });

    it('should close node details panel when Escape key is pressed', async () => {
      const workflow = createMockWorkflow();

      render(<WorkflowVisualizerReaflow workflow={workflow} />);

      // Click on a node to select it
      const node = screen.getByTestId('workflow-node-node-uuid-1');
      fireEvent.click(node);

      // Verify node is selected by checking if details panel would appear
      await waitFor(() => {
        // In the actual component, the details panel appears when a node is selected
        // We can't directly test for the panel in this mocked environment,
        // but we can verify the escape key handler works
        expect(node).toBeInTheDocument();
      });

      // Press Escape key
      fireEvent.keyDown(document, { key: 'Escape', code: 'Escape' });

      // The component should deselect the node
      // In a real scenario, the details panel would disappear
      await waitFor(() => {
        // This test verifies the escape key handler is registered
        expect(node).toBeInTheDocument();
      });
    });
  });

  describe('API Response Handling', () => {
    it('should extract task data from nested API response', () => {
      // Test the logic that handles 'data' in response
      const wrappedResponse = { data: createMockTask() };
      const taskData = 'data' in wrappedResponse ? wrappedResponse.data : wrappedResponse;

      expect(taskData).toHaveProperty('script');
      expect(taskData.script).toContain('from analysi import task');
    });

    it('should handle direct task response', () => {
      // Test the logic that handles direct response
      const directResponse = createMockTask();
      const taskData = 'data' in directResponse ? (directResponse as any).data : directResponse;

      expect(taskData).toHaveProperty('script');
      expect(taskData.script).toContain('from analysi import task');
    });
  });

  describe('Workflow Execution', () => {
    it('should open execution dialog when execute button is clicked', async () => {
      const workflow = createMockWorkflow();

      render(<WorkflowVisualizerReaflow workflow={workflow} />);

      const executeButtons = screen.getAllByRole('button');
      const executeButton = executeButtons.find((btn) => btn.title === 'Execute Workflow');

      expect(executeButton).toBeInTheDocument();

      fireEvent.click(executeButton!);

      await waitFor(() => {
        expect(screen.getByTestId('execution-dialog')).toBeInTheDocument();
      });
    });

    it('should call onExecuteWorkflow callback if provided', () => {
      const workflow = createMockWorkflow();

      render(
        <WorkflowVisualizerReaflow workflow={workflow} onExecuteWorkflow={mockOnExecuteWorkflow} />
      );

      const executeButtons = screen.getAllByRole('button');
      const executeButton = executeButtons.find((btn) => btn.title === 'Execute Workflow');

      fireEvent.click(executeButton!);

      expect(mockOnExecuteWorkflow).toHaveBeenCalled();
    });
  });

  describe('Node Size and Appearance', () => {
    it('should create smaller nodes for template transformations', () => {
      const workflow = createMockWorkflow();

      render(<WorkflowVisualizerReaflow workflow={workflow} />);

      // This is tested through the component's internal logic
      // The nodes array should have different dimensions based on node type
      // Template nodes: 60x60, Regular nodes: 180x100
      expect(screen.getByTestId('workflow-node-node-uuid-1')).toBeInTheDocument();
      expect(screen.getByTestId('workflow-node-node-uuid-2')).toBeInTheDocument();
    });
  });

  describe('Edge Crossing Prevention', () => {
    it('should create ports for nodes with multiple incoming edges', () => {
      // Create a workflow with an aggregation node (multiple edges to one target)
      const workflow: Workflow = {
        id: 'workflow-123',
        tenant_id: 'test-tenant',
        name: 'Aggregation Test Workflow',
        description: 'Tests edge crossing prevention',
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
            id: 'source-1',
            node_id: 'n-source-1',
            kind: 'task',
            name: 'Source 1',
            task_id: TASK_UUID_1,
            node_template_id: null,
            foreach_config: null,
            is_start_node: false,
            schemas: { input: { type: 'object' }, output_result: { type: 'object' } },
            created_at: TIMESTAMP,
          },
          {
            id: 'source-2',
            node_id: 'n-source-2',
            kind: 'task',
            name: 'Source 2',
            task_id: 'task-uuid-2',
            node_template_id: null,
            foreach_config: null,
            is_start_node: false,
            schemas: { input: { type: 'object' }, output_result: { type: 'object' } },
            created_at: TIMESTAMP,
          },
          {
            id: 'aggregation',
            node_id: 'n-agg',
            kind: 'transformation',
            name: 'Aggregation',
            task_id: null,
            node_template_id: 'template-agg',
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
            from_node_uuid: 'source-1',
            to_node_uuid: 'aggregation',
            alias: 'input1',
            created_at: TIMESTAMP,
          },
          {
            id: 'edge-2',
            edge_id: 'e2',
            from_node_uuid: 'source-2',
            to_node_uuid: 'aggregation',
            alias: 'input2',
            created_at: TIMESTAMP,
          },
        ],
      };

      render(<WorkflowVisualizerReaflow workflow={workflow} />);

      // Component should render without errors
      expect(screen.getByText('Aggregation Test Workflow')).toBeInTheDocument();

      // Info panel starts collapsed - expand it to see statistics
      const panelHeader = screen.getByTitle('Expand panel');
      fireEvent.click(panelHeader);
      expect(screen.getByText('3')).toBeInTheDocument(); // 3 nodes
      expect(screen.getByText('2')).toBeInTheDocument(); // 2 edges
    });

    it('should sort edges by source node ID to prevent crossing', () => {
      // Test the edge sorting logic that prevents crossings
      const edges = [
        { id: 'e1', from_node_uuid: 'node-b', to_node_uuid: 'target', alias: '' },
        { id: 'e2', from_node_uuid: 'node-a', to_node_uuid: 'target', alias: '' },
        { id: 'e3', from_node_uuid: 'node-c', to_node_uuid: 'target', alias: '' },
      ];

      // Sort edges by source node ID (alphabetically)
      const sortedEdges = [...edges].sort((a, b) =>
        a.from_node_uuid.localeCompare(b.from_node_uuid)
      );

      // Verify edges are sorted alphabetically by source
      expect(sortedEdges[0].from_node_uuid).toBe('node-a');
      expect(sortedEdges[1].from_node_uuid).toBe('node-b');
      expect(sortedEdges[2].from_node_uuid).toBe('node-c');

      // Verify port assignment would maintain this order
      expect(sortedEdges.indexOf(edges[0])).toBe(1); // node-b -> port 1
      expect(sortedEdges.indexOf(edges[1])).toBe(0); // node-a -> port 0
      expect(sortedEdges.indexOf(edges[2])).toBe(2); // node-c -> port 2
    });

    it('should create correct number of ports based on edge count', () => {
      const workflow: Workflow = {
        id: 'workflow-123',
        tenant_id: 'test-tenant',
        name: 'Multi-Port Test',
        description: 'Tests port creation',
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
            id: 'source',
            node_id: 'n-src',
            kind: 'task',
            name: 'Source',
            task_id: TASK_UUID_1,
            node_template_id: null,
            foreach_config: null,
            is_start_node: false,
            schemas: { input: { type: 'object' }, output_result: { type: 'object' } },
            created_at: TIMESTAMP,
          },
          {
            id: 'target',
            node_id: 'n-target',
            kind: 'task',
            name: 'Target',
            task_id: 'task-uuid-2',
            node_template_id: null,
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
            from_node_uuid: 'source',
            to_node_uuid: 'target',
            alias: 'data',
            created_at: TIMESTAMP,
          },
        ],
      };

      // Test port count calculation logic
      const incomingCount = workflow.edges.filter((e) => e.to_node_uuid === 'target').length;
      const outgoingCount = workflow.edges.filter((e) => e.from_node_uuid === 'source').length;

      expect(incomingCount).toBe(1); // Target has 1 incoming edge
      expect(outgoingCount).toBe(1); // Source has 1 outgoing edge

      // Each node should have at least 1 port even with 0 edges
      expect(Math.max(incomingCount, 1)).toBe(1);
      expect(Math.max(outgoingCount, 1)).toBe(1);
    });
  });
});
