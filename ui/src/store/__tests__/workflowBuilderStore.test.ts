/**
 * Tests for WorkflowBuilderStore
 *
 * Covers undo/redo, merge node insertion, and edge operations.
 */

import { describe, it, expect, beforeEach } from 'vitest';

import { useWorkflowBuilderStore } from '../workflowBuilderStore';

describe('WorkflowBuilderStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useWorkflowBuilderStore.getState().reset();
  });

  describe('Node Operations', () => {
    it('should add a node', () => {
      const store = useWorkflowBuilderStore.getState();
      store.addNode({
        id: 'node-1',
        text: 'Task A',
        kind: 'task',
        taskId: 'task-a',
      });

      const state = useWorkflowBuilderStore.getState();
      expect(state.nodes).toHaveLength(1);
      expect(state.nodes[0].id).toBe('node-1');
      expect(state.isDirty).toBe(true);
    });

    it('should remove a node and its connected edges', () => {
      const store = useWorkflowBuilderStore.getState();

      // Add two nodes
      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      store.addNode({ id: 'node-2', text: 'B', kind: 'task' });
      store.addEdge('node-1', 'node-2');

      // Remove node-1
      store.removeNode('node-1');

      const state = useWorkflowBuilderStore.getState();
      expect(state.nodes).toHaveLength(1);
      expect(state.nodes[0].id).toBe('node-2');
      expect(state.edges).toHaveLength(0); // Edge should be removed too
    });
  });

  describe('Edge Operations', () => {
    it('should add an edge between nodes', () => {
      const store = useWorkflowBuilderStore.getState();

      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      store.addNode({ id: 'node-2', text: 'B', kind: 'task' });
      store.addEdge('node-1', 'node-2');

      const state = useWorkflowBuilderStore.getState();
      expect(state.edges).toHaveLength(1);
      expect(state.edges[0].from).toBe('node-1');
      expect(state.edges[0].to).toBe('node-2');
    });

    it('should prevent duplicate edges', () => {
      const store = useWorkflowBuilderStore.getState();

      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      store.addNode({ id: 'node-2', text: 'B', kind: 'task' });
      store.addEdge('node-1', 'node-2');
      store.addEdge('node-1', 'node-2'); // Duplicate

      const state = useWorkflowBuilderStore.getState();
      expect(state.edges).toHaveLength(1);
    });

    it('should prevent self-loops', () => {
      const store = useWorkflowBuilderStore.getState();

      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      store.addEdge('node-1', 'node-1'); // Self-loop

      const state = useWorkflowBuilderStore.getState();
      expect(state.edges).toHaveLength(0);
    });
  });

  describe('Merge Node Auto-Creation', () => {
    it('should create a merge node when fan-in detected', () => {
      const store = useWorkflowBuilderStore.getState();

      // Create: A -> C, then add B -> C (fan-in)
      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'B', text: 'B', kind: 'task' });
      store.addNode({ id: 'C', text: 'C', kind: 'task' });
      store.addEdge('A', 'C'); // First edge
      store.addEdge('B', 'C'); // Fan-in triggers merge node

      const state = useWorkflowBuilderStore.getState();

      // Should have 4 nodes (A, B, C, merge)
      expect(state.nodes).toHaveLength(4);
      const mergeNode = state.nodes.find(
        (n) => n.kind === 'transformation' && n.nodeTemplateId === 'merge'
      );
      expect(mergeNode).toBeDefined();

      // Should have 3 edges: A->merge, B->merge, merge->C
      expect(state.edges).toHaveLength(3);
      expect(state.edges.some((e) => e.from === 'A' && e.to === mergeNode!.id)).toBe(true);
      expect(state.edges.some((e) => e.from === 'B' && e.to === mergeNode!.id)).toBe(true);
      expect(state.edges.some((e) => e.from === mergeNode!.id && e.to === 'C')).toBe(true);
    });

    it('should connect to existing merge node when adding third input', () => {
      const store = useWorkflowBuilderStore.getState();

      // Create: A, B -> merge -> C
      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'B', text: 'B', kind: 'task' });
      store.addNode({ id: 'C', text: 'C', kind: 'task' });
      store.addNode({ id: 'D', text: 'D', kind: 'task' });
      store.addEdge('A', 'C'); // First edge
      store.addEdge('B', 'C'); // Creates merge node

      // Get merge node ID
      let state = useWorkflowBuilderStore.getState();
      const mergeNode = state.nodes.find(
        (n) => n.kind === 'transformation' && n.nodeTemplateId === 'merge'
      );

      // Add D -> C (should connect to existing merge)
      store.addEdge('D', 'C');

      state = useWorkflowBuilderStore.getState();

      // Should still have only one merge node (not two)
      const mergeNodes = state.nodes.filter(
        (n) => n.kind === 'transformation' && n.nodeTemplateId === 'merge'
      );
      expect(mergeNodes).toHaveLength(1);

      // D should connect to the merge node
      expect(state.edges.some((e) => e.from === 'D' && e.to === mergeNode!.id)).toBe(true);
    });

    it('should allow direct connection to merge node without creating nested merge', () => {
      const store = useWorkflowBuilderStore.getState();

      // Manually create a merge node
      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'B', text: 'B', kind: 'task' });
      store.addNode({
        id: 'merge-1',
        text: 'Merge',
        kind: 'transformation',
        nodeTemplateId: 'merge',
      });
      store.addNode({ id: 'C', text: 'C', kind: 'task' });

      // Connect A and B to merge
      store.addEdge('A', 'merge-1');
      store.addEdge('B', 'merge-1');
      store.addEdge('merge-1', 'C');

      // Now add D directly targeting the merge node
      store.addNode({ id: 'D', text: 'D', kind: 'task' });
      store.addEdge('D', 'merge-1');

      const state = useWorkflowBuilderStore.getState();

      // Should NOT create a new merge node
      const mergeNodes = state.nodes.filter(
        (n) => n.kind === 'transformation' && n.nodeTemplateId === 'merge'
      );
      expect(mergeNodes).toHaveLength(1);

      // D should be connected to the existing merge node
      expect(state.edges.some((e) => e.from === 'D' && e.to === 'merge-1')).toBe(true);
    });

    it('should prevent duplicate edge to merge node', () => {
      const store = useWorkflowBuilderStore.getState();

      // Create merge scenario
      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'B', text: 'B', kind: 'task' });
      store.addNode({ id: 'C', text: 'C', kind: 'task' });
      store.addEdge('A', 'C');
      store.addEdge('B', 'C'); // Creates merge

      let state = useWorkflowBuilderStore.getState();
      const mergeNode = state.nodes.find((n) => n.nodeTemplateId === 'merge');
      const edgeCountBefore = state.edges.length;

      // Try to add duplicate: A -> C again (should try to connect A to merge, but already exists)
      store.addEdge('A', 'C');

      state = useWorkflowBuilderStore.getState();
      expect(state.edges.length).toBe(edgeCountBefore); // No new edge added

      // Try direct duplicate to merge
      store.addEdge('A', mergeNode!.id);
      state = useWorkflowBuilderStore.getState();
      expect(state.edges.length).toBe(edgeCountBefore); // Still no new edge
    });

    it('should handle multiple independent merge points', () => {
      const store = useWorkflowBuilderStore.getState();

      // Create two separate fan-in scenarios
      // Group 1: A, B -> merge1 -> C
      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'B', text: 'B', kind: 'task' });
      store.addNode({ id: 'C', text: 'C', kind: 'task' });
      store.addEdge('A', 'C');
      store.addEdge('B', 'C');

      // Group 2: D, E -> merge2 -> F
      store.addNode({ id: 'D', text: 'D', kind: 'task' });
      store.addNode({ id: 'E', text: 'E', kind: 'task' });
      store.addNode({ id: 'F', text: 'F', kind: 'task' });
      store.addEdge('D', 'F');
      store.addEdge('E', 'F');

      const state = useWorkflowBuilderStore.getState();

      // Should have 2 merge nodes
      const mergeNodes = state.nodes.filter((n) => n.nodeTemplateId === 'merge');
      expect(mergeNodes).toHaveLength(2);

      // Each merge should have exactly one outgoing edge
      for (const merge of mergeNodes) {
        const outgoing = state.edges.filter((e) => e.from === merge.id);
        expect(outgoing).toHaveLength(1);
      }
    });

    it('should create merge when connecting to node downstream of existing merge', () => {
      const store = useWorkflowBuilderStore.getState();

      // Create: A, B -> merge -> C -> D
      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'B', text: 'B', kind: 'task' });
      store.addNode({ id: 'C', text: 'C', kind: 'task' });
      store.addNode({ id: 'D', text: 'D', kind: 'task' });
      store.addEdge('A', 'C');
      store.addEdge('B', 'C'); // Creates first merge
      store.addEdge('C', 'D');

      // Now add E -> D (fan-in to D, which is downstream of first merge)
      store.addNode({ id: 'E', text: 'E', kind: 'task' });
      store.addEdge('E', 'D');

      const state = useWorkflowBuilderStore.getState();

      // Should have 2 merge nodes now
      const mergeNodes = state.nodes.filter((n) => n.nodeTemplateId === 'merge');
      expect(mergeNodes).toHaveLength(2);

      // E should connect to second merge, not directly to D
      const edgeFromE = state.edges.find((e) => e.from === 'E');
      expect(edgeFromE).toBeDefined();
      expect(mergeNodes.some((m) => m.id === edgeFromE!.to)).toBe(true);
    });

    it('should handle fan-in when first input is from transformation node', () => {
      const store = useWorkflowBuilderStore.getState();

      // Create: Transform -> C, then A -> C
      store.addNode({
        id: 'transform-1',
        text: 'Identity',
        kind: 'transformation',
        nodeTemplateId: 'identity',
      });
      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'C', text: 'C', kind: 'task' });
      store.addEdge('transform-1', 'C');
      store.addEdge('A', 'C'); // Fan-in with non-merge transformation

      const state = useWorkflowBuilderStore.getState();

      // Should create a merge node (identity is not a merge)
      const mergeNodes = state.nodes.filter((n) => n.nodeTemplateId === 'merge');
      expect(mergeNodes).toHaveLength(1);

      // Both transform-1 and A should connect to merge
      expect(state.edges.some((e) => e.from === 'transform-1' && e.to === mergeNodes[0].id)).toBe(
        true
      );
      expect(state.edges.some((e) => e.from === 'A' && e.to === mergeNodes[0].id)).toBe(true);
    });
  });

  describe('Undo/Redo', () => {
    it('should undo a single node addition', () => {
      const store = useWorkflowBuilderStore.getState();

      // Start fresh
      expect(store.nodes).toHaveLength(0);

      // Add a node
      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(1);

      // Undo should remove the node
      store.undo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(0);
    });

    it('should undo exactly one step, not two', () => {
      const store = useWorkflowBuilderStore.getState();

      // Add three nodes
      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      store.addNode({ id: 'node-2', text: 'B', kind: 'task' });
      store.addNode({ id: 'node-3', text: 'C', kind: 'task' });

      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(3);

      // Undo once - should have 2 nodes
      store.undo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(2);
      expect(useWorkflowBuilderStore.getState().nodes.map((n) => n.id)).toEqual([
        'node-1',
        'node-2',
      ]);

      // Undo again - should have 1 node
      store.undo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(1);
      expect(useWorkflowBuilderStore.getState().nodes.map((n) => n.id)).toEqual(['node-1']);

      // Undo again - should have 0 nodes
      store.undo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(0);
    });

    it('should redo after undo', () => {
      const store = useWorkflowBuilderStore.getState();

      // Add two nodes
      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      store.addNode({ id: 'node-2', text: 'B', kind: 'task' });

      // Undo
      store.undo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(1);

      // Redo
      store.redo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(2);
    });

    it('should clear redo history when new action is performed', () => {
      const store = useWorkflowBuilderStore.getState();

      // Add two nodes
      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      store.addNode({ id: 'node-2', text: 'B', kind: 'task' });

      // Undo
      store.undo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(1);
      expect(useWorkflowBuilderStore.getState().canRedo()).toBe(true);

      // Perform new action
      store.addNode({ id: 'node-3', text: 'C', kind: 'task' });

      // Redo should no longer be available (history was cleared)
      // The new node should be in place
      const state = useWorkflowBuilderStore.getState();
      expect(state.nodes).toHaveLength(2);
      expect(state.nodes.map((n) => n.id)).toEqual(['node-1', 'node-3']);
    });

    it('canUndo should return false when nothing to undo', () => {
      const store = useWorkflowBuilderStore.getState();
      expect(store.canUndo()).toBe(false);
    });

    it('canRedo should return false when nothing to redo', () => {
      const store = useWorkflowBuilderStore.getState();
      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      expect(useWorkflowBuilderStore.getState().canRedo()).toBe(false);
    });

    it('should undo edge addition', () => {
      const store = useWorkflowBuilderStore.getState();

      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'B', text: 'B', kind: 'task' });
      store.addEdge('A', 'B');

      expect(useWorkflowBuilderStore.getState().edges).toHaveLength(1);

      store.undo();
      expect(useWorkflowBuilderStore.getState().edges).toHaveLength(0);
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(2); // Nodes still there
    });

    it('should undo node removal and restore edges', () => {
      const store = useWorkflowBuilderStore.getState();

      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'B', text: 'B', kind: 'task' });
      store.addEdge('A', 'B');

      // Remove node A (and its edge)
      store.removeNode('A');
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(1);
      expect(useWorkflowBuilderStore.getState().edges).toHaveLength(0);

      // Undo should restore both node and edge
      store.undo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(2);
      expect(useWorkflowBuilderStore.getState().edges).toHaveLength(1);
    });

    it('should undo merge node creation', () => {
      const store = useWorkflowBuilderStore.getState();

      // Create initial structure
      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'B', text: 'B', kind: 'task' });
      store.addNode({ id: 'C', text: 'C', kind: 'task' });
      store.addEdge('A', 'C');

      // Capture state before merge
      let state = useWorkflowBuilderStore.getState();
      expect(state.nodes).toHaveLength(3);
      expect(state.edges).toHaveLength(1);

      // Add B -> C which creates merge
      store.addEdge('B', 'C');
      state = useWorkflowBuilderStore.getState();
      expect(state.nodes).toHaveLength(4); // +1 merge node
      expect(state.edges).toHaveLength(3); // A->merge, B->merge, merge->C

      // Undo should remove merge node and restore original edge
      store.undo();
      state = useWorkflowBuilderStore.getState();
      expect(state.nodes).toHaveLength(3);
      expect(state.edges).toHaveLength(1);
      expect(state.edges[0].from).toBe('A');
      expect(state.edges[0].to).toBe('C');
    });

    it('should handle multiple undo then multiple redo', () => {
      const store = useWorkflowBuilderStore.getState();

      // Add 4 nodes
      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.addNode({ id: 'B', text: 'B', kind: 'task' });
      store.addNode({ id: 'C', text: 'C', kind: 'task' });
      store.addNode({ id: 'D', text: 'D', kind: 'task' });

      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(4);

      // Undo 3 times
      store.undo();
      store.undo();
      store.undo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(1);
      expect(useWorkflowBuilderStore.getState().nodes[0].id).toBe('A');

      // Redo 2 times
      store.redo();
      store.redo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(3);
      expect(useWorkflowBuilderStore.getState().nodes.map((n) => n.id)).toEqual(['A', 'B', 'C']);
    });

    it('should not undo past the beginning', () => {
      const store = useWorkflowBuilderStore.getState();

      store.addNode({ id: 'A', text: 'A', kind: 'task' });

      // Undo to empty
      store.undo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(0);

      // Try to undo again - should do nothing
      store.undo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(0);
      expect(useWorkflowBuilderStore.getState().canUndo()).toBe(false);
    });

    it('should not redo past the end', () => {
      const store = useWorkflowBuilderStore.getState();

      store.addNode({ id: 'A', text: 'A', kind: 'task' });
      store.undo();
      store.redo();

      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(1);

      // Try to redo again - should do nothing
      store.redo();
      expect(useWorkflowBuilderStore.getState().nodes).toHaveLength(1);
      expect(useWorkflowBuilderStore.getState().canRedo()).toBe(false);
    });
  });

  describe('Dirty State', () => {
    it('should be dirty after adding a node', () => {
      const store = useWorkflowBuilderStore.getState();
      expect(store.isDirty).toBe(false);

      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      expect(useWorkflowBuilderStore.getState().isDirty).toBe(true);
    });

    it('should not be dirty after removing all nodes in new workflow', () => {
      const store = useWorkflowBuilderStore.getState();

      store.addNode({ id: 'node-1', text: 'A', kind: 'task' });
      expect(useWorkflowBuilderStore.getState().isDirty).toBe(true);

      store.removeNode('node-1');
      expect(useWorkflowBuilderStore.getState().isDirty).toBe(false);
    });

    it('should be dirty after changing workflow name', () => {
      const store = useWorkflowBuilderStore.getState();
      expect(store.isDirty).toBe(false);

      store.setWorkflowName('New Name');
      expect(useWorkflowBuilderStore.getState().isDirty).toBe(true);
    });
  });
});
