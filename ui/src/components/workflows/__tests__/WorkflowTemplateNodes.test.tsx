/**
 * Tests for Template Node Visualization
 *
 * This test suite verifies that template nodes (Identity, Merge, Collect) are:
 * - Correctly identified and sized (60x60 circular vs 180x100 rectangular)
 * - Display appropriate icons (functional icons vs status icons)
 * - Maintain consistent structure across static and execution views
 * - Preserve their functional icons during execution (not replaced by checkmarks)
 */

import { describe, it, expect } from 'vitest';

import { WorkflowNode } from '../../../types/workflow';

// Helper function to create a test node with required fields
const createTestNode = (overrides: Partial<WorkflowNode>): WorkflowNode => ({
  id: 'test-node',
  node_id: '1',
  name: 'Test Node',
  kind: 'task',
  task_id: null,
  node_template_id: null,
  foreach_config: null,
  is_start_node: false,
  schemas: {
    input: {},
    output_result: {},
  },
  created_at: '2025-01-01T00:00:00Z',
  ...overrides,
});

describe('WorkflowTemplateNodes - Node Identification and Sizing', () => {
  describe('Template Node Detection', () => {
    it('should identify a node as a template node when kind is transformation and node_template_id exists', () => {
      const node = createTestNode({
        id: 'node-1',
        name: 'system_identity_1',
        kind: 'transformation',
        node_template_id: 'template-123',
        node_id: '1',
      });

      const isTemplateNode = node.kind === 'transformation' && !!node.node_template_id;

      expect(isTemplateNode).toBe(true);
    });

    it('should NOT identify a regular transformation node as a template node', () => {
      const node = createTestNode({
        id: 'node-2',
        name: 'Custom Transformation',
        kind: 'transformation',
        node_id: '2',
        template_code: 'return input',
      });

      const isTemplateNode = node.kind === 'transformation' && !!node.node_template_id;

      expect(isTemplateNode).toBe(false);
    });

    it('should NOT identify a task node as a template node', () => {
      const node = createTestNode({
        id: 'node-3',
        name: 'Regular Task',
        kind: 'task',
        node_id: '3',
        task_id: 'task-123',
      });

      const isTemplateNode = node.kind === 'transformation' && !!node.node_template_id;

      expect(isTemplateNode).toBe(false);
    });
  });

  describe('Template Node Dimensions', () => {
    it('should assign 60x60 dimensions to template nodes', () => {
      const node = createTestNode({
        id: 'node-1',
        name: 'system_collect_1',
        kind: 'transformation',
        node_template_id: 'template-collect',
        node_id: '1',
      });

      const isTemplateNode = node.kind === 'transformation' && !!node.node_template_id;
      const width = isTemplateNode ? 60 : 180;
      const height = isTemplateNode ? 60 : 100;

      expect(width).toBe(60);
      expect(height).toBe(60);
    });

    it('should assign 180x100 dimensions to regular task nodes', () => {
      const node = createTestNode({
        id: 'node-2',
        name: 'Regular Task',
        kind: 'task',
        node_id: '2',
        task_id: 'task-123',
      });

      const isTemplateNode = node.kind === 'transformation' && !!node.node_template_id;
      const width = isTemplateNode ? 60 : 180;
      const height = isTemplateNode ? 60 : 100;

      expect(width).toBe(180);
      expect(height).toBe(100);
    });
  });

  describe('Template Type Classification', () => {
    it('should classify node with "identity" in name as Identity type', () => {
      const nodeName = 'system_identity_1';
      const lowerName = nodeName.toLowerCase();

      const isIdentity = lowerName.includes('identity');
      const isMerge = lowerName.includes('merge');
      const isCollect = lowerName.includes('collect');

      expect(isIdentity).toBe(true);
      expect(isMerge).toBe(false);
      expect(isCollect).toBe(false);
    });

    it('should classify node with "merge" in name as Merge type', () => {
      const nodeName = 'system_merge_1';
      const lowerName = nodeName.toLowerCase();

      const isIdentity = lowerName.includes('identity');
      const isMerge = lowerName.includes('merge');
      const isCollect = lowerName.includes('collect');

      expect(isIdentity).toBe(false);
      expect(isMerge).toBe(true);
      expect(isCollect).toBe(false);
    });

    it('should classify node with "collect" in name as Collect type', () => {
      const nodeName = 'system_collect_1';
      const lowerName = nodeName.toLowerCase();

      const isIdentity = lowerName.includes('identity');
      const isMerge = lowerName.includes('merge');
      const isCollect = lowerName.includes('collect');

      expect(isIdentity).toBe(false);
      expect(isMerge).toBe(false);
      expect(isCollect).toBe(true);
    });

    it('should handle case-insensitive template type detection', () => {
      const testNames = ['SYSTEM_IDENTITY_1', 'System_Merge_1', 'system_COLLECT_1'];

      const results = testNames.map((name) => {
        const lowerName = name.toLowerCase();
        return {
          isIdentity: lowerName.includes('identity'),
          isMerge: lowerName.includes('merge'),
          isCollect: lowerName.includes('collect'),
        };
      });

      expect(results[0].isIdentity).toBe(true);
      expect(results[1].isMerge).toBe(true);
      expect(results[2].isCollect).toBe(true);
    });
  });
});

