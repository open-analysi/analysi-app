/**
 * Workflow Builder Store
 *
 * Zustand store for managing workflow builder state including:
 * - Canvas nodes and edges
 * - Selection state
 * - Undo/redo history
 * - Workflow metadata
 * - Persistence operations
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { backendApi } from '../services/backendApi';
import type { Workflow, WorkflowNode } from '../types/workflow';
import type {
  WorkflowBuilderStore,
  CanvasNodeData,
  CanvasEdgeData,
  HistoryEntry,
} from '../types/workflowBuilder';

import { createStorage, STORAGE_KEYS } from './draftStorage';

const MAX_HISTORY_SIZE = 50;

/**
 * Generate a unique ID for canvas elements
 * Uses crypto.randomUUID() for better randomness when available
 */
function generateId(prefix: string): string {
  const randomPart =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID().slice(0, 8)
      : // eslint-disable-next-line sonarjs/pseudo-random -- fallback for environments without crypto
        Date.now().toString(36) + Math.random().toString(36).substring(2, 9);
  return `${prefix}-${randomPart}`;
}

/**
 * Infer template ID from node name for transformation nodes
 * This handles workflows saved before node_template_id was properly stored
 */
function inferTemplateIdFromName(name: string): string | undefined {
  const normalizedName = name.toLowerCase().trim();
  if (normalizedName === 'identity') return 'identity';
  if (normalizedName === 'merge') return 'merge';
  if (normalizedName === 'collect') return 'collect';
  return undefined;
}

/**
 * Convert a Workflow to canvas format
 */
function workflowToCanvas(workflow: Workflow): {
  nodes: CanvasNodeData[];
  edges: CanvasEdgeData[];
} {
  const nodes: CanvasNodeData[] = workflow.nodes.map((node) => {
    // For transformation nodes without node_template_id, infer from name
    let nodeTemplateId = node.node_template_id;
    if (node.kind === 'transformation' && !nodeTemplateId) {
      nodeTemplateId = inferTemplateIdFromName(node.name) ?? null;
    }

    return {
      id: node.id,
      text: node.name,
      kind: node.kind,
      taskId: node.task_id ?? undefined,
      nodeTemplateId: nodeTemplateId ?? undefined,
      foreachConfig: node.foreach_config ?? undefined,
      workflowNode: node,
    };
  });

  const edges: CanvasEdgeData[] = workflow.edges.map((edge) => ({
    id: edge.id,
    from: edge.from_node_uuid,
    to: edge.to_node_uuid,
    text: edge.alias ?? undefined,
    workflowEdge: edge,
  }));

  return { nodes, edges };
}

/**
 * Node data format for API
 */
interface WorkflowNodeSaveData {
  node_id: string;
  kind: string;
  name: string;
  task_id?: string;
  node_template_id?: string;
  foreach_config?: Record<string, unknown>;
  template_code?: string;
  is_start_node?: boolean;
  schemas?: Record<string, unknown>;
}

/**
 * Edge data format for API
 */
interface WorkflowEdgeSaveData {
  edge_id: string;
  from_node_id: string;
  to_node_id: string;
  alias?: string;
}

/**
 * Convert canvas data to workflow format for saving
 */
function canvasToWorkflowNodes(
  nodes: CanvasNodeData[],
  edges: CanvasEdgeData[]
): WorkflowNodeSaveData[] {
  // Find nodes with no incoming edges (start nodes)
  const nodesWithIncomingEdges = new Set(edges.map((e) => e.to));

  return nodes.map((node, index) => {
    // Get template ID from node or fallback to original workflow node data
    // This handles cases where persisted state loses the nodeTemplateId
    const workflowNode: WorkflowNode | undefined = node.workflowNode;
    const nodeTemplateId = node.nodeTemplateId || workflowNode?.node_template_id || undefined;
    const taskId = node.taskId || workflowNode?.task_id || undefined;

    // Validate: transformation nodes must have a nodeTemplateId
    if (node.kind === 'transformation' && !nodeTemplateId) {
      throw new Error(
        `Transformation node "${node.text}" (${node.id}) requires a template. ` +
          `Please select a template (identity, merge, or collect) for this node.`
      );
    }

    // Validate: task nodes must have a taskId
    if (node.kind === 'task' && !taskId) {
      throw new Error(`Task node "${node.text}" (${node.id}) requires a task to be selected.`);
    }

    // Mark as start node if it has no incoming edges (or is first node when no edges exist)
    const isStartNode = edges.length === 0 ? index === 0 : !nodesWithIncomingEdges.has(node.id);

    return {
      node_id: node.id,
      kind: node.kind,
      name: node.text,
      task_id: taskId,
      node_template_id: nodeTemplateId,
      foreach_config: node.foreachConfig,
      is_start_node: isStartNode,
      // Required: provide default schemas structure
      schemas: {
        input: { type: 'object' },
        output_result: { type: 'object' },
      },
    };
  });
}

