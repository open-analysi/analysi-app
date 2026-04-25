/**
 * Cy Script Editor Store
 *
 * Zustand store for managing Cy script editor state including:
 * - Draft persistence per task
 * - Undo/redo history (session-only, not persisted)
 * - Script content and dirty state
 *
 * Drafts are automatically saved to localStorage and can be restored
 * when returning to a task after navigation.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { createStorage, STORAGE_KEYS } from './draftStorage';

/**
 * Draft data stored per task
 */
export interface CyDraft {
  script: string;
  taskName: string;
  timestamp: number;
}

/**
 * History entry for undo/redo
 */
interface HistoryEntry {
  script: string;
  timestamp: number;
}

const MAX_HISTORY_SIZE = 50;

/**
 * Cy Editor State interface
 */
export interface CyEditorState {
  // Persisted draft data (stored in localStorage)
  drafts: Record<string, CyDraft>;

  // Session state (not persisted)
  activeTaskId: string | null;
  activeTaskName: string;
  scriptContent: string;
  originalScript: string; // For isDirty comparison
  isDirty: boolean;

  // Undo/redo history (session-only, not persisted)
  history: HistoryEntry[];
  historyIndex: number;

  // Actions
  setActiveTask: (taskId: string, script: string, taskName: string) => void;
  setScript: (content: string) => void;
  saveDraft: () => void;
  loadDraft: (taskId: string) => CyDraft | null;
  clearDraft: (taskId: string) => void;
  hasDraft: (taskId: string) => boolean;
  getDraftTimestamp: (taskId: string) => number | null;
  markAsSaved: (newScript: string) => void;

  // Undo/redo
  pushHistory: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  // Reset
  reset: () => void;
}

/**
 * Initial session state (not persisted)
 */
const initialSessionState = {
  activeTaskId: null as string | null,
  activeTaskName: '',
  scriptContent: '',
  originalScript: '',
  isDirty: false,
  history: [] as HistoryEntry[],
  historyIndex: -1,
};

export const useCyEditorStore = create<CyEditorState>()(
  persist(
    (set, get) => ({
      // Persisted data
      drafts: {},

      // Session state
      ...initialSessionState,

      /**
       * Set the active task and load its script
       * Auto-saves current draft before switching
       */
      setActiveTask: (taskId: string, script: string, taskName: string) => {
        const state = get();

        // Auto-save current draft before switching tasks
        if (state.activeTaskId && state.isDirty) {
          state.saveDraft();
        }

        set({
          activeTaskId: taskId,
          activeTaskName: taskName,
          scriptContent: script,
          originalScript: script,
          isDirty: false,
          history: [],
          historyIndex: -1,
        });
      },

      /**
       * Update the script content
       * Pushes to history for undo support
       */
      setScript: (content: string) => {
        const state = get();
        state.pushHistory();
        set({
          scriptContent: content,
          isDirty: content !== state.originalScript,
        });
      },

      /**
       * Save current script as a draft
       */
      saveDraft: () => {
        const state = get();
        if (!state.activeTaskId) return;

        // Only save if there are actual changes
        if (state.scriptContent === state.originalScript) return;

        set({
          drafts: {
            ...state.drafts,
            [state.activeTaskId]: {
              script: state.scriptContent,
              taskName: state.activeTaskName,
              timestamp: Date.now(),
            },
          },
        });
      },

      /**
       * Load a draft for a specific task
       */
      loadDraft: (taskId: string): CyDraft | null => {
        return get().drafts[taskId] ?? null;
      },

      /**
       * Clear the draft for a specific task
       */
      clearDraft: (taskId: string) => {
        const state = get();
        // eslint-disable-next-line @typescript-eslint/no-unused-vars, sonarjs/no-unused-vars
        const { [taskId]: _, ...remaining } = state.drafts;
        set({ drafts: remaining });
      },

      /**
       * Check if a draft exists for a task
       */
      hasDraft: (taskId: string): boolean => {
        return !!get().drafts[taskId];
      },

      /**
       * Get the timestamp of a draft
       */
      getDraftTimestamp: (taskId: string): number | null => {
        return get().drafts[taskId]?.timestamp ?? null;
      },

      /**
       * Mark the current script as saved (after successful API save)
       * Clears the draft and updates originalScript
       */
      markAsSaved: (newScript: string) => {
        const state = get();
        if (state.activeTaskId) {
          state.clearDraft(state.activeTaskId);
        }
        set({
          originalScript: newScript,
          isDirty: false,
        });
      },

      // ============================================
      // Undo/Redo (same pattern as workflowBuilderStore)
      // ============================================

      /**
       * Push current state to history
       */
      pushHistory: () => {
        const state = get();
        const entry: HistoryEntry = {
          script: state.scriptContent,
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

      /**
       * Undo the last change
       */
      undo: () => {
        const state = get();
        if (!state.canUndo()) return;

        const newIndex = state.historyIndex - 1;
        const entry = state.history[newIndex];

        if (entry) {
          set({
            scriptContent: entry.script,
            historyIndex: newIndex,
            isDirty: entry.script !== state.originalScript,
          });
        }
      },

      /**
       * Redo the last undone change
       */
      redo: () => {
        const state = get();
        if (!state.canRedo()) return;

        const newIndex = state.historyIndex + 1;
        const entry = state.history[newIndex];

        if (entry) {
          set({
            scriptContent: entry.script,
            historyIndex: newIndex,
            isDirty: entry.script !== state.originalScript,
          });
        }
      },

      /**
       * Check if undo is available
       */
      canUndo: (): boolean => {
        const state = get();
        return state.historyIndex > 0;
      },

      /**
       * Check if redo is available
       */
      canRedo: (): boolean => {
        const state = get();
        return state.historyIndex < state.history.length - 1;
      },

      /**
       * Reset session state (keeps drafts)
       */
      reset: () => {
        set(initialSessionState);
      },
    }),
    {
      name: STORAGE_KEYS.CY_EDITOR,
      storage: createStorage<CyEditorState>(),
      // Only persist the drafts map
      partialize: (state) =>
        ({
          drafts: state.drafts,
        }) as CyEditorState,
    }
  )
);