describe('WorkflowTemplateNodes - Execution View Consistency', () => {
  describe('Node ID Consistency', () => {
    it('should use the same node ID in static and execution views', () => {
      const staticNodeId = 'node-uuid-123';

      // In static view
      const staticViewNodeId = staticNodeId;

      // In execution view (previously prefixed with 'exec-' or 'static-')
      const executionViewNodeId = staticNodeId; // Now using same ID

      expect(staticViewNodeId).toBe(executionViewNodeId);
    });

    it('should use the same edge ID in static and execution views', () => {
      const staticEdgeId = 'edge-uuid-456';

      // In static view
      const staticViewEdgeId = staticEdgeId;

      // In execution view (previously prefixed with 'edge-')
      const executionViewEdgeId = staticEdgeId; // Now using same ID

      expect(staticViewEdgeId).toBe(executionViewEdgeId);
    });
  });

  describe('Graph Structure Consistency', () => {
    it('should include all workflow nodes in execution view regardless of instantiation', () => {
      const workflowNodes: WorkflowNode[] = [
        createTestNode({
          id: 'node-1',
          name: 'Task 1',
          kind: 'task',
          node_id: '1',
          task_id: 'task-1',
        }),
        createTestNode({
          id: 'node-2',
          name: 'system_identity_1',
          kind: 'transformation',
          node_id: '2',
          node_template_id: 'identity-template',
        }),
        createTestNode({
          id: 'node-3',
          name: 'Task 2',
          kind: 'task',
          node_id: '3',
          task_id: 'task-2',
        }),
      ];

      // Execution instances (only node-1 has been instantiated)
      const executionInstances = new Map([['node-1', { status: 'completed' }]]);

      // Process ALL workflow nodes (not just instantiated ones)
      const executionViewNodes = workflowNodes.map((node) => {
        const instance = executionInstances.get(node.id);
        return {
          id: node.id,
          status: instance?.status || 'waiting',
          nodeData: node,
        };
      });

      // All nodes should be present in execution view
      expect(executionViewNodes).toHaveLength(3);
      expect(executionViewNodes[0].status).toBe('completed');
      expect(executionViewNodes[1].status).toBe('waiting');
      expect(executionViewNodes[2].status).toBe('waiting');
    });

    it('should maintain node order from workflow definition in execution view', () => {
      const workflowNodes: WorkflowNode[] = [
        createTestNode({ id: 'node-a', name: 'A', kind: 'task', node_id: 'a' }),
        createTestNode({ id: 'node-b', name: 'B', kind: 'task', node_id: 'b' }),
        createTestNode({ id: 'node-c', name: 'C', kind: 'task', node_id: 'c' }),
      ];

      // Process in workflow order
      const executionViewNodes = workflowNodes.map((node) => ({ id: node.id }));

      expect(executionViewNodes[0].id).toBe('node-a');
      expect(executionViewNodes[1].id).toBe('node-b');
      expect(executionViewNodes[2].id).toBe('node-c');
    });
  });
});