function canvasToWorkflowEdges(edges: CanvasEdgeData[]): WorkflowEdgeSaveData[] {
  return edges.map((edge) => ({
    edge_id: edge.id,
    from_node_id: edge.from,
    to_node_id: edge.to,
    alias: edge.text,
  }));
}

/**
 * Initial state
 */
const initialState = {
  // Workflow metadata
  workflowId: null as string | null,
  workflowName: 'Untitled Workflow',
  workflowDescription: '',
  isDynamic: false,
  dataSamples: [] as unknown[],

  // Canvas state
  nodes: [] as CanvasNodeData[],
  edges: [] as CanvasEdgeData[],
  selections: [] as string[],

  // UI state
  isDirty: false,
  draftTimestamp: null as number | null,
  isLoading: false,
  isSaving: false,
  error: null as string | null,

  // History
  history: [] as HistoryEntry[],
  historyIndex: -1,
};

/**
 * Check if the state matches the initial "clean" state for a new workflow.
 * Used to determine if isDirty should be false after deletions.
 */
function isCleanNewWorkflowState(state: {
  workflowId: string | null;
  workflowName: string;
  workflowDescription: string;
  nodes: CanvasNodeData[];
  edges: CanvasEdgeData[];
  dataSamples: unknown[];
}): boolean {
  // Only applies to new workflows (no saved workflowId)
  if (state.workflowId !== null) return false;

  return (
    state.nodes.length === 0 &&
    state.edges.length === 0 &&
    state.dataSamples.length === 0 &&
    state.workflowName === 'Untitled Workflow' &&
    state.workflowDescription === ''
  );
}

