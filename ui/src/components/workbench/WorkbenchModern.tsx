/**
 * WorkbenchModern - IDE-style task execution environment
 *
 * Theme: Uses the centralized dark theme from src/styles/theme.ts
 * - Page background: bg-dark-900 (#121212)
 * - Panel backgrounds: bg-dark-800 (#1E1E1E)
 * - Component backgrounds: bg-dark-700 (#2D2D2D)
 * - Borders: border-gray-700, border-gray-600
 * - Text: text-white, text-gray-100, text-gray-400
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';

import {
  ClipboardDocumentIcon,
  CheckIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  CodeBracketIcon,
  PlayIcon,
  SparklesIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import ace from 'ace-builds/src-noconflict/ace';
import AceEditor from 'react-ace';
import type { IAceEditor } from 'react-ace/lib/types';
import {
  Panel,
  Group,
  Separator,
  useDefaultLayout,
  type PanelImperativeHandle,
} from 'react-resizable-panels';
import { useBlocker } from 'react-router';

import 'ace-builds/src-noconflict/ext-inline_autocomplete';
import 'ace-builds/src-noconflict/ext-language_tools';
import 'ace-builds/src-noconflict/mode-python';
import 'ace-builds/src-noconflict/theme-terminal';

import { useClickTracking } from '../../hooks/useClickTracking';
import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { useCyEditorStore } from '../../store/cyEditorStore';
import type { Task } from '../../types/knowledge';
import { startPolling, type PollingController } from '../../utils/polling';
import { ConfirmDialog } from '../common/ConfirmDialog';

import { aiCompleter, cancelAiCompletion, schedulAiCompletion } from './aiCompleter';
import { cyCompleter } from './cyCompleter';
import { OutputRenderer } from './OutputRenderer';
import { ProgressBar } from './ProgressBar';
import { RunUnsavedChangesDialog } from './RunUnsavedChangesDialog';
import { SaveAsTaskModal } from './SaveAsTaskModal';
import TaskFeedbackSection from './TaskFeedbackSection';
import { TaskGenerationModal } from './TaskGenerationModal';
import { TaskSelector } from './TaskSelector';
import { UnsavedChangesDialog } from './UnsavedChangesDialog';
import { useAutocompleteData } from './useAutocompleteData';
import {
  useWorkbenchKeyboardShortcuts,
  useAutoSaveDraft,
  useScriptAnalysis,
} from './useWorkbenchEffects';
import {
  ADHOC_DRAFT_KEY,
  DEFAULT_SCRIPT,
  generateVersionedName,
  getStatusClasses,
  getToolNamespaceClasses,
  parseErrorLocation,
  parseExecutionOutput,
  parseTaskRunInput,
  type AceEditorWithAiRef,
  type AceLangTools,
  type AceRangeModule,
  type DataSample,
  type TaskRunDetailsResponse,
} from './workbenchUtils';

// Configure Ace base path
// eslint-disable-next-line @typescript-eslint/no-unsafe-call, @typescript-eslint/no-unsafe-member-access
ace.config.set('basePath', 'https://cdn.jsdelivr.net/npm/ace-builds@1.32.0/src-noconflict/');

// Extend window type for ace global
declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ace?: any;
  }
}

interface WorkbenchState {
  selectedTask: Task | null;
  scriptContent: string;
  isDirty: boolean;
  input: string;
  output: string;
  isSaving: boolean;
  isRunning: boolean;
  currentTrid: string | null;
  isAdHocMode: boolean;
  estimatedTime: number | null;
  startTime: number | null;
  elapsedTime: number;
  showProgress: boolean;
  completedOutput: string | null;
  fromTaskRunId: string | null;
  selectedExample: string;
  /** Explicit status from task execution: 'completed', 'failed', 'error', etc. */
  lastExecutionStatus: string | null;
  /** Log entries from Cy log() calls (dicts with ts+message, or legacy strings) */
  logEntries: ({ ts: number; message: string } | string)[];
  /** Which output tab is active */
  outputTab: 'result' | 'logs';
}

interface LayoutState {
  isSidebarCollapsed: boolean;
  isBottomPanelCollapsed: boolean;
}

interface WorkbenchModernProps {
  taskId?: string;
  inputData?: unknown;
  taskRunId?: string;
  cyScript?: string;
  isAdHoc?: boolean;
  onClearTaskRunId?: () => void;
  onClearTaskId?: () => void;
}