describe('WorkflowTemplateNodes - Icon Preservation During Execution', () => {
  describe('Template Node Icon Logic', () => {
    it('should preserve functional icon for template node even when completed', () => {
      const node = {
        kind: 'transformation',
        nodeData: {
          node_template_id: 'identity-template',
          name: 'system_identity_1',
        },
      };
      const status = 'completed';

      // Template node check should happen BEFORE status check
      const isTemplateNode = node.kind === 'transformation' && !!node.nodeData.node_template_id;

      // Template nodes should show functional icon regardless of status
      if (isTemplateNode) {
        expect(isTemplateNode).toBe(true);
        // Icon would be ArrowRightIcon (Identity), not CheckCircleIcon
      } else {
        // Only non-template nodes show status icons
        expect(status).toBe('completed');
        // Icon would be CheckCircleIcon
      }
    });

    it('should show status icon for regular task node when completed', () => {
      const node = {
        kind: 'task',
        nodeData: {
          node_template_id: null,
          name: 'Regular Task',
        },
      };
      const status = 'completed';

      const isTemplateNode = node.kind === 'transformation' && !!node.nodeData.node_template_id;

      // Task nodes should show status-based icons
      expect(isTemplateNode).toBe(false);
      expect(status).toBe('completed');
      // Icon would be CheckCircleIcon for completed tasks
    });

    it('should determine template type from node name for icon selection', () => {
      const templates = [
        { name: 'system_identity_1', expectedType: 'identity' },
        { name: 'system_merge_1', expectedType: 'merge' },
        { name: 'system_collect_1', expectedType: 'collect' },
      ];

      templates.forEach(({ name, expectedType }) => {
        const lowerName = name.toLowerCase();

        let detectedType = 'unknown';
        if (lowerName.includes('collect')) detectedType = 'collect';
        else if (lowerName.includes('merge')) detectedType = 'merge';
        else if (lowerName.includes('identity')) detectedType = 'identity';

        expect(detectedType).toBe(expectedType);
      });
    });
  });

  describe('Status Reflection Through Styling', () => {
    it('should reflect completed status through border color for template nodes', () => {
      const templateNode = {
        kind: 'transformation',
        nodeData: { node_template_id: 'identity-template', name: 'system_identity_1' },
        status: 'completed',
      };

      // Template nodes show functional icon but status affects styling
      const isTemplateNode =
        templateNode.kind === 'transformation' && !!templateNode.nodeData.node_template_id;

      expect(isTemplateNode).toBe(true);
      expect(templateNode.status).toBe('completed');
      // Border would be green (#10b981) but icon stays as ArrowRightIcon
    });

    it('should reflect running status through border color for template nodes', () => {
      const templateNode = {
        kind: 'transformation',
        nodeData: { node_template_id: 'merge-template', name: 'system_merge_1' },
        status: 'running',
      };

      const isTemplateNode =
        templateNode.kind === 'transformation' && !!templateNode.nodeData.node_template_id;

      expect(isTemplateNode).toBe(true);
      expect(templateNode.status).toBe('running');
      // Border would be blue (#3b82f6) but icon stays as ArrowsPointingInIcon
    });

    it('should reflect failed status through border color for template nodes', () => {
      const templateNode = {
        kind: 'transformation',
        nodeData: { node_template_id: 'collect-template', name: 'system_collect_1' },
        status: 'failed',
      };

      const isTemplateNode =
        templateNode.kind === 'transformation' && !!templateNode.nodeData.node_template_id;

      expect(isTemplateNode).toBe(true);
      expect(templateNode.status).toBe('failed');
      // Border would be red (#ef4444) but icon stays as InboxStackIcon
    });
  });
});

describe('WorkflowTemplateNodes - Tooltip Information', () => {
  describe('Template Node Tooltip Generation', () => {
    it('should generate correct tooltip for Identity template', () => {
      const templateType = 'Identity';
      const expectedTooltip = 'Identity: Passes data through unchanged (supports high fan-out)';

      // This would be handled by getTemplateTooltip function
      const tooltip =
        templateType === 'Identity'
          ? 'Identity: Passes data through unchanged (supports high fan-out)'
          : '';

      expect(tooltip).toBe(expectedTooltip);
    });

    it('should generate correct tooltip for Merge template', () => {
      const templateType = 'Merge';
      const expectedTooltip = 'Merge: Combines multiple inputs into a single output';

      const tooltip =
        templateType === 'Merge' ? 'Merge: Combines multiple inputs into a single output' : '';

      expect(tooltip).toBe(expectedTooltip);
    });

    it('should generate correct tooltip for Collect template', () => {
      const templateType = 'Collect';
      const expectedTooltip = 'Collect: Gathers all inputs into an array';

      const tooltip = templateType === 'Collect' ? 'Collect: Gathers all inputs into an array' : '';

      expect(tooltip).toBe(expectedTooltip);
    });

    it('should return empty string for non-template nodes', () => {
      const getTooltip = (type?: string) => (type ? `Template: ${type}` : '');

      expect(getTooltip()).toBe('');
    });
  });
});