export const useWorkflowBuilderStore = create<WorkflowBuilderStore>()(
  persist(
    (set, get) => ({
      ...initialState,

      // Node operations
      addNode: (node: CanvasNodeData, autoConnect?: boolean) => {
        const state = get();
        state.pushHistory();

        // Determine which node to connect to (opt-in, disabled by default)
        let connectToNodeId: string | null = null;
        if (autoConnect === true && state.nodes.length > 0) {
          // If a node is selected, connect to it; otherwise connect to the last node
          const selectedNodeId = state.selections.find((id) =>
            state.nodes.some((n) => n.id === id)
          );
          connectToNodeId = selectedNodeId || state.nodes[state.nodes.length - 1].id;
        }

        // Add the node
        const newNodes = [...state.nodes, node];

        // Auto-create edge if connecting to an existing node
        let newEdges = state.edges;
        if (connectToNodeId) {
          const newEdge: CanvasEdgeData = {
            id: generateId('edge'),
            from: connectToNodeId,
            to: node.id,
          };
          newEdges = [...state.edges, newEdge];
        }

        set({
          nodes: newNodes,
          edges: newEdges,
          selections: [node.id], // Select the newly added node
          isDirty: true,
          draftTimestamp: Date.now(),
        });
      },

      removeNode: (nodeId: string) => {
        const state = get();
        state.pushHistory();
        const newNodes = state.nodes.filter((n) => n.id !== nodeId);
        const newEdges = state.edges.filter((e) => e.from !== nodeId && e.to !== nodeId);
        const newState = {
          ...state,
          nodes: newNodes,
          edges: newEdges,
        };
        // Check if we're back to a clean initial state
        const isClean = isCleanNewWorkflowState(newState);
        set({
          nodes: newNodes,
          edges: newEdges,
          // Clear selection if removed node was selected
          selections: state.selections.filter((id) => id !== nodeId),
          isDirty: !isClean,
          draftTimestamp: isClean ? null : Date.now(),
        });
      },

      updateNode: (nodeId: string, updates: Partial<CanvasNodeData>) => {
        const state = get();
        state.pushHistory();
        set({
          nodes: state.nodes.map((n) => (n.id === nodeId ? { ...n, ...updates } : n)),
          isDirty: true,
          draftTimestamp: Date.now(),
        });
      },

      // Edge operations
      addEdge: (fromId: string, toId: string, label?: string) => {
        const state = get();

        // Prevent duplicate edges
        const exists = state.edges.some((e) => e.from === fromId && e.to === toId);
        if (exists) return;

        // Prevent self-loops
        if (fromId === toId) return;

        state.pushHistory();

        // If target is already a merge node, just add the edge directly
        // (no need to create another merge node)
        const targetNode = state.nodes.find((n) => n.id === toId);
        if (targetNode?.kind === 'transformation' && targetNode?.nodeTemplateId === 'merge') {
          const newEdge: CanvasEdgeData = {
            id: generateId('edge'),
            from: fromId,
            to: toId,
            text: label,
          };
          set({
            edges: [...state.edges, newEdge],
            isDirty: true,
            draftTimestamp: Date.now(),
          });
          return;
        }

        // Check for fan-in: does the target node already have incoming edges?
        const existingIncomingEdges = state.edges.filter((e) => e.to === toId);

        if (existingIncomingEdges.length >= 1) {
          // Fan-in detected! Check if there's already a merge node feeding into target
          const existingMergeEdge = existingIncomingEdges.find((e) => {
            const sourceNode = state.nodes.find((n) => n.id === e.from);
            return sourceNode?.kind === 'transformation' && sourceNode?.nodeTemplateId === 'merge';
          });

          if (existingMergeEdge) {
            // There's already a merge node - add new edge to the existing merge node
            const mergeNodeId = existingMergeEdge.from;

            // Prevent duplicate edge to merge node
            const edgeToMergeExists = state.edges.some(
              (e) => e.from === fromId && e.to === mergeNodeId
            );
            if (edgeToMergeExists) return;

            const newEdge: CanvasEdgeData = {
              id: generateId('edge'),
              from: fromId,
              to: mergeNodeId,
            };

            set({
              edges: [...state.edges, newEdge],
              isDirty: true,
              draftTimestamp: Date.now(),
            });
          } else {
            // No merge node yet - create one and rewire edges
            const mergeNodeId = generateId('node');
            const mergeNode: CanvasNodeData = {
              id: mergeNodeId,
              text: 'Merge',
              kind: 'transformation',
              nodeTemplateId: 'merge',
            };

            // Update existing incoming edges to point to merge node instead
            const updatedEdges = state.edges.map((e) => {
              if (e.to === toId) {
                return { ...e, to: mergeNodeId };
              }
              return e;
            });

            // Add new edge from source to merge node
            const newEdgeToMerge: CanvasEdgeData = {
              id: generateId('edge'),
              from: fromId,
              to: mergeNodeId,
            };

            // Add edge from merge node to original target
            const mergeToTargetEdge: CanvasEdgeData = {
              id: generateId('edge'),
              from: mergeNodeId,
              to: toId,
            };

            set({
              nodes: [...state.nodes, mergeNode],
              edges: [...updatedEdges, newEdgeToMerge, mergeToTargetEdge],
              isDirty: true,
              draftTimestamp: Date.now(),
            });
          }
        } else {
          // Normal case - just add the edge
          const newEdge: CanvasEdgeData = {
            id: generateId('edge'),
            from: fromId,
            to: toId,
            text: label,
          };

          set({
            edges: [...state.edges, newEdge],
            isDirty: true,
            draftTimestamp: Date.now(),
          });
        }
      },

      removeEdge: (edgeId: string) => {
        const state = get();
        state.pushHistory();
        const newEdges = state.edges.filter((e) => e.id !== edgeId);
        const newState = {
          ...state,
          edges: newEdges,
        };
        // Check if we're back to a clean initial state
        const isClean = isCleanNewWorkflowState(newState);
        set({
          edges: newEdges,
          selections: state.selections.filter((id) => id !== edgeId),
          isDirty: !isClean,
          draftTimestamp: isClean ? null : Date.now(),
        });
      },

      updateEdge: (edgeId: string, updates: Partial<CanvasEdgeData>) => {
        const state = get();
        state.pushHistory();
        set({
          edges: state.edges.map((e) => (e.id === edgeId ? { ...e, ...updates } : e)),
          isDirty: true,
          draftTimestamp: Date.now(),
        });
      },

      // Selection
      setSelections: (ids: string[]) => {
        set({ selections: ids });
      },

      clearSelections: () => {
        set({ selections: [] });
      },

      // Workflow metadata
      setWorkflowName: (name: string) => {
        set({ workflowName: name, isDirty: true, draftTimestamp: Date.now() });
      },

      setWorkflowDescription: (description: string) => {
        set({ workflowDescription: description, isDirty: true, draftTimestamp: Date.now() });
      },

      // Data samples
      addDataSample: (sample: unknown) => {
        const state = get();
        set({
          dataSamples: [...state.dataSamples, sample],
          isDirty: true,
          draftTimestamp: Date.now(),
        });
      },

      removeDataSample: (index: number) => {
        const state = get();
        const newDataSamples = state.dataSamples.filter((_, i) => i !== index);
        const newState = {
          ...state,
          dataSamples: newDataSamples,
        };
        // Check if we're back to a clean initial state
        const isClean = isCleanNewWorkflowState(newState);
        set({
          dataSamples: newDataSamples,
          isDirty: !isClean,
          draftTimestamp: isClean ? null : Date.now(),
        });
      },

      updateDataSample: (index: number, sample: unknown) => {
        const state = get();
        const newSamples = [...state.dataSamples];
        newSamples[index] = sample;
        set({
          dataSamples: newSamples,
          isDirty: true,
          draftTimestamp: Date.now(),
        });
      },

      setDataSamples: (samples: unknown[]) => {
        set({ dataSamples: samples, isDirty: true, draftTimestamp: Date.now() });
      },

      // Persistence
      newWorkflow: () => {
        set({
          ...initialState,
          workflowId: null,
          workflowName: 'Untitled Workflow',
          workflowDescription: '',
        });
      },

      loadWorkflow: (workflow: Workflow) => {
        const { nodes, edges } = workflowToCanvas(workflow);
        set({
          workflowId: workflow.id,
          workflowName: workflow.name,
          workflowDescription: workflow.description ?? '',
          isDynamic: workflow.is_dynamic,
          dataSamples: workflow.data_samples || [],
          nodes,
          edges,
          selections: [],
          isDirty: false,
          isLoading: false,
          error: null,
          history: [],
          historyIndex: -1,
        });
      },

      saveWorkflow: async () => {
        const state = get();
        set({ isSaving: true, error: null });

        try {
          const workflowData = {
            name: state.workflowName,
            description: state.workflowDescription,
            is_dynamic: state.isDynamic,
            io_schema: { input: {}, output: {} },
            nodes: canvasToWorkflowNodes(state.nodes, state.edges),
            edges: canvasToWorkflowEdges(state.edges),
            data_samples: state.dataSamples,
          };

          console.info('Saving workflow', {
            workflowId: state.workflowId,
            workflowData,
          });

          let savedWorkflow: Workflow;

          if (state.workflowId) {
            // Update existing workflow
            console.info('Updating existing workflow', { workflowId: state.workflowId });
            try {
              savedWorkflow = await backendApi.updateWorkflow(state.workflowId, workflowData);
            } catch (updateError) {
              // If update fails with 404, workflow was deleted - create new one
              const isNotFound =
                updateError instanceof Error &&
                (updateError.message.includes('404') ||
                  (updateError as { response?: { status?: number } }).response?.status === 404);

              if (isNotFound) {
                console.info('Workflow not found, creating new one');
                savedWorkflow = await backendApi.createWorkflow(workflowData);
              } else {
                throw updateError;
              }
            }
          } else {
            // Create new workflow
            console.info('Creating new workflow');
            savedWorkflow = await backendApi.createWorkflow(workflowData);
          }

          console.info('Workflow saved successfully', { workflow: savedWorkflow });

          set({
            workflowId: savedWorkflow.id,
            isDirty: false,
            isSaving: false,
          });

          return savedWorkflow;
        } catch (error) {
          console.error('Failed to save workflow:', error);
          const errorMessage = error instanceof Error ? error.message : 'Failed to save workflow';
          set({ error: errorMessage, isSaving: false });
          return null;
        }
      },

      // History (undo/redo)
      pushHistory: () => {
        const state = get();
        const entry: HistoryEntry = {
          nodes: [...state.nodes],
          edges: [...state.edges],
          timestamp: Date.now(),
        };

        // Remove any "future" history if we're not at the end
        const newHistory = state.history.slice(0, state.historyIndex + 1);
        newHistory.push(entry);

        // Limit history size
        if (newHistory.length > MAX_HISTORY_SIZE) {
          newHistory.shift();
        }

        set({
          history: newHistory,
          historyIndex: newHistory.length - 1,
        });
      },

      undo: () => {
        const state = get();
        if (state.historyIndex < 0) return;

        const entry = state.history[state.historyIndex];
        if (!entry) return;

        // Check if current state already matches this history entry
        const isSame =
          JSON.stringify(state.nodes) === JSON.stringify(entry.nodes) &&
          JSON.stringify(state.edges) === JSON.stringify(entry.edges);

        if (isSame) {
          // Already at this state, need to go further back
          if (state.historyIndex <= 0) return;
          const olderEntry = state.history[state.historyIndex - 1];
          set({
            nodes: olderEntry.nodes,
            edges: olderEntry.edges,
            historyIndex: state.historyIndex - 1,
            isDirty: true,
            draftTimestamp: Date.now(),
          });
        } else {
          // Save current state for redo before restoring
          const currentEntry: HistoryEntry = {
            nodes: [...state.nodes],
            edges: [...state.edges],
            timestamp: Date.now(),
          };
          const newHistory = [...state.history.slice(0, state.historyIndex + 1), currentEntry];

          set({
            nodes: entry.nodes,
            edges: entry.edges,
            history: newHistory,
            historyIndex: state.historyIndex, // Stay at same index after first undo
            isDirty: true,
            draftTimestamp: Date.now(),
          });
        }
      },

      redo: () => {
        const state = get();
        if (!state.canRedo()) return;

        const newIndex = state.historyIndex + 1;
        const entry = state.history[newIndex];

        if (entry) {
          set({
            nodes: entry.nodes,
            edges: entry.edges,
            historyIndex: newIndex,
            isDirty: true,
            draftTimestamp: Date.now(),
          });
        }
      },

      canUndo: () => {
        const state = get();
        if (state.historyIndex < 0) return false;

        const entry = state.history[state.historyIndex];
        if (!entry) return false;

        // Check if current state matches this history entry
        const isSame =
          JSON.stringify(state.nodes) === JSON.stringify(entry.nodes) &&
          JSON.stringify(state.edges) === JSON.stringify(entry.edges);

        // Can undo if current != history[idx] (can restore idx)
        // Or if current == history[idx] but idx > 0 (can restore idx-1)
        return !isSame || state.historyIndex > 0;
      },

      canRedo: () => {
        const state = get();
        return state.historyIndex < state.history.length - 1;
      },

      // Reset
      reset: () => {
        set(initialState);
      },
    }),
    {
      name: STORAGE_KEYS.WORKFLOW_BUILDER,
      storage: createStorage<WorkflowBuilderStore>(),
      // Only persist draft data - NOT history, selections, or UI state
      partialize: (state) =>
        ({
          workflowId: state.workflowId,
          workflowName: state.workflowName,
          workflowDescription: state.workflowDescription,
          isDynamic: state.isDynamic,
          nodes: state.nodes,
          edges: state.edges,
          dataSamples: state.dataSamples,
          isDirty: state.isDirty,
          draftTimestamp: state.draftTimestamp,
        }) as WorkflowBuilderStore,
    }
  )
);