const WorkbenchModern: React.FC<WorkbenchModernProps> = ({
  taskId,
  inputData,
  taskRunId,
  cyScript,
  isAdHoc = false,
  onClearTaskRunId,
  onClearTaskId,
  // eslint-disable-next-line sonarjs/cognitive-complexity -- Large IDE component; hooks extracted where practical
}) => {
  const { error, runSafe, clearError } = useErrorHandler('WorkbenchModern');
  const { trackExecute } = useClickTracking('WorkbenchModern');

  // Draft persistence store
  const draftStore = useCyEditorStore();

  // Layout state
  const [layout, setLayout] = useState<LayoutState>({
    isSidebarCollapsed: false,
    isBottomPanelCollapsed: false,
  });

  // Workbench state - same as original
  const [state, setState] = useState<WorkbenchState>({
    selectedTask: null,
    scriptContent: cyScript || DEFAULT_SCRIPT,
    isDirty: false,
    input: '',
    output: '',
    isSaving: false,
    isRunning: false,
    currentTrid: null,
    isAdHocMode: isAdHoc,
    estimatedTime: null,
    startTime: null,
    elapsedTime: 0,
    showProgress: false,
    completedOutput: null,
    fromTaskRunId: taskRunId || null,
    selectedExample: '',
    lastExecutionStatus: null,
    logEntries: [],
    outputTab: 'result',
  });

  // Refs
  const sidebarPanelRef = useRef<PanelImperativeHandle>(null);
  const bottomPanelRef = useRef<PanelImperativeHandle>(null);
  const editorRef = useRef<IAceEditor | null>(null);
  const pollingControllerRef = useRef<PollingController | null>(null);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [copiedSection, setCopiedSection] = useState<string | null>(null);

  // Persistent layouts for resizable panels (v4 API)
  const { defaultLayout: mainLayout, onLayoutChanged: onMainLayoutChanged } = useDefaultLayout({
    id: 'workbench-main-layout',
  });
  const { defaultLayout: verticalLayout, onLayoutChanged: onVerticalLayoutChanged } =
    useDefaultLayout({ id: 'workbench-vertical-layout' });
  const { defaultLayout: ioLayout, onLayoutChanged: onIoLayoutChanged } = useDefaultLayout({
    id: 'workbench-io-layout',
  });

  // Recent task runs for the empty sidebar state
  const [recentTaskRuns, setRecentTaskRuns] = useState<
    Array<{
      id: string;
      task_name?: string;
      task_id?: string | null;
      status: string;
      started_at?: string | null;
      cy_script?: string | null;
      input_type?: string | null;
      input_location?: string | null;
    }>
  >([]);

  useEffect(() => {
    let cancelled = false;
    backendApi
      .getTaskRuns({ limit: 5, skip: 0, sort: 'started_at', order: 'desc' })
      .then((response) => {
        if (!cancelled && response?.task_runs) {
          setRecentTaskRuns(response.task_runs);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // Feature flag: AI-assisted task writing (generate + autocomplete). Default OFF.
  const aiAssistEnabled = (() => {
    try {
      return localStorage.getItem('workbench:aiAssist') === 'true';
    } catch {
      return false;
    }
  })();

  // AI inline autocomplete toggle (persisted to localStorage)
  const [aiAutocompleteEnabled, setAiAutocompleteEnabled] = useState<boolean>(() => {
    if (!aiAssistEnabled) return false;
    try {
      const stored = localStorage.getItem('workbench:aiAutocomplete');
      return stored === null ? true : stored === 'true';
    } catch {
      return true;
    }
  });

  const toggleAiAutocomplete = useCallback(() => {
    setAiAutocompleteEnabled((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('workbench:aiAutocomplete', String(next));
      } catch {
        // ignore
      }
      if (!next) cancelAiCompletion();
      return next;
    });
  }, []);

  // Track current occurrence index for tool navigation (for cycling through multiple usages)
  const toolOccurrenceIndexRef = useRef<Map<string, number>>(new Map());

  // Reset occurrence indices when script content changes
  useEffect(() => {
    toolOccurrenceIndexRef.current.clear();
  }, [state.scriptContent]);

  // Script analysis state (tools used, integrations)
  const [scriptAnalysis, setScriptAnalysis] = useState<{
    tools_used: string[] | null;
    external_variables: string[] | null;
    errors: string[] | null;
    isLoading: boolean;
  }>({
    tools_used: null,
    external_variables: null,
    errors: null,
    isLoading: false,
  });

  // Draft restore confirmation state
  const [pendingDraftRestore, setPendingDraftRestore] = useState<{
    taskId: string;
    task: Task;
    draft: { script: string; timestamp: number };
    savedScript: string;
    firstExampleInput: string;
    avgTime: number | null;
    preserveInput: boolean;
  } | null>(null);

  // Save As modal state
  const [showSaveAsModal, setShowSaveAsModal] = useState(false);

  // Task generation modal state
  const [showTaskGenerationModal, setShowTaskGenerationModal] = useState(false);

  // Unsaved changes dialog state (for New button)
  const [showUnsavedChangesDialog, setShowUnsavedChangesDialog] = useState(false);

  // Run unsaved changes dialog state (for Run button)
  const [showRunUnsavedDialog, setShowRunUnsavedDialog] = useState(false);

  // Track if we should proceed with "New" after a successful save
  const [pendingNewAfterSave, setPendingNewAfterSave] = useState(false);

  // Track if we should run after a successful save
  const [pendingRunAfterSave, setPendingRunAfterSave] = useState(false);

  // Navigation blocker dialog state (when navigating away with unsaved changes)
  const [showNavBlockerDialog, setShowNavBlockerDialog] = useState(false);
  const [pendingNavAfterSave, setPendingNavAfterSave] = useState(false);

  // Reload dialog state (when user presses Cmd+R / F5 / Ctrl+R with unsaved changes)
  const [showReloadDialog, setShowReloadDialog] = useState(false);
  const [pendingReloadAfterSave, setPendingReloadAfterSave] = useState(false);

  // Block React Router navigation when there are unsaved changes
  const blocker = useBlocker(state.isDirty);
  const blockerRef = useRef(blocker);
  blockerRef.current = blocker;

  // Show nav blocker dialog when navigation is intercepted
  useEffect(() => {
    if (blocker.state === 'blocked') {
      setShowNavBlockerDialog(true);
    }
  }, [blocker.state]);

  // Load integrations on mount for autocomplete (extracted to custom hook)
  useAutocompleteData();

  // Calculate average execution time from historical runs
  const calculateAverageExecutionTime = useCallback(
    async (taskId: string): Promise<number | null> => {
      const [historyResult] = await runSafe(
        backendApi.getTaskRunHistory(taskId, 5),
        'getTaskRunHistory',
        { action: 'fetching task run history', entityId: taskId }
      );

      if (historyResult?.task_runs && historyResult.task_runs.length > 0) {
        const executionTimes = historyResult.task_runs
          .filter((run) => run.created_at && run.updated_at)
          .map((run) => {
            const start = new Date(run.created_at).getTime();
            const end = new Date(run.updated_at).getTime();
            return (end - start) / 1000;
          })
          .filter((time: number) => time > 0 && time < 3600);

        if (executionTimes.length > 0) {
          const weights = executionTimes.map((_, index: number) => Math.pow(0.8, index));
          const weightedSum = executionTimes.reduce(
            (sum: number, time: number, index: number) => sum + time * weights[index],
            0
          );
          const totalWeight = weights.reduce((sum: number, weight: number) => sum + weight, 0);
          return Math.round(weightedSum / totalWeight);
        }
      }
      return null;
    },
    [runSafe]
  );

  // Save current draft before switching tasks (extracted to reduce cognitive complexity)
  const saveDraftBeforeSwitch = useCallback(() => {
    if (!state.isDirty) return;

    if (state.isAdHocMode) {
      if (state.scriptContent.trim() !== '' && state.scriptContent !== DEFAULT_SCRIPT) {
        useCyEditorStore.setState((s) => ({
          ...s,
          drafts: {
            ...s.drafts,
            [ADHOC_DRAFT_KEY]: {
              script: state.scriptContent,
              taskName: 'Ad-hoc Script',
              timestamp: Date.now(),
            },
          },
        }));
      }
      return;
    }

    if (!state.selectedTask) return;
    const currentTaskId = state.selectedTask.id;
    const savedScript = state.selectedTask.script || '';
    if (state.scriptContent !== savedScript) {
      useCyEditorStore.setState((s) => ({
        ...s,
        drafts: {
          ...s.drafts,
          [currentTaskId]: {
            script: state.scriptContent,
            taskName: state.selectedTask?.name || '',
            timestamp: Date.now(),
          },
        },
      }));
    }
  }, [state.isDirty, state.isAdHocMode, state.scriptContent, state.selectedTask]);

  // Clear task run viewing state and URL param (only triggers URL change if needed)
  const clearTaskRunState = useCallback(() => {
    setState((prev) => {
      if (prev.fromTaskRunId) onClearTaskRunId?.();
      return { ...prev, fromTaskRunId: null, selectedExample: '' };
    });
  }, [onClearTaskRunId]);

  // Handle switching to ad-hoc mode (extracted to reduce cognitive complexity)
  const switchToAdHocMode = useCallback(() => {
    const adhocDraft = draftStore.loadDraft(ADHOC_DRAFT_KEY);

    if (adhocDraft && adhocDraft.script !== DEFAULT_SCRIPT) {
      setPendingDraftRestore({
        taskId: ADHOC_DRAFT_KEY,
        task: {
          id: ADHOC_DRAFT_KEY,
          name: 'Ad-hoc Script',
          script: DEFAULT_SCRIPT,
        } as Task,
        draft: { script: adhocDraft.script, timestamp: adhocDraft.timestamp },
        savedScript: DEFAULT_SCRIPT,
        firstExampleInput: '',
        avgTime: null,
        preserveInput: false,
      });
    } else {
      setState((prev) => ({
        ...prev,
        selectedTask: null,
        scriptContent: DEFAULT_SCRIPT,
        isDirty: false,
        isAdHocMode: true,
        input: '',
        estimatedTime: null,
        elapsedTime: 0,
        showProgress: false,
        completedOutput: null,
        fromTaskRunId: null,
        selectedExample: '',
      }));
    }
    clearTaskRunState();
  }, [draftStore, clearTaskRunState]);

  // Handle task selection
  const handleTaskChange = useCallback(
    async (taskId: string, preserveInput = false) => {
      // Save current draft immediately before switching tasks
      saveDraftBeforeSwitch();

      if (!taskId || taskId === ADHOC_DRAFT_KEY) {
        switchToAdHocMode();
        return;
      }

      const [taskResponse] = await runSafe(backendApi.getTask(taskId), 'getTask', {
        action: 'fetching task details',
        entityId: taskId,
      });

      if (!taskResponse) {
        // Task not found (404) or fetch failed — clean up invalid taskId from URL
        onClearTaskId?.();
        clearError();
        return;
      }

      const selectedTask = taskResponse;

      let firstExampleInput = '';
      if (
        !preserveInput &&
        selectedTask.data_samples &&
        Array.isArray(selectedTask.data_samples) &&
        selectedTask.data_samples.length > 0
      ) {
        const firstSample = selectedTask.data_samples[0];
        const inputData = (firstSample as DataSample)?.input || firstSample;
        firstExampleInput =
          typeof inputData === 'string' ? inputData : JSON.stringify(inputData, null, 2);
      }

      const avgTime = await calculateAverageExecutionTime(taskId);

      // Check for unsaved draft
      const draft = draftStore.loadDraft(taskId);
      const savedScript = selectedTask.script || '';

      if (draft && draft.script !== savedScript) {
        setPendingDraftRestore({
          taskId,
          task: selectedTask,
          draft: { script: draft.script, timestamp: draft.timestamp },
          savedScript,
          firstExampleInput,
          avgTime,
          preserveInput,
        });
      } else {
        setState((prev) => ({
          ...prev,
          selectedTask,
          scriptContent: savedScript,
          isDirty: false,
          isAdHocMode: false,
          input: preserveInput ? prev.input : firstExampleInput,
          estimatedTime: avgTime,
          elapsedTime: 0,
          showProgress: false,
          completedOutput: null,
          fromTaskRunId: preserveInput ? prev.fromTaskRunId : null,
          selectedExample: preserveInput && prev.fromTaskRunId ? 'task-run' : '',
        }));
      }
      // User-initiated task switch clears task run anchoring
      if (!preserveInput && state.fromTaskRunId) {
        onClearTaskRunId?.();
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- state.fromTaskRunId only used for guard, not reactive
    [
      runSafe,
      calculateAverageExecutionTime,
      draftStore,
      saveDraftBeforeSwitch,
      switchToAdHocMode,
      onClearTaskRunId,
      onClearTaskId,
      clearError,
    ]
  );

  // Handle loading a recent task run into the editor
  const handleLoadTaskRun = useCallback(
    (run: (typeof recentTaskRuns)[number]) => {
      saveDraftBeforeSwitch();

      // For task-based runs, load the task
      if (run.task_id) {
        void handleTaskChange(run.task_id);
        return;
      }

      // For ad-hoc runs, load the script and input directly from the run
      setState((prev) => ({
        ...prev,
        selectedTask: null,
        scriptContent: run.cy_script || DEFAULT_SCRIPT,
        isDirty: false,
        isAdHocMode: true,
        input: parseTaskRunInput(run.input_type, run.input_location),
        estimatedTime: null,
        elapsedTime: 0,
        showProgress: false,
        completedOutput: null,
        fromTaskRunId: run.id,
        selectedExample: '',
      }));
    },
    [saveDraftBeforeSwitch, handleTaskChange]
  );

  // Handle draft restore confirmation
  const handleRestoreDraft = useCallback(() => {
    if (!pendingDraftRestore) return;

    const { taskId, task, draft, firstExampleInput, avgTime, preserveInput } = pendingDraftRestore;
    const isAdHoc = taskId === ADHOC_DRAFT_KEY;

    setState((prev) => ({
      ...prev,
      selectedTask: isAdHoc ? null : task,
      scriptContent: draft.script,
      isDirty: true,
      isAdHocMode: isAdHoc,
      input: preserveInput ? prev.input : firstExampleInput,
      estimatedTime: avgTime,
      elapsedTime: 0,
      showProgress: false,
      completedOutput: null,
      fromTaskRunId: prev.fromTaskRunId,
      selectedExample: prev.fromTaskRunId ? 'task-run' : '',
    }));

    setPendingDraftRestore(null);
  }, [pendingDraftRestore]);

  // Handle draft discard
  const handleDiscardDraft = useCallback(() => {
    if (!pendingDraftRestore) return;

    const { taskId, task, savedScript, firstExampleInput, avgTime, preserveInput } =
      pendingDraftRestore;
    const isAdHoc = taskId === ADHOC_DRAFT_KEY;

    // Clear the draft
    draftStore.clearDraft(taskId);

    setState((prev) => ({
      ...prev,
      selectedTask: isAdHoc ? null : task,
      scriptContent: savedScript,
      isDirty: false,
      isAdHocMode: isAdHoc,
      input: preserveInput ? prev.input : firstExampleInput,
      estimatedTime: avgTime,
      elapsedTime: 0,
      showProgress: false,
      completedOutput: null,
      fromTaskRunId: prev.fromTaskRunId,
      selectedExample: prev.fromTaskRunId ? 'task-run' : '',
    }));

    setPendingDraftRestore(null);
  }, [pendingDraftRestore, draftStore]);

  // Check for ad-hoc draft on initial mount (when starting in ad-hoc mode with no props)
  useEffect(() => {
    // Only run on mount when no taskId is provided (default ad-hoc mode)
    if (!taskId && !isAdHoc && !cyScript) {
      const adhocDraft = draftStore.loadDraft(ADHOC_DRAFT_KEY);

      if (adhocDraft && adhocDraft.script !== DEFAULT_SCRIPT) {
        setPendingDraftRestore({
          taskId: ADHOC_DRAFT_KEY,
          task: {
            id: ADHOC_DRAFT_KEY,
            name: 'Ad-hoc Script',
            script: DEFAULT_SCRIPT,
          } as Task,
          draft: { script: adhocDraft.script, timestamp: adhocDraft.timestamp },
          savedScript: DEFAULT_SCRIPT,
          firstExampleInput: '',
          avgTime: null,
          preserveInput: false,
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount

  // Handle incoming task from navigation
  useEffect(() => {
    if (isAdHoc && cyScript) {
      setState((prev) => ({
        ...prev,
        isAdHocMode: true,
        scriptContent: cyScript,
        isDirty: true,
        selectedTask: null,
        input: typeof inputData === 'string' ? inputData : JSON.stringify(inputData || {}, null, 2),
        fromTaskRunId: taskRunId || null,
        selectedExample: taskRunId ? 'task-run' : '',
      }));
    } else if (taskId && !state.selectedTask) {
      if (inputData !== undefined || taskRunId) {
        const inputString =
          typeof inputData === 'string' ? inputData : JSON.stringify(inputData, null, 2);

        setState((prev) => ({
          ...prev,
          input: inputString,
          fromTaskRunId: taskRunId || null,
          selectedExample: taskRunId ? 'task-run' : '',
        }));

        void handleTaskChange(taskId, true);
      } else {
        void handleTaskChange(taskId, false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId, inputData, taskRunId, cyScript, isAdHoc]);

  // Fetch output (and input for deep links) from the task run
  useEffect(() => {
    if (!taskRunId) return;
    let cancelled = false;

    void (async () => {
      const [details] = await runSafe<TaskRunDetailsResponse>(
        backendApi.getTaskRunDetails(taskRunId) as Promise<TaskRunDetailsResponse>,
        'loadTaskRunOutput',
        { action: 'loading task run output', entityId: taskRunId }
      );

      if (cancelled || !details) {
        // Invalid taskRunId — clear it from URL
        if (!details) onClearTaskRunId?.();
        return;
      }

      const { output: parsed } = parseExecutionOutput(details);
      const outputStr = JSON.stringify(parsed, null, 2);

      // Deep link case: no inputData prop was passed, extract input from API response
      const needsInput = inputData === undefined;
      const inputStr = needsInput
        ? parseTaskRunInput(details.input_type, details.input_location)
        : undefined;

      // Deep link case: no taskId prop was passed, derive from API response
      const needsTask = !taskId && details.task_id;

      setState((prev) => ({
        ...prev,
        output: outputStr,
        lastExecutionStatus: details.status ?? 'completed',
        ...(inputStr !== undefined ? { input: inputStr, selectedExample: 'task-run' } : {}),
      }));

      // Fetch logs for this task run
      const [logsResult] = await runSafe(backendApi.getTaskRunLogs(taskRunId), 'loadTaskRunLogs', {
        action: 'loading task run logs',
        entityId: taskRunId,
      });
      if (!cancelled && logsResult?.has_logs) {
        setState((prev) => ({ ...prev, logEntries: logsResult.entries }));
      }

      // Load the parent task if we derived the taskId from the response
      if (needsTask && details.task_id) {
        void handleTaskChange(details.task_id, true);
      }
    })();

    return () => {
      cancelled = true;
    };
    // Only run when taskRunId changes (on mount from navigation)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskRunId]);

  // Handle script content changes
  const handleScriptChange = useCallback((newContent: string) => {
    if (editorRef.current) {
      const editor = editorRef.current;
      const session = editor.getSession();
      session.clearAnnotations();
      const markers = session.getMarkers();
      if (markers) {
        Object.keys(markers).forEach((markerId) => {
          session.removeMarker(parseInt(markerId, 10));
        });
      }
    }

    setState((prev) => {
      const isDirty = prev.isAdHocMode
        ? newContent.trim() !== ''
        : newContent !== (prev.selectedTask?.script || '');
      return {
        ...prev,
        scriptContent: newContent,
        isDirty,
      };
    });
  }, []);

  // Handle save functionality
  const handleSave = useCallback(async () => {
    if (!state.selectedTask || !state.isDirty) return;

    setState((prev) => ({ ...prev, isSaving: true }));

    const [result] = await runSafe(
      backendApi.updateTask(state.selectedTask.id, {
        script: state.scriptContent,
      }),
      'saveScript',
      {
        action: 'saving script changes',
        entityId: state.selectedTask.id,
        entityType: 'task',
      }
    );

    if (result) {
      // Clear draft on successful save
      if (state.selectedTask) {
        draftStore.clearDraft(state.selectedTask.id);
      }
      setState((prev) => ({
        ...prev,
        isDirty: false,
        isSaving: false,
        selectedTask: prev.selectedTask
          ? {
              ...prev.selectedTask,
              script: state.scriptContent,
            }
          : null,
      }));
    } else {
      setState((prev) => ({ ...prev, isSaving: false }));
    }
  }, [state.selectedTask, state.scriptContent, state.isDirty, runSafe, draftStore]);

  // Handle save click - if no task selected (ad-hoc mode or no task loaded), open Save As
  const handleSaveClick = useCallback(() => {
    if (state.isAdHocMode || !state.selectedTask) {
      setShowSaveAsModal(true);
    } else {
      void handleSave();
    }
  }, [state.isAdHocMode, state.selectedTask, handleSave]);

  // Handle new script (clear editor and enter ad-hoc mode)
  const handleNew = useCallback(() => {
    // Check for unsaved changes - show unsaved changes dialog
    if (state.isDirty) {
      setShowUnsavedChangesDialog(true);
      return;
    }

    // No unsaved changes, proceed directly
    setState((prev) => ({
      ...prev,
      selectedTask: null,
      scriptContent: DEFAULT_SCRIPT,
      isDirty: false,
      isAdHocMode: true,
      input: '',
      output: '',
      selectedExample: '',
    }));
  }, [state.isDirty]);

  // Proceed with New action (after save or discard)
  const proceedWithNew = useCallback(() => {
    setState((prev) => ({
      ...prev,
      selectedTask: null,
      scriptContent: DEFAULT_SCRIPT,
      isDirty: false,
      isAdHocMode: true,
      input: '',
      output: '',
      selectedExample: '',
    }));
  }, []);

  // Handle "Save" option from unsaved changes dialog
  const handleSaveAndNew = useCallback(async () => {
    setShowUnsavedChangesDialog(false);
    setPendingNewAfterSave(true);
    await handleSave();
  }, [handleSave]);

  // Handle "Save As" option from unsaved changes dialog
  const handleSaveAsAndNew = useCallback(() => {
    setShowUnsavedChangesDialog(false);
    setPendingNewAfterSave(true);
    setShowSaveAsModal(true);
  }, []);

  // Handle "Discard" option from unsaved changes dialog
  const handleDiscardAndNew = useCallback(() => {
    // Clear draft if discarding changes
    if (state.selectedTask) {
      draftStore.clearDraft(state.selectedTask.id);
    }
    setShowUnsavedChangesDialog(false);
    proceedWithNew();
  }, [state.selectedTask, draftStore, proceedWithNew]);

  // Navigation blocker dialog handlers
  const handleNavCancel = useCallback(() => {
    setShowNavBlockerDialog(false);
    blockerRef.current.reset?.();
  }, []);

  const handleNavDiscard = useCallback(() => {
    if (state.selectedTask) {
      draftStore.clearDraft(state.selectedTask.id);
    } else if (state.isAdHocMode) {
      draftStore.clearDraft(ADHOC_DRAFT_KEY);
    }
    setShowNavBlockerDialog(false);
    blockerRef.current.proceed?.();
  }, [state.selectedTask, state.isAdHocMode, draftStore]);

  const handleNavSave = useCallback(async () => {
    setShowNavBlockerDialog(false);
    setPendingNavAfterSave(true);
    await handleSave();
  }, [handleSave]);

  const handleNavSaveAs = useCallback(() => {
    setShowNavBlockerDialog(false);
    setPendingNavAfterSave(true);
    setShowSaveAsModal(true);
  }, []);

  // Reload dialog handlers (for keyboard refresh shortcuts)
  const handleReloadCancel = useCallback(() => {
    setShowReloadDialog(false);
    setPendingReloadAfterSave(false);
  }, []);

  const handleReloadDiscard = useCallback(() => {
    setShowReloadDialog(false);
    window.location.reload();
  }, []);

  const handleReloadSave = useCallback(async () => {
    setShowReloadDialog(false);
    setPendingReloadAfterSave(true);
    await handleSave();
  }, [handleSave]);

  const handleReloadSaveAs = useCallback(() => {
    setShowReloadDialog(false);
    setPendingReloadAfterSave(true);
    setShowSaveAsModal(true);
  }, []);

  // Handle save as success (new task created)
  const handleSaveAsSuccess = useCallback(
    (newTask: Task) => {
      // Switch to the new task first
      setState((prev) => ({
        ...prev,
        selectedTask: newTask,
        scriptContent: newTask.script || prev.scriptContent,
        isDirty: false,
        isAdHocMode: false,
      }));

      // Check if we should proceed with New after saving
      if (pendingNewAfterSave) {
        setPendingNewAfterSave(false);
        proceedWithNew();
      }
      // Check if we should proceed with navigation after saving
      if (pendingNavAfterSave) {
        setPendingNavAfterSave(false);
        blockerRef.current.proceed?.();
      }
      // Check if we should reload after saving
      if (pendingReloadAfterSave) {
        setPendingReloadAfterSave(false);
        window.location.reload();
      }
      // Note: pendingRunAfterSave is handled by the useEffect that watches for save completion
    },
    [pendingNewAfterSave, pendingNavAfterSave, pendingReloadAfterSave, proceedWithNew]
  );

  // Handle AI task generation completion
  const handleTaskGenerationComplete = useCallback(
    (taskId: string, _taskName: string) => {
      // Load the generated task into the editor
      void handleTaskChange(taskId, false);
    },
    [handleTaskChange]
  );

  // Handle polling completion - extracted to avoid excessive nesting in startPolling callback
  const handlePollingComplete = useCallback(
    async (trid: string, result: { status: string } | undefined) => {
      if (!result) {
        setState((prev) => ({
          ...prev,
          isRunning: false,
          currentTrid: null,
          output: 'Failed to get task status',
          lastExecutionStatus: 'error',
        }));
        return;
      }

      const executionStatus = result.status;

      const [detailsResult] = await runSafe<TaskRunDetailsResponse>(
        backendApi.getTaskRunDetails(trid) as Promise<TaskRunDetailsResponse>,
        'getTaskRunDetails',
        { action: 'fetching task results', entityId: trid }
      );

      if (!detailsResult) {
        setState((prev) => ({
          ...prev,
          isRunning: false,
          currentTrid: null,
          output: `Task ${result.status} but failed to fetch results`,
          startTime: null,
          lastExecutionStatus: executionStatus,
        }));
        return;
      }

      const { output: parsed } = parseExecutionOutput(detailsResult);
      const finalOutput = JSON.stringify(parsed, null, 2);

      // Fetch execution logs (fire-and-forget — don't block output display)
      void (async () => {
        const [logsResult] = await runSafe(backendApi.getTaskRunLogs(trid), 'getTaskRunLogs', {
          action: 'fetching task logs',
          entityId: trid,
        });
        if (logsResult?.has_logs) {
          setState((prev) => ({ ...prev, logEntries: logsResult.entries }));
        }
      })();

      const minDisplayTime = 500;
      const elapsedMs = state.startTime ? Date.now() - state.startTime : 0;
      const remainingDisplayTime = Math.max(0, minDisplayTime - elapsedMs);

      const clearElapsedTimer = () => {
        if (elapsedTimerRef.current) {
          clearInterval(elapsedTimerRef.current);
          elapsedTimerRef.current = null;
        }
      };

      if (remainingDisplayTime > 0) {
        setState((prev) => ({
          ...prev,
          completedOutput: finalOutput,
          lastExecutionStatus: executionStatus,
        }));

        setTimeout(() => {
          setState((prev) => ({
            ...prev,
            isRunning: false,
            currentTrid: null,
            output: prev.completedOutput || '',
            showProgress: false,
            startTime: null,
          }));
          clearElapsedTimer();
        }, remainingDisplayTime);
      } else {
        setState((prev) => ({
          ...prev,
          isRunning: false,
          currentTrid: null,
          output: finalOutput,
          showProgress: false,
          startTime: null,
          completedOutput: null,
          lastExecutionStatus: executionStatus,
        }));
        clearElapsedTimer();
      }
    },
    [runSafe, state.startTime]
  );

  // HITL: fetch task details when paused and update UI with paused state
  const fetchPausedDetails = useCallback(
    async (trid: string) => {
      const [details] = await runSafe<TaskRunDetailsResponse>(
        backendApi.getTaskRunDetails(trid) as Promise<TaskRunDetailsResponse>,
        'getTaskRunDetails',
        { action: 'fetching paused task details', entityId: trid }
      );
      if (details) {
        const { output: parsed } = parseExecutionOutput(details);
        setState((prev) => ({
          ...prev,
          output: JSON.stringify(parsed, null, 2),
          lastExecutionStatus: 'paused',
          showProgress: false,
        }));
      }
    },
    [runSafe]
  );

  // Poll task status until completion
  const pollTaskStatus = useCallback(
    (trid: string) => {
      if (pollingControllerRef.current) {
        pollingControllerRef.current.stop();
      }

      pollingControllerRef.current = startPolling({
        pollFn: async () => {
          const [statusResult] = await runSafe(
            backendApi.getTaskRunStatus(trid),
            'pollTaskStatus',
            { action: 'polling task status', entityId: trid }
          );
          return statusResult;
        },

        shouldStop: (result) => {
          if (!result) return true;
          // HITL: keep polling for paused tasks — they'll resume after human response
          return result.status !== 'running' && result.status !== 'paused';
        },

        onPoll: (result, attemptNumber) => {
          if (result) {
            console.info(`[Polling] Attempt ${attemptNumber}, Status: ${result.status}`);
            // HITL: when task transitions to paused, fetch details and show paused UI
            if (result.status === 'paused') {
              void fetchPausedDetails(trid);
            }
          }
        },

        onComplete: (result) => {
          void handlePollingComplete(trid, result);
        },

        onError: (error, attemptNumber) => {
          console.error(`Polling error at attempt ${attemptNumber}:`, error);
          setState((prev) => ({
            ...prev,
            output: `Error polling task status (attempt ${attemptNumber}): ${error.message}`,
          }));
        },

        // First 10s: poll every 1s for snappy feedback, then backoff
        delayIntervals: [
          1000,
          1000,
          1000,
          1000,
          1000,
          1000,
          1000,
          1000,
          1000,
          1000, // 10× 1s
          2000,
          3000,
          5000,
          10_000,
        ],
        maxTotalTime: 3_600_000, // 1 hour — HITL tasks can be paused for extended periods
        maxAttempts: 1000,
        stopOnError: false,
      });
    },
    [runSafe, handlePollingComplete]
  );

  // Handle copy functionality
  const handleCopy = useCallback((text: string, section: string) => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopiedSection(section);
      setTimeout(() => setCopiedSection(null), 2000);
    });
  }, []);

  // Find all occurrences of a tool in the script
  const findToolOccurrences = useCallback(
    (toolName: string): Array<{ line: number; column: number }> => {
      const content = state.scriptContent;
      const lines = content.split('\n');
      const occurrences: Array<{ line: number; column: number }> = [];

      // Search terms: handle both full FQN and short name for native tools
      const searchTerms = [toolName];
      if (toolName.startsWith('native::')) {
        const parts = toolName.split('::');
        if (parts.length >= 3) {
          searchTerms.push(parts[parts.length - 1]); // Short name
        }
      }

      for (let i = 0; i < lines.length; i++) {
        for (const term of searchTerms) {
          let startIndex = 0;
          let index: number;
          // Find all occurrences on this line
          while ((index = lines[i].indexOf(term, startIndex)) !== -1) {
            occurrences.push({ line: i + 1, column: index });
            startIndex = index + term.length;
          }
        }
      }

      return occurrences;
    },
    [state.scriptContent]
  );

  // Navigate to tool usage in the editor (cycles through multiple occurrences)
  const navigateToTool = useCallback(
    (toolName: string) => {
      if (!editorRef.current) return;

      const editor = editorRef.current;
      const occurrences = findToolOccurrences(toolName);

      if (occurrences.length === 0) return;

      // Get current occurrence index (default to -1 so first click goes to 0)
      const currentIndex = toolOccurrenceIndexRef.current.get(toolName) ?? -1;
      // Cycle to next occurrence
      const nextIndex = (currentIndex + 1) % occurrences.length;
      toolOccurrenceIndexRef.current.set(toolName, nextIndex);

      const occurrence = occurrences[nextIndex];
      editor.gotoLine(occurrence.line, occurrence.column, true);
      editor.focus();
    },
    [findToolOccurrences]
  );

  // Get count of tool occurrences (for displaying "1 of N" indicator)
  const getToolOccurrenceCount = useCallback(
    (toolName: string): number => {
      return findToolOccurrences(toolName).length;
    },
    [findToolOccurrences]
  );

  // Execute the task (actual execution logic)
  const executeRun = useCallback(async () => {
    if (state.isRunning) return;

    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
    }

    // New execution replaces viewed task run
    clearTaskRunState();

    const startTime = Date.now();
    setState((prev) => ({
      ...prev,
      isRunning: true,
      output: 'Task execution in progress...\nPolling for results...',
      startTime,
      elapsedTime: 0,
      showProgress: true,
      completedOutput: null,
      lastExecutionStatus: null,
      fromTaskRunId: null,
      logEntries: [],
      outputTab: 'result',
    }));

    elapsedTimerRef.current = setInterval(() => {
      setState((prev) => ({
        ...prev,
        elapsedTime: Math.floor((Date.now() - startTime) / 1000),
      }));
    }, 100);

    let inputData: unknown;
    try {
      inputData = state.input ? (JSON.parse(state.input) as unknown) : {};
    } catch {
      inputData = state.input || '';
    }

    let executionResult;

    if (state.selectedTask) {
      // Run saved task by ID
      trackExecute('task', {
        entityId: state.selectedTask.id,
        entityName: state.selectedTask.name,
      });

      [executionResult] = await runSafe(
        backendApi.executeTask(state.selectedTask.id, inputData as Record<string, unknown>),
        'executeTask',
        {
          action: 'executing saved task',
          entityId: state.selectedTask.id,
          entityType: 'task',
          meta: { input: inputData },
        }
      );
    } else if (state.scriptContent.trim()) {
      // Run ad-hoc script
      trackExecute('ad-hoc-script', {
        params: { scriptLength: state.scriptContent.length },
      });

      [executionResult] = await runSafe(
        backendApi.executeAdHocScript(state.scriptContent, inputData as Record<string, unknown>),
        'executeAdHocScript',
        {
          action: 'executing ad-hoc script',
          meta: { scriptLength: state.scriptContent.length, input: inputData },
        }
      );
    } else {
      setState((prev) => ({
        ...prev,
        isRunning: false,
        output: 'Error: No task selected and no script content to execute',
      }));
      return;
    }

    if (executionResult) {
      setState((prev) => ({
        ...prev,
        currentTrid: executionResult.trid,
        output: `Task initiated (TRID: ${executionResult.trid})\nStatus: ${executionResult.status}\nPolling for results...`,
      }));

      pollTaskStatus(executionResult.trid);
    } else {
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }

      setState((prev) => ({
        ...prev,
        isRunning: false,
        output: 'Failed to initiate task execution',
        startTime: null,
      }));
    }
  }, [
    state.selectedTask,
    state.scriptContent,
    state.input,
    state.isRunning,
    runSafe,
    pollTaskStatus,
    trackExecute,
    clearTaskRunState,
  ]);

  // Handle run button - show dialog if there are unsaved changes to a saved task
  const handleRun = useCallback(() => {
    if (state.isRunning) return;

    // If editing a saved task with unsaved changes, show the dialog
    if (state.selectedTask && state.isDirty) {
      setShowRunUnsavedDialog(true);
      return;
    }

    // Otherwise, run directly
    void executeRun();
  }, [state.isRunning, state.selectedTask, state.isDirty, executeRun]);

  // Handle "Save and Run" from the run unsaved dialog
  const handleSaveAndRun = useCallback(async () => {
    setShowRunUnsavedDialog(false);
    setPendingRunAfterSave(true);
    await handleSave();
  }, [handleSave]);

  // Handle "Save As and Run" from the run unsaved dialog
  const handleSaveAsAndRun = useCallback(() => {
    setShowRunUnsavedDialog(false);
    setPendingRunAfterSave(true);
    setShowSaveAsModal(true);
  }, []);

  // Effect to proceed with pending actions after Save completes
  useEffect(() => {
    // If we were waiting for save to complete and it's now done (not dirty, not saving)
    if (!state.isDirty && !state.isSaving) {
      if (pendingNewAfterSave) {
        setPendingNewAfterSave(false);
        proceedWithNew();
      } else if (pendingRunAfterSave) {
        setPendingRunAfterSave(false);
        void executeRun();
      } else if (pendingNavAfterSave) {
        setPendingNavAfterSave(false);
        blockerRef.current.proceed?.();
      } else if (pendingReloadAfterSave) {
        setPendingReloadAfterSave(false);
        window.location.reload();
      }
    }
  }, [
    pendingNewAfterSave,
    pendingRunAfterSave,
    pendingNavAfterSave,
    pendingReloadAfterSave,
    state.isDirty,
    state.isSaving,
    proceedWithNew,
    executeRun,
  ]);

  // Keep the editor's __aiEnabledRef in sync with aiAutocompleteEnabled state
  useEffect(() => {
    if (!editorRef.current) return;
    const ref = (editorRef.current as unknown as AceEditorWithAiRef).__aiEnabledRef;
    if (ref) ref.current = aiAutocompleteEnabled;
    if (!aiAutocompleteEnabled) cancelAiCompletion();
  }, [aiAutocompleteEnabled]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollingControllerRef.current) {
        pollingControllerRef.current.stop();
      }
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
      }
      cancelAiCompletion();
    };
  }, []);

  // Toggle sidebar
  const toggleSidebar = useCallback(() => {
    if (layout.isSidebarCollapsed) {
      sidebarPanelRef.current?.expand();
    } else {
      sidebarPanelRef.current?.collapse();
    }
    setLayout((prev) => ({ ...prev, isSidebarCollapsed: !prev.isSidebarCollapsed }));
  }, [layout.isSidebarCollapsed]);

  // Toggle bottom panel
  const toggleBottomPanel = useCallback(() => {
    if (layout.isBottomPanelCollapsed) {
      bottomPanelRef.current?.expand();
    } else {
      bottomPanelRef.current?.collapse();
    }
    setLayout((prev) => ({ ...prev, isBottomPanelCollapsed: !prev.isBottomPanelCollapsed }));
  }, [layout.isBottomPanelCollapsed]);

  // Handle example selection
  const handleExampleChange = useCallback(
    (exampleIndex: string) => {
      if (!state.selectedTask?.data_samples) return;

      const index = parseInt(exampleIndex, 10);
      if (isNaN(index) || index < 0 || index >= state.selectedTask.data_samples.length) return;

      const sample = state.selectedTask.data_samples[index];
      const inputData = (sample as DataSample)?.input || sample;
      const inputString =
        typeof inputData === 'string' ? inputData : JSON.stringify(inputData, null, 2);

      setState((prev) => {
        if (prev.fromTaskRunId) onClearTaskRunId?.();
        return {
          ...prev,
          input: inputString,
          selectedExample: exampleIndex,
          fromTaskRunId: null,
        };
      });
    },
    [state.selectedTask?.data_samples, onClearTaskRunId]
  );

  // Keyboard shortcuts (extracted to custom hook)
  useWorkbenchKeyboardShortcuts({
    toggleSidebar,
    toggleBottomPanel,
    isRunning: state.isRunning,
    selectedTask: state.selectedTask,
    scriptContent: state.scriptContent,
    isDirty: state.isDirty,
    handleRun,
    setShowReloadDialog,
  });

  // Auto-save draft when script changes (debounced, extracted to custom hook)
  useAutoSaveDraft({
    isDirty: state.isDirty,
    isAdHocMode: state.isAdHocMode,
    scriptContent: state.scriptContent,
    selectedTask: state.selectedTask,
  });

  // Script analysis - analyze tools used (extracted to custom hook)
  useScriptAnalysis({
    scriptContent: state.scriptContent,
    selectedTask: state.selectedTask,
    isDirty: state.isDirty,
    setScriptAnalysis,
  });

  // Error highlighting in editor
  useEffect(() => {
    if (!editorRef.current) return;

    const editor = editorRef.current;
    const session = editor.getSession();

    // Clear existing annotations and markers
    session.clearAnnotations();
    const markers = session.getMarkers();
    if (markers) {
      Object.keys(markers).forEach((markerId) => {
        session.removeMarker(parseInt(markerId, 10));
      });
    }

    // Check if task failed and output contains error with location information
    const output = state.completedOutput || state.output;
    const isErrorStatus =
      state.lastExecutionStatus === 'failed' || state.lastExecutionStatus === 'error';
    if (!output || !isErrorStatus) return;

    const errorLocation = parseErrorLocation(output);
    if (!errorLocation) return;

    // Add annotation (shows error icon in gutter and tooltip on hover)
    session.setAnnotations([
      {
        row: errorLocation.line - 1, // Ace uses 0-based line indexing
        column: errorLocation.column,
        text: errorLocation.message,
        type: 'error',
      },
    ]);

    // Add marker to highlight the error line
    if (window.ace) {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-call, @typescript-eslint/no-unsafe-member-access
      const aceRangeModule = window.ace.require('ace/range') as AceRangeModule | undefined;
      if (aceRangeModule) {
        const AceRange = aceRangeModule.Range;
        session.addMarker(
          new AceRange(
            errorLocation.line - 1,
            0,
            errorLocation.line - 1,
            Number.MAX_VALUE
          ) as import('ace-builds').Ace.Range,
          'ace-error-line', // CSS class defined in index.css
          'fullLine'
        );
      }
    }

    // Scroll viewport to center on the error line
    editor.gotoLine(errorLocation.line, errorLocation.column, true);
  }, [state.output, state.completedOutput, state.lastExecutionStatus]);

  return (
    <div className="h-full flex flex-col bg-dark-900">
      {/* Main layout with resizable panels */}
      <div className="flex-1 min-h-0">
        <Group
          orientation="horizontal"
          defaultLayout={mainLayout}
          onLayoutChanged={onMainLayoutChanged}
        >
          {/* Sidebar */}
          <Panel
            panelRef={sidebarPanelRef}
            defaultSize="20"
            minSize="5"
            maxSize="30"
            collapsible
            collapsedSize="3"
            id="sidebar"
            className="bg-dark-800 border-r border-gray-700"
          >
            <div className="h-full flex flex-col">
              {!layout.isSidebarCollapsed ? (
                <>
                  <div className="p-4 border-b border-gray-700">
                    <div className="flex items-center justify-between mb-3">
                      <h2 className="text-sm font-semibold text-white">Tasks</h2>
                      <button
                        onClick={toggleSidebar}
                        className="p-1 text-gray-400 hover:text-white hover:bg-dark-700 rounded-sm"
                        title="Toggle sidebar (Ctrl+B)"
                      >
                        <ChevronDoubleLeftIcon className="h-4 w-4" />
                      </button>
                    </div>
                    <TaskSelector
                      selectedTask={state.selectedTask}
                      onTaskChange={(taskId) => void handleTaskChange(taskId)}
                      isAdHocMode={state.isAdHocMode}
                    />
                  </div>
                  <div className="flex-1 overflow-y-auto p-4">
                    {state.selectedTask ? (
                      <div className="space-y-3">
                        <div>
                          <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">
                            Selected Task
                          </h3>
                          <p className="text-base font-medium text-white">
                            {state.selectedTask.name}
                          </p>
                        </div>
                        {state.selectedTask.description && (
                          <div>
                            <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">
                              Description
                            </h3>
                            <p className="text-sm text-gray-300 leading-relaxed">
                              {state.selectedTask.description}
                            </p>
                          </div>
                        )}
                        {/* Dependencies section */}
                        {(scriptAnalysis.tools_used || scriptAnalysis.isLoading) && (
                          <div>
                            <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">
                              Dependencies
                              {scriptAnalysis.isLoading && (
                                <span className="ml-2 text-gray-500">...</span>
                              )}
                            </h3>
                            {scriptAnalysis.tools_used && scriptAnalysis.tools_used.length > 0 ? (
                              <div className="flex flex-col gap-1">
                                {scriptAnalysis.tools_used
                                  .filter((tool) => !tool.startsWith('__')) // Filter internal tools
                                  .sort((a, b) => a.localeCompare(b))
                                  .map((tool) => {
                                    const namespace = tool.split('::')[0];
                                    const occurrenceCount = getToolOccurrenceCount(tool);
                                    return (
                                      <button
                                        key={tool}
                                        onClick={() => navigateToTool(tool)}
                                        className={`px-1.5 py-0.5 rounded text-xs font-mono cursor-pointer hover:ring-1 hover:ring-white/30 transition-all flex items-center gap-1 w-fit ${getToolNamespaceClasses(
                                          namespace
                                        )}`}
                                        title={
                                          occurrenceCount > 1
                                            ? `Click to cycle through ${occurrenceCount} usages of ${tool}`
                                            : `Go to ${tool}`
                                        }
                                      >
                                        {tool}
                                        {occurrenceCount > 1 && (
                                          <span className="bg-white/20 px-1 rounded-sm text-[10px]">
                                            ×{occurrenceCount}
                                          </span>
                                        )}
                                      </button>
                                    );
                                  })}
                              </div>
                            ) : (
                              !scriptAnalysis.isLoading && (
                                <p className="text-xs text-gray-500">No external tools used</p>
                              )
                            )}
                          </div>
                        )}
                        {/* Feedback section */}
                        <TaskFeedbackSection taskId={state.selectedTask.id} />
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <p className="text-sm text-gray-400">
                          Select a task or create a new ad-hoc script
                        </p>
                        {/* Dependencies for ad-hoc mode */}
                        {(scriptAnalysis.tools_used || scriptAnalysis.isLoading) && (
                          <div>
                            <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">
                              Dependencies
                              {scriptAnalysis.isLoading && (
                                <span className="ml-2 text-gray-500">...</span>
                              )}
                            </h3>
                            {scriptAnalysis.tools_used && scriptAnalysis.tools_used.length > 0 ? (
                              <div className="flex flex-col gap-1">
                                {scriptAnalysis.tools_used
                                  .filter((tool) => !tool.startsWith('__')) // Filter internal tools
                                  .sort((a, b) => a.localeCompare(b))
                                  .map((tool) => {
                                    const namespace = tool.split('::')[0];
                                    const occurrenceCount = getToolOccurrenceCount(tool);
                                    return (
                                      <button
                                        key={tool}
                                        onClick={() => navigateToTool(tool)}
                                        className={`px-1.5 py-0.5 rounded text-xs font-mono cursor-pointer hover:ring-1 hover:ring-white/30 transition-all flex items-center gap-1 w-fit ${getToolNamespaceClasses(
                                          namespace
                                        )}`}
                                        title={
                                          occurrenceCount > 1
                                            ? `Click to cycle through ${occurrenceCount} usages of ${tool}`
                                            : `Go to ${tool}`
                                        }
                                      >
                                        {tool}
                                        {occurrenceCount > 1 && (
                                          <span className="bg-white/20 px-1 rounded-sm text-[10px]">
                                            ×{occurrenceCount}
                                          </span>
                                        )}
                                      </button>
                                    );
                                  })}
                              </div>
                            ) : (
                              !scriptAnalysis.isLoading && (
                                <p className="text-xs text-gray-500">No external tools used</p>
                              )
                            )}
                          </div>
                        )}
                      </div>
                    )}
                    {!state.selectedTask && recentTaskRuns.length > 0 && (
                      <div className="space-y-2 mt-2">
                        <h3 className="text-xs font-medium text-gray-400 uppercase mb-2">
                          Recent Task Runs
                        </h3>
                        {recentTaskRuns.map((run) => (
                          <button
                            key={run.id}
                            onClick={() => handleLoadTaskRun(run)}
                            className="w-full text-left px-3 py-2 rounded-md bg-dark-700 hover:bg-dark-600 transition-colors border border-gray-700 hover:border-gray-500"
                          >
                            <div className="text-xs font-medium text-gray-200 truncate">
                              {run.task_name || run.task_id?.slice(0, 16) || 'Ad-hoc run'}
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span
                                className={`text-[10px] font-medium ${getStatusClasses(
                                  run.status
                                )}`}
                              >
                                {run.status}
                              </span>
                              <span className="text-[10px] text-gray-500">
                                {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                              </span>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center py-4 gap-3">
                  <button
                    onClick={toggleSidebar}
                    className="p-2 text-gray-400 hover:text-white hover:bg-dark-700 rounded-sm"
                    title="Expand sidebar"
                  >
                    <ChevronDoubleRightIcon className="h-5 w-5" />
                  </button>
                  <CodeBracketIcon className="h-5 w-5 text-gray-400" />
                </div>
              )}
            </div>
          </Panel>

          <Separator className="w-1 bg-gray-700 hover:bg-blue-500 transition-colors cursor-col-resize" />

          {/* Main content area */}
          <Panel minSize="30">
            <Group
              orientation="vertical"
              defaultLayout={verticalLayout}
              onLayoutChanged={onVerticalLayoutChanged}
            >
              {/* Editor panel */}
              <Panel defaultSize="60" minSize="30" id="editor">
                <div className="h-full flex flex-col bg-dark-800">
                  <div className="px-4 py-2 bg-dark-700 border-b border-gray-600 flex items-center justify-between">
                    <h3 className="text-sm font-medium text-white">Code Editor</h3>
                    <div className="flex items-center justify-between flex-1 ml-4">
                      {/* Group 1: Script management actions */}
                      <div className="flex items-center gap-2">
                        <button
                          onClick={handleNew}
                          className="px-3 py-1 text-sm font-medium text-gray-300 border border-gray-600 rounded-sm hover:bg-gray-700"
                        >
                          New
                        </button>
                        <button
                          onClick={handleSaveClick}
                          className="px-3 py-1 text-sm font-medium text-gray-300 border border-gray-600 rounded-sm hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                          disabled={
                            state.isSaving ||
                            (state.isAdHocMode || !state.selectedTask
                              ? !state.scriptContent.trim()
                              : !state.isDirty)
                          }
                        >
                          {state.isSaving ? 'Saving...' : 'Save'}
                        </button>
                        <button
                          onClick={() => setShowSaveAsModal(true)}
                          className="px-3 py-1 text-sm font-medium text-gray-300 border border-gray-600 rounded-sm hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                          disabled={!state.scriptContent.trim()}
                        >
                          Save As...
                        </button>
                      </div>

                      {/* Group 2: AI actions + Copy + Run (right side) */}
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setShowTaskGenerationModal(true)}
                          className="px-3 py-1 text-sm font-medium text-purple-300 border border-purple-600 rounded-sm hover:bg-purple-900/30 flex items-center gap-1.5 whitespace-nowrap"
                          title="Create or improve tasks with AI"
                        >
                          <SparklesIcon className="h-4 w-4" />
                          AI Task Assistant
                        </button>
                        {aiAssistEnabled && (
                          <button
                            onClick={toggleAiAutocomplete}
                            className={`px-3 py-1 text-sm font-medium border rounded-sm flex items-center gap-1.5 whitespace-nowrap transition-colors ${
                              aiAutocompleteEnabled
                                ? 'text-purple-300 border-purple-700 bg-purple-900/20 hover:bg-purple-900/40'
                                : 'text-gray-500 border-gray-700 hover:bg-dark-700 hover:text-gray-300'
                            }`}
                            title={
                              aiAutocompleteEnabled
                                ? 'AI autocomplete on — click to disable'
                                : 'AI autocomplete off — click to enable'
                            }
                          >
                            <SparklesIcon className="h-4 w-4" />
                            AI Autocomplete
                          </button>
                        )}
                        <button
                          onClick={() => handleCopy(state.scriptContent, 'code')}
                          className="p-1 text-gray-400 hover:text-white"
                          title="Copy code"
                        >
                          {copiedSection === 'code' ? (
                            <CheckIcon className="h-4 w-4 text-green-400" />
                          ) : (
                            <ClipboardDocumentIcon className="h-4 w-4" />
                          )}
                        </button>
                        <button
                          onClick={handleRun}
                          className="px-3 py-1 bg-green-600 text-white text-sm font-medium rounded-sm hover:bg-green-700 focus:ring-2 focus:ring-green-500 focus:ring-offset-2 flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
                          disabled={
                            state.isRunning || (!state.selectedTask && !state.scriptContent.trim())
                          }
                          title="Run script (⌘+Enter / Ctrl+Enter)"
                        >
                          <PlayIcon className="h-4 w-4" />
                          {state.isRunning ? 'Running...' : 'Run'}
                          <kbd className="ml-1 px-1.5 py-0.5 text-[10px] font-mono bg-green-700/50 rounded-sm border border-green-500/30">
                            ⌘↵
                          </kbd>
                        </button>
                      </div>
                    </div>
                  </div>
                  <div className="flex-1 min-h-0">
                    <AceEditor
                      mode="python"
                      theme="terminal"
                      value={state.scriptContent}
                      onChange={handleScriptChange}
                      onLoad={(editor) => {
                        editorRef.current = editor;

                        // Register completers: cyCompleter always, aiCompleter only when AI assist is enabled.
                        if (window.ace) {
                          // eslint-disable-next-line @typescript-eslint/no-unsafe-call, @typescript-eslint/no-unsafe-member-access
                          const langTools = window.ace.require('ace/ext/language_tools') as
                            | AceLangTools
                            | undefined;
                          langTools?.setCompleters(
                            aiAssistEnabled ? [cyCompleter, aiCompleter] : [cyCompleter]
                          );
                        }

                        // Trigger AI inline completion after user pauses typing (only when AI assist enabled).
                        if (aiAssistEnabled) {
                          const aiEnabledRef = { current: aiAutocompleteEnabled };
                          (editor as unknown as AceEditorWithAiRef).__aiEnabledRef = aiEnabledRef;
                          editor.on('change', () => {
                            if ((editor as unknown as AceEditorWithAiRef).__aiEnabledRef?.current) {
                              schedulAiCompletion(editor);
                            }
                          });
                        }

                        // Add Escape key handler to close autocomplete popup
                        // Listen at document level to capture before popup's own handlers
                        const handleEscapeForAutocomplete = (e: KeyboardEvent) => {
                          if (e.key === 'Escape') {
                            const completer = editor.completer;
                            // Check multiple ways if autocomplete is active
                            if (
                              completer &&
                              (completer.activated ||
                                (completer as unknown as { popup?: { isOpen: boolean } }).popup
                                  ?.isOpen)
                            ) {
                              e.preventDefault();
                              e.stopPropagation();
                              e.stopImmediatePropagation();
                              completer.detach();
                            }
                          }
                        };
                        document.addEventListener('keydown', handleEscapeForAutocomplete, true);

                        // Anti password manager attributes
                        const textArea = editor.textInput.getElement();
                        textArea.setAttribute('autocomplete', 'off');
                        textArea.setAttribute('autocorrect', 'off');
                        textArea.setAttribute('autocapitalize', 'off');
                        textArea.setAttribute('spellcheck', 'false');
                        textArea.setAttribute('data-gramm', 'false');
                        textArea.setAttribute('data-gramm_editor', 'false');
                        textArea.setAttribute('data-enable-grammarly', 'false');
                        textArea.setAttribute('data-1p-ignore', 'true');
                        textArea.setAttribute('data-lpignore', 'true');
                        textArea.setAttribute('data-form-type', 'other');
                      }}
                      name="cy-script-editor-modern"
                      width="100%"
                      height="100%"
                      fontSize={14}
                      showPrintMargin={false}
                      showGutter
                      highlightActiveLine
                      setOptions={{
                        enableBasicAutocompletion: true,
                        enableLiveAutocompletion: true,
                        enableInlineAutocompletion: true,
                        enableSnippets: true,
                        showLineNumbers: true,
                        tabSize: 2,
                      }}
                    />
                  </div>
                </div>
              </Panel>

              <Separator className="h-1 bg-gray-700 hover:bg-blue-500 transition-colors cursor-row-resize" />

              {/* Bottom panel (Input/Output) */}
              <Panel
                panelRef={bottomPanelRef}
                defaultSize="40"
                minSize="15"
                maxSize="70"
                collapsible
                collapsedSize="5"
                id="bottom"
              >
                <div className="h-full flex flex-col bg-dark-900">
                  {!layout.isBottomPanelCollapsed ? (
                    <>
                      <div className="px-4 py-2 bg-dark-800 border-b border-gray-700 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <h3 className="text-sm font-medium text-white">Input & Output</h3>
                          {state.fromTaskRunId && (
                            <div
                              className="flex items-center gap-1.5 px-2 py-0.5 text-xs bg-primary/10 border border-primary/20 rounded text-primary"
                              data-testid="task-run-banner"
                            >
                              <span>
                                Viewing Task Run{' '}
                                <span className="font-mono">
                                  {state.fromTaskRunId.slice(0, 8)}...
                                </span>
                              </span>
                              <button
                                onClick={() => {
                                  setState((prev) => ({
                                    ...prev,
                                    fromTaskRunId: null,
                                    selectedExample: '',
                                    output: '',
                                    completedOutput: null,
                                    lastExecutionStatus: null,
                                  }));
                                  onClearTaskRunId?.();
                                }}
                                className="p-0.5 hover:bg-primary/20 rounded"
                                title="Dismiss task run view"
                                data-testid="dismiss-task-run"
                              >
                                <XMarkIcon className="h-3 w-3" />
                              </button>
                            </div>
                          )}
                        </div>
                        <button
                          onClick={toggleBottomPanel}
                          className="p-1 text-gray-400 hover:text-white"
                          title="Collapse panel (Ctrl+J)"
                        >
                          <ChevronDownIcon className="h-4 w-4" />
                        </button>
                      </div>
                      <div className="flex-1 min-h-0">
                        <Group
                          orientation="horizontal"
                          defaultLayout={ioLayout}
                          onLayoutChanged={onIoLayoutChanged}
                        >
                          {/* Input panel */}
                          <Panel defaultSize="50" minSize="20" id="input">
                            <div className="h-full flex flex-col bg-dark-800 border-r border-gray-700">
                              <div className="px-4 py-2 bg-dark-700 border-b border-gray-600 flex items-center justify-between h-[48px]">
                                <h3 className="text-sm font-medium text-white">Input</h3>
                                <button
                                  onClick={() => handleCopy(state.input, 'input')}
                                  className="p-1 text-gray-400 hover:text-white"
                                  title="Copy input"
                                >
                                  {copiedSection === 'input' ? (
                                    <CheckIcon className="h-4 w-4 text-green-400" />
                                  ) : (
                                    <ClipboardDocumentIcon className="h-4 w-4" />
                                  )}
                                </button>
                              </div>
                              <div className="flex-1 flex flex-col p-4 min-h-0 gap-3">
                                {state.selectedTask?.data_samples &&
                                state.selectedTask.data_samples.length > 0 ? (
                                  <div className="shrink-0">
                                    <label
                                      htmlFor="workbench-example-select"
                                      className="block text-xs font-medium text-gray-300 mb-1"
                                    >
                                      Examples:
                                    </label>
                                    <select
                                      id="workbench-example-select"
                                      value={state.selectedExample}
                                      onChange={(e) => handleExampleChange(e.target.value)}
                                      className="w-full text-xs px-2 py-1 border border-gray-600 rounded-sm bg-dark-700 text-gray-100"
                                    >
                                      <option value="">Select an example...</option>
                                      {state.fromTaskRunId && (
                                        <option value="task-run">From Task Run (Current)</option>
                                      )}
                                      {state.selectedTask.data_samples.map((sample, index) => (
                                        <option key={index} value={index}>
                                          {(sample as DataSample)?.name || `Example ${index + 1}`}
                                          {(sample as DataSample)?.description &&
                                            ` - ${(sample as DataSample).description}`}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                ) : null}
                                <textarea
                                  value={state.input}
                                  onChange={(e) => {
                                    setState((prev) => {
                                      if (prev.fromTaskRunId) onClearTaskRunId?.();
                                      return {
                                        ...prev,
                                        input: e.target.value,
                                        selectedExample: '',
                                        fromTaskRunId: null,
                                      };
                                    });
                                  }}
                                  placeholder="Enter input data (JSON, text, etc.)"
                                  className="flex-1 resize-none border border-gray-600 rounded-md p-2 text-sm bg-dark-700 text-gray-100 placeholder-gray-500 focus:ring-2 focus:ring-primary focus:border-transparent"
                                />
                              </div>
                            </div>
                          </Panel>

                          <Separator className="w-1 bg-gray-700 hover:bg-blue-500 transition-colors cursor-col-resize" />

                          {/* Output panel */}
                          <Panel defaultSize="50" minSize="20" id="output">
                            <div className="h-full flex flex-col bg-dark-800">
                              <div className="px-4 py-2 bg-dark-700 border-b border-gray-600 flex items-center justify-between h-[48px]">
                                <h3 className="text-sm font-medium text-white">Output</h3>
                              </div>
                              <div className="flex-1 p-4 min-h-0 flex flex-col gap-3">
                                {/* Progress bar */}
                                {state.showProgress && (
                                  <ProgressBar
                                    elapsedTime={state.elapsedTime}
                                    estimatedTime={state.isAdHocMode ? null : state.estimatedTime}
                                    isRunning={state.isRunning || state.showProgress}
                                    isCompleted={!state.isRunning && state.showProgress}
                                  />
                                )}
                                {/* Output tab bar */}
                                {state.logEntries.length > 0 && (
                                  <div className="flex items-center gap-1 px-2 py-1 border-b border-gray-700/50">
                                    <button
                                      onClick={() =>
                                        setState((prev) => ({ ...prev, outputTab: 'result' }))
                                      }
                                      className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                                        state.outputTab === 'result'
                                          ? 'bg-gray-700 text-gray-100'
                                          : 'text-gray-400 hover:text-gray-200'
                                      }`}
                                    >
                                      Result
                                    </button>
                                    <button
                                      onClick={() =>
                                        setState((prev) => ({ ...prev, outputTab: 'logs' }))
                                      }
                                      className={`px-2.5 py-1 text-xs font-medium rounded transition-colors flex items-center gap-1.5 ${
                                        state.outputTab === 'logs'
                                          ? 'bg-gray-700 text-gray-100'
                                          : 'text-gray-400 hover:text-gray-200'
                                      }`}
                                    >
                                      Logs
                                      <span className="text-[10px] bg-gray-600 text-gray-300 rounded-full px-1.5 min-w-[18px] text-center">
                                        {state.logEntries.length}
                                      </span>
                                    </button>
                                  </div>
                                )}
                                {/* Output / Logs renderer */}
                                <div className="flex-1 min-h-0">
                                  {state.outputTab === 'logs' && state.logEntries.length > 0 ? (
                                    <div className="w-full h-full overflow-y-auto px-3 py-2">
                                      <div className="font-mono text-xs text-gray-300 space-y-0.5">
                                        {state.logEntries.map((entry, i) => {
                                          const msg =
                                            typeof entry === 'string' ? entry : entry.message;
                                          const ts =
                                            typeof entry === 'object' && entry.ts
                                              ? new Date(entry.ts * 1000)
                                                  .toISOString()
                                                  .slice(11, 23)
                                              : null;
                                          return (
                                            <div
                                              key={i}
                                              className="flex gap-3 leading-relaxed hover:bg-gray-800/50 rounded px-1"
                                            >
                                              <span className="text-gray-600 select-none w-6 text-right flex-shrink-0">
                                                {i + 1}
                                              </span>
                                              {ts && (
                                                <span className="text-gray-600 select-none flex-shrink-0">
                                                  {ts}
                                                </span>
                                              )}
                                              <span className="break-all">{msg}</span>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  ) : (
                                    <OutputRenderer
                                      output={state.completedOutput || state.output}
                                      onCopy={() =>
                                        handleCopy(state.completedOutput || state.output, 'output')
                                      }
                                      isCopied={copiedSection === 'output'}
                                      isError={
                                        state.lastExecutionStatus === 'failed' ||
                                        state.lastExecutionStatus === 'error'
                                      }
                                      inputData={state.input}
                                      executionStatus={state.lastExecutionStatus ?? undefined}
                                    />
                                  )}
                                </div>
                              </div>
                            </div>
                          </Panel>
                        </Group>
                      </div>
                    </>
                  ) : (
                    <div className="h-full flex items-center justify-center gap-2 bg-dark-800">
                      <button
                        onClick={toggleBottomPanel}
                        className="flex items-center gap-2 px-3 py-1 text-sm text-gray-400 hover:text-white hover:bg-dark-700 rounded-sm"
                        title="Expand panel (Ctrl+J)"
                      >
                        <ChevronUpIcon className="h-4 w-4" />
                        <span>Input & Output</span>
                      </button>
                    </div>
                  )}
                </div>
              </Panel>
            </Group>
          </Panel>
        </Group>
      </div>

      {/* Error display */}
      {error && error.hasError && (
        <div className="p-4 bg-red-900/20 border-t border-red-800">
          <p className="text-sm text-red-400">{error.message}</p>
        </div>
      )}

      {/* Draft restore confirmation dialog */}
      <ConfirmDialog
        isOpen={pendingDraftRestore !== null}
        onClose={handleDiscardDraft}
        onConfirm={handleRestoreDraft}
        title="Restore Unsaved Draft?"
        message={
          pendingDraftRestore
            ? `Found an unsaved draft from ${new Date(pendingDraftRestore.draft.timestamp).toLocaleString()}. Would you like to restore your previous work or use the saved version?`
            : ''
        }
        confirmLabel="Restore Draft"
        cancelLabel="Use Saved"
        variant="question"
      />

      {/* Unsaved changes dialog for New button */}
      <UnsavedChangesDialog
        isOpen={showUnsavedChangesDialog}
        onClose={() => setShowUnsavedChangesDialog(false)}
        onSave={() => void handleSaveAndNew()}
        onSaveAs={handleSaveAsAndNew}
        onDiscard={handleDiscardAndNew}
        taskName={state.selectedTask?.name}
        canSave={!state.isAdHocMode && !!state.selectedTask}
      />

      {/* Unsaved changes dialog for navigation away (sidebar links, back button, etc.) */}
      <UnsavedChangesDialog
        isOpen={showNavBlockerDialog}
        onClose={handleNavCancel}
        onSave={() => void handleNavSave()}
        onSaveAs={handleNavSaveAs}
        onDiscard={handleNavDiscard}
        taskName={state.selectedTask?.name}
        canSave={!state.isAdHocMode && !!state.selectedTask}
      />

      {/* Unsaved changes dialog for keyboard reload (Cmd+R / F5) */}
      <UnsavedChangesDialog
        isOpen={showReloadDialog}
        onClose={handleReloadCancel}
        onSave={() => void handleReloadSave()}
        onSaveAs={handleReloadSaveAs}
        onDiscard={handleReloadDiscard}
        taskName={state.selectedTask?.name}
        canSave={!state.isAdHocMode && !!state.selectedTask}
      />

      {/* Run unsaved changes dialog */}
      <RunUnsavedChangesDialog
        isOpen={showRunUnsavedDialog}
        onClose={() => setShowRunUnsavedDialog(false)}
        onSaveAndRun={() => void handleSaveAndRun()}
        onSaveAsAndRun={handleSaveAsAndRun}
        taskName={state.selectedTask?.name}
      />

      {/* Save As modal */}
      <SaveAsTaskModal
        isOpen={showSaveAsModal}
        onClose={() => {
          setShowSaveAsModal(false);
          // If the user closes Save As without saving while a nav was pending, reset the blocker
          if (pendingNavAfterSave) {
            setPendingNavAfterSave(false);
            blockerRef.current.reset?.();
          }
          // If the user closes Save As without saving while a reload was pending, cancel it
          if (pendingReloadAfterSave) {
            setPendingReloadAfterSave(false);
          }
        }}
        onSave={handleSaveAsSuccess}
        initialScript={state.scriptContent}
        initialName={state.selectedTask ? generateVersionedName(state.selectedTask.name) : ''}
        initialDescription={state.selectedTask?.description || ''}
      />

      {/* AI Task Generation modal */}
      <TaskGenerationModal
        isOpen={showTaskGenerationModal}
        onClose={() => setShowTaskGenerationModal(false)}
        onComplete={handleTaskGenerationComplete}
        taskId={state.selectedTask?.id}
        taskName={state.selectedTask?.name}
      />
    </div>
  );
};

export default WorkbenchModern;
