/**
 * Custom hooks for WorkbenchModern side-effects.
 * Extracted to reduce the component's cognitive complexity score.
 */
import React, { useEffect, useCallback } from 'react';

import { backendApi } from '../../services/backendApi';
import { useCyEditorStore } from '../../store/cyEditorStore';
import type { Task } from '../../types/knowledge';

import { ADHOC_DRAFT_KEY, DEFAULT_SCRIPT, type DataSample } from './workbenchUtils';

// ─── Keyboard Shortcuts ──────────────────────────────────────────────

interface KeyboardShortcutsDeps {
  toggleSidebar: () => void;
  toggleBottomPanel: () => void;
  isRunning: boolean;
  selectedTask: Task | null;
  scriptContent: string;
  isDirty: boolean;
  handleRun: () => void;
  setShowReloadDialog: (show: boolean) => void;
}

/**
 * Registers global keyboard shortcuts for the workbench.
 * Cmd/Ctrl+B: toggle sidebar, Cmd/Ctrl+J: toggle bottom panel,
 * Cmd/Ctrl+Enter: run, Cmd/Ctrl+R / F5: intercept refresh when dirty.
 */
export function useWorkbenchKeyboardShortcuts(deps: KeyboardShortcutsDeps): void {
  const {
    toggleSidebar,
    toggleBottomPanel,
    isRunning,
    selectedTask,
    scriptContent,
    isDirty,
    handleRun,
    setShowReloadDialog,
  } = deps;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;

      if (mod && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
        return;
      }
      if (mod && e.key === 'j') {
        e.preventDefault();
        toggleBottomPanel();
        return;
      }
      if (mod && e.key === 'Enter') {
        e.preventDefault();
        if (!isRunning && (selectedTask || scriptContent.trim())) {
          handleRun();
        }
        return;
      }
      // Intercept refresh when dirty
      const isRefreshKey = (mod && e.key === 'r') || e.key === 'F5';
      if (isRefreshKey && isDirty) {
        e.preventDefault();
        setShowReloadDialog(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [
    toggleSidebar,
    toggleBottomPanel,
    isRunning,
    selectedTask,
    scriptContent,
    isDirty,
    handleRun,
    setShowReloadDialog,
  ]);
}

// ─── Auto-save Draft ─────────────────────────────────────────────────

interface AutoSaveDraftDeps {
  isDirty: boolean;
  isAdHocMode: boolean;
  scriptContent: string;
  selectedTask: Task | null;
}

/**
 * Auto-saves the editor draft to the CyEditorStore with debouncing.
 * Handles both ad-hoc and saved-task modes.
 */
export function useAutoSaveDraft(deps: AutoSaveDraftDeps): void {
  const { isDirty, isAdHocMode, scriptContent, selectedTask } = deps;

  useEffect(() => {
    if (!isDirty) return;

    // Handle ad-hoc mode
    if (isAdHocMode) {
      if (scriptContent.trim() === '' || scriptContent === DEFAULT_SCRIPT) return;

      const timeoutId = setTimeout(() => {
        useCyEditorStore.setState((s) => ({
          ...s,
          drafts: {
            ...s.drafts,
            [ADHOC_DRAFT_KEY]: {
              script: scriptContent,
              taskName: 'Ad-hoc Script',
              timestamp: Date.now(),
            },
          },
        }));
      }, 1000);

      return () => clearTimeout(timeoutId);
    }

    // Handle saved task mode
    if (!selectedTask) return;

    const taskId = selectedTask.id;
    const savedScript = selectedTask.script || '';
    if (scriptContent === savedScript) return;

    const timeoutId = setTimeout(() => {
      useCyEditorStore.setState((s) => ({
        ...s,
        drafts: {
          ...s.drafts,
          [taskId]: {
            script: scriptContent,
            taskName: selectedTask?.name || '',
            timestamp: Date.now(),
          },
        },
      }));
    }, 1000);

    return () => clearTimeout(timeoutId);
  }, [scriptContent, selectedTask, isDirty, isAdHocMode]);
}

// ─── Example Selection ───────────────────────────────────────────────

/**
 * Returns a handler for selecting a data sample example in the workbench.
 */
export function useExampleSelection(
  dataSamples: unknown[] | undefined,
  setState: React.Dispatch<
    React.SetStateAction<
      {
        input: string;
        selectedExample: string;
        fromTaskRunId: string | null;
      } & Record<string, unknown>
    >
  >
): (exampleIndex: string) => void {
  return useCallback(
    (exampleIndex: string) => {
      if (!dataSamples) return;

      const index = parseInt(exampleIndex, 10);
      if (isNaN(index) || index < 0 || index >= dataSamples.length) return;

      const sample = dataSamples[index];
      const inputData = (sample as DataSample)?.input || sample;
      const inputString =
        typeof inputData === 'string' ? inputData : JSON.stringify(inputData, null, 2);

      setState((prev) => ({
        ...prev,
        input: inputString,
        selectedExample: exampleIndex,
        fromTaskRunId: null,
      }));
    },
    [dataSamples, setState]
  );
}

// ─── Script Analysis ─────────────────────────────────────────────────

interface ScriptAnalysisState {
  tools_used: string[] | null;
  external_variables: string[] | null;
  errors: string[] | null;
  isLoading: boolean;
}

interface ScriptAnalysisDeps {
  scriptContent: string;
  selectedTask: Task | null;
  isDirty: boolean;
  setScriptAnalysis: React.Dispatch<React.SetStateAction<ScriptAnalysisState>>;
}

/**
 * Analyzes script content for tool usage and errors.
 * Immediate for saved tasks, debounced for ad-hoc/modified scripts.
 */
export function useScriptAnalysis(deps: ScriptAnalysisDeps): void {
  const { scriptContent, selectedTask, isDirty, setScriptAnalysis } = deps;

  useEffect(() => {
    if (!scriptContent.trim()) {
      setScriptAnalysis({
        tools_used: null,
        external_variables: null,
        errors: null,
        isLoading: false,
      });
      return;
    }

    // For saved tasks, analyze immediately when task changes
    if (selectedTask && !isDirty) {
      setScriptAnalysis((prev) => ({ ...prev, isLoading: true }));
      backendApi
        .analyzeTask(selectedTask.id)
        .then((result) => {
          setScriptAnalysis({
            tools_used: result.tools_used,
            external_variables: result.external_variables,
            errors: result.errors,
            isLoading: false,
          });
        })
        .catch((err) => {
          console.error('[Script Analysis] Failed to analyze task:', err);
          setScriptAnalysis((prev) => ({ ...prev, isLoading: false }));
        });
      return;
    }

    // For ad-hoc or modified scripts, debounce the analysis
    const runAnalysis = async () => {
      setScriptAnalysis((prev) => ({ ...prev, isLoading: true }));
      try {
        const result = await backendApi.analyzeScript(scriptContent);
        setScriptAnalysis({
          tools_used: result.tools_used,
          external_variables: result.external_variables,
          errors: result.errors,
          isLoading: false,
        });
      } catch (err) {
        console.error('[Script Analysis] Failed to analyze script:', err);
        setScriptAnalysis((prev) => ({ ...prev, isLoading: false }));
      }
    };
    const timeoutId = setTimeout(() => void runAnalysis(), 500);

    return () => clearTimeout(timeoutId);
  }, [scriptContent, selectedTask, isDirty, setScriptAnalysis]);
}
