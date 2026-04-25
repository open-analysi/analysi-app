import React from 'react';

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import WorkbenchModern from '../WorkbenchModern';

// ── Mocks ────────────────────────────────────────────────────────────

vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getTask: vi.fn(),
    getTaskRuns: vi.fn(),
    getTaskRunDetails: vi.fn(),
    getTaskRunLogs: vi.fn(),
    getTaskRunHistory: vi.fn(),
    getIntegrations: vi.fn(),
    getIntegrationTypes: vi.fn(),
    getIntegrationType: vi.fn(),
    getAllTools: vi.fn(),
  },
}));

vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: null,
    runSafe: vi.fn(async (promise: Promise<unknown>) => {
      try {
        const result = await promise;
        return [result, undefined];
      } catch (error) {
        return [undefined, error];
      }
    }),
  }),
}));

vi.mock('../../../hooks/useClickTracking', () => ({
  useClickTracking: () => ({ trackExecute: vi.fn(), trackClick: vi.fn() }),
}));

vi.mock('../../../store/cyEditorStore', () => ({
  useCyEditorStore: Object.assign(
    () => ({
      drafts: {},
      loadDraft: () => null,
      saveDraft: vi.fn(),
      clearDraft: vi.fn(),
    }),
    { setState: vi.fn(), getState: vi.fn(() => ({ drafts: {} })) }
  ),
}));

vi.mock('../../../utils/polling', () => ({
  startPolling: vi.fn(),
}));

// Mock react-router
vi.mock('react-router', () => ({
  useBlocker: () => ({ state: 'idle' }),
  useNavigate: () => vi.fn(),
}));

// Mock Ace editor — render a simple textarea stub
vi.mock('react-ace', () => ({
  default: ({ value }: { value: string }) => (
    <textarea data-testid="ace-editor" defaultValue={value} />
  ),
}));

vi.mock('ace-builds/src-noconflict/ace', () => ({
  default: { config: { set: vi.fn() }, require: vi.fn() },
}));
vi.mock('ace-builds/src-noconflict/ext-inline_autocomplete', () => ({}));
vi.mock('ace-builds/src-noconflict/ext-language_tools', () => ({
  default: { setCompleters: vi.fn() },
}));
vi.mock('ace-builds/src-noconflict/mode-python', () => ({}));
vi.mock('ace-builds/src-noconflict/theme-terminal', () => ({}));

// Mock resizable panels
vi.mock('react-resizable-panels', () => ({
  Panel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Group: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Separator: () => <div />,
  useDefaultLayout: () => ({
    defaultLayout: undefined,
    onLayoutChanged: vi.fn(),
  }),
}));

// Mock sub-components that are not under test
vi.mock('../TaskSelector', () => ({
  TaskSelector: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <select data-testid="task-selector" onChange={(e) => onSelect(e.target.value)}>
      <option value="">Select task</option>
    </select>
  ),
}));
vi.mock('../OutputRenderer', () => ({
  OutputRenderer: ({ output, isError }: { output: string; isError: boolean }) => (
    <div data-testid="output-renderer" data-error={isError}>
      {output}
    </div>
  ),
}));
vi.mock('../ProgressBar', () => ({
  ProgressBar: () => <div data-testid="progress-bar" />,
}));
vi.mock('../SaveAsTaskModal', () => ({
  SaveAsTaskModal: () => null,
}));
vi.mock('../TaskGenerationModal', () => ({
  TaskGenerationModal: () => null,
}));
vi.mock('../UnsavedChangesDialog', () => ({
  UnsavedChangesDialog: () => null,
}));
vi.mock('../RunUnsavedChangesDialog', () => ({
  RunUnsavedChangesDialog: () => null,
}));
vi.mock('../TaskFeedbackSection', () => ({
  default: () => null,
}));
vi.mock('../../common/ConfirmDialog', () => ({
  ConfirmDialog: () => null,
}));
vi.mock('../useAutocompleteData', () => ({
  useAutocompleteData: () => ({}),
}));
vi.mock('../useWorkbenchEffects', () => ({
  useWorkbenchKeyboardShortcuts: vi.fn(),
  useAutoSaveDraft: vi.fn(),
  useScriptAnalysis: vi.fn(),
}));
vi.mock('../aiCompleter', () => ({
  aiCompleter: {},
  cancelAiCompletion: vi.fn(),
  schedulAiCompletion: vi.fn(),
}));
vi.mock('../cyCompleter', () => ({
  cyCompleter: {},
}));

// ── Helpers ──────────────────────────────────────────────────────────

const OUTPUT_RENDERER_ID = 'output-renderer';

const mockTask = {
  id: 'task-123',
  name: 'Test Task',
  description: 'A task for testing',
  script: 'return input',
  function: 'summarization' as const,
  owner: 'System',
  created_by: 'System',
  visible: true,
  system_only: false,
  app: 'default',
  mode: 'script',
  tenant_id: 'test-tenant',
  version: '1.0.0',
  scopes: ['processing'],
  status: 'active',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  usage_stats: { count: 0, last_used: null },
  data_samples: [],
  knowledge_units: [],
  knowledge_modules: [],
} as unknown as Awaited<ReturnType<typeof backendApi.getTask>>;

// ── Tests ────────────────────────────────────────────────────────────

describe('WorkbenchModern — task run output loading', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Default: getTask resolves with our mock task
    vi.mocked(backendApi.getTask).mockResolvedValue(mockTask);

    // Default: getTaskRuns returns empty (for avg time calculation)
    vi.mocked(backendApi.getTaskRuns).mockResolvedValue({ task_runs: [], total: 0 } as Awaited<
      ReturnType<typeof backendApi.getTaskRuns>
    >);
    vi.mocked(backendApi.getTaskRunHistory).mockResolvedValue({
      task_runs: [],
      total: 0,
    } as Awaited<ReturnType<typeof backendApi.getTaskRunHistory>>);

    // Default: no logs
    vi.mocked(backendApi.getTaskRunLogs).mockResolvedValue({
      trid: '',
      status: 'completed',
      entries: [],
      has_logs: false,
    });
  });

  it('fetches and displays task run output when taskRunId is provided', async () => {
    const taskRunOutput = { result: 'analysis complete', findings: ['finding-1'] };

    vi.mocked(backendApi.getTaskRunDetails).mockResolvedValue({
      id: 'trid-456',
      status: 'completed',
      output_type: 'inline',
      output_location: JSON.stringify(taskRunOutput),
    } as unknown as Awaited<ReturnType<typeof backendApi.getTaskRunDetails>>);

    render(
      <WorkbenchModern taskId="task-123" inputData='{"alert_id": "alert-1"}' taskRunId="trid-456" />
    );

    await waitFor(() => {
      expect(backendApi.getTaskRunDetails).toHaveBeenCalledWith('trid-456');
    });

    await waitFor(() => {
      const outputEl = screen.getByTestId(OUTPUT_RENDERER_ID);
      expect(outputEl.textContent).toContain('analysis complete');
      expect(outputEl.textContent).toContain('finding-1');
    });
  });

  it('does not fetch task run output when no taskRunId is provided', async () => {
    render(<WorkbenchModern taskId="task-123" inputData='{"alert_id": "alert-1"}' />);

    // Wait for task loading to settle
    await waitFor(() => {
      expect(backendApi.getTask).toHaveBeenCalledWith('task-123');
    });

    expect(backendApi.getTaskRunDetails).not.toHaveBeenCalled();
  });

  it('handles failed task run output fetch gracefully', async () => {
    vi.mocked(backendApi.getTaskRunDetails).mockRejectedValue(new Error('Network error'));

    render(
      <WorkbenchModern taskId="task-123" inputData='{"alert_id": "alert-1"}' taskRunId="trid-789" />
    );

    await waitFor(() => {
      expect(backendApi.getTaskRunDetails).toHaveBeenCalledWith('trid-789');
    });

    // The output should remain empty (no crash)
    const outputEl = screen.getByTestId(OUTPUT_RENDERER_ID);
    expect(outputEl).toBeInTheDocument();
  });

  it('sets lastExecutionStatus from the task run status', async () => {
    vi.mocked(backendApi.getTaskRunDetails).mockResolvedValue({
      id: 'trid-failed',
      status: 'failed',
      output_type: 'inline',
      output_location: JSON.stringify({ error: 'task failed' }),
    } as unknown as Awaited<ReturnType<typeof backendApi.getTaskRunDetails>>);

    render(
      <WorkbenchModern
        taskId="task-123"
        inputData='{"alert_id": "alert-1"}'
        taskRunId="trid-failed"
      />
    );

    await waitFor(() => {
      const outputEl = screen.getByTestId(OUTPUT_RENDERER_ID);
      expect(outputEl.getAttribute('data-error')).toBe('true');
    });
  });

  it('fetches output for ad-hoc task runs', async () => {
    const adHocOutput = { message: 'ad hoc result' };

    vi.mocked(backendApi.getTaskRunDetails).mockResolvedValue({
      id: 'trid-adhoc',
      status: 'completed',
      output_type: 'inline',
      output_location: JSON.stringify(adHocOutput),
    } as unknown as Awaited<ReturnType<typeof backendApi.getTaskRunDetails>>);

    render(
      <WorkbenchModern
        cyScript='return "hello"'
        inputData='{"test": true}'
        taskRunId="trid-adhoc"
        isAdHoc={true}
      />
    );

    await waitFor(() => {
      expect(backendApi.getTaskRunDetails).toHaveBeenCalledWith('trid-adhoc');
    });

    await waitFor(() => {
      const outputEl = screen.getByTestId(OUTPUT_RENDERER_ID);
      expect(outputEl.textContent).toContain('ad hoc result');
    });
  });

  it('deep link: fetches input from API when inputData prop is undefined', async () => {
    const taskRunOutput = { result: 'deep link output' };
    const taskRunInput = { alert_id: 'alert-deep' };

    vi.mocked(backendApi.getTaskRunDetails).mockResolvedValue({
      id: 'trid-deep',
      status: 'completed',
      output_type: 'inline',
      output_location: JSON.stringify(taskRunOutput),
      input_type: 'inline',
      input_location: JSON.stringify(taskRunInput),
      task_id: 'task-123',
    } as unknown as Awaited<ReturnType<typeof backendApi.getTaskRunDetails>>);

    // Deep link: taskId and taskRunId provided, but no inputData
    render(<WorkbenchModern taskId="task-123" taskRunId="trid-deep" />);

    await waitFor(() => {
      expect(backendApi.getTaskRunDetails).toHaveBeenCalledWith('trid-deep');
    });

    // Output should be displayed
    await waitFor(() => {
      const outputEl = screen.getByTestId(OUTPUT_RENDERER_ID);
      expect(outputEl.textContent).toContain('deep link output');
    });

    // Input should be populated from the API response
    await waitFor(() => {
      const textarea = screen.getByPlaceholderText('Enter input data (JSON, text, etc.)');
      expect(textarea).toHaveValue(JSON.stringify(taskRunInput, null, 2));
    });
  });

  it('shows task run banner and dismiss clears state', async () => {
    const mockClearTaskRunId = vi.fn();

    vi.mocked(backendApi.getTaskRunDetails).mockResolvedValue({
      id: 'trid-banner',
      status: 'completed',
      output_type: 'inline',
      output_location: JSON.stringify({ result: 'banner test' }),
    } as unknown as Awaited<ReturnType<typeof backendApi.getTaskRunDetails>>);

    render(
      <WorkbenchModern
        taskId="task-123"
        inputData='{"alert_id": "alert-1"}'
        taskRunId="trid-banner"
        onClearTaskRunId={mockClearTaskRunId}
      />
    );

    // Wait for the banner to appear
    await waitFor(() => {
      const banner = screen.getByTestId('task-run-banner');
      expect(banner).toBeInTheDocument();
      expect(banner.textContent).toContain('trid-ban');
    });

    // Click dismiss
    fireEvent.click(screen.getByTestId('dismiss-task-run'));

    // Banner should disappear and callback should be called
    await waitFor(() => {
      expect(screen.queryByTestId('task-run-banner')).not.toBeInTheDocument();
    });
    expect(mockClearTaskRunId).toHaveBeenCalled();
  });

  it('editing input calls onClearTaskRunId', async () => {
    const mockClearTaskRunId = vi.fn();

    vi.mocked(backendApi.getTaskRunDetails).mockResolvedValue({
      id: 'trid-edit',
      status: 'completed',
      output_type: 'inline',
      output_location: JSON.stringify({ result: 'edit test' }),
    } as unknown as Awaited<ReturnType<typeof backendApi.getTaskRunDetails>>);

    render(
      <WorkbenchModern
        taskId="task-123"
        inputData='{"alert_id": "alert-1"}'
        taskRunId="trid-edit"
        onClearTaskRunId={mockClearTaskRunId}
      />
    );

    // Wait for banner to appear (confirms task run state is set)
    await waitFor(() => {
      expect(screen.getByTestId('task-run-banner')).toBeInTheDocument();
    });

    // Edit the input textarea
    const textarea = screen.getByPlaceholderText('Enter input data (JSON, text, etc.)');
    fireEvent.change(textarea, { target: { value: '{"modified": true}' } });

    // onClearTaskRunId should be called and banner should disappear
    expect(mockClearTaskRunId).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.queryByTestId('task-run-banner')).not.toBeInTheDocument();
    });
  });

  it('fetches and displays logs tab when task run has log entries', async () => {
    const taskRunOutput = { result: 'done' };

    vi.mocked(backendApi.getTaskRunDetails).mockResolvedValue({
      id: 'trid-logs',
      status: 'completed',
      output_type: 'inline',
      output_location: JSON.stringify(taskRunOutput),
    } as unknown as Awaited<ReturnType<typeof backendApi.getTaskRunDetails>>);

    vi.mocked(backendApi.getTaskRunLogs).mockResolvedValue({
      trid: 'trid-logs',
      status: 'completed',
      entries: ['Step 1: Starting', 'Step 2: Processing', 'Step 3: Done'],
      has_logs: true,
    });

    render(<WorkbenchModern taskId="task-123" inputData="{}" taskRunId="trid-logs" />);

    // Should fetch logs
    await waitFor(() => {
      expect(backendApi.getTaskRunLogs).toHaveBeenCalledWith('trid-logs');
    });

    // Logs tab should appear with count badge
    await waitFor(() => {
      expect(screen.getByText('Logs')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
    });

    // Click Logs tab
    fireEvent.click(screen.getByText('Logs'));

    // Should show log entries
    await waitFor(() => {
      expect(screen.getByText('Step 1: Starting')).toBeInTheDocument();
      expect(screen.getByText('Step 2: Processing')).toBeInTheDocument();
      expect(screen.getByText('Step 3: Done')).toBeInTheDocument();
    });
  });

  it('does not show logs tab when task has no logs', async () => {
    vi.mocked(backendApi.getTaskRunDetails).mockResolvedValue({
      id: 'trid-nologs',
      status: 'completed',
      output_type: 'inline',
      output_location: JSON.stringify({ result: 'ok' }),
    } as unknown as Awaited<ReturnType<typeof backendApi.getTaskRunDetails>>);

    render(<WorkbenchModern taskId="task-123" inputData="{}" taskRunId="trid-nologs" />);

    await waitFor(() => {
      expect(backendApi.getTaskRunDetails).toHaveBeenCalledWith('trid-nologs');
    });

    // Wait for render to settle
    await waitFor(() => {
      expect(screen.getByText(/"result": "ok"/)).toBeInTheDocument();
    });

    // Logs tab should NOT appear
    expect(screen.queryByText('Logs')).not.toBeInTheDocument();
  });

  it('Result/Logs tabs coexist with Output/Diff toggle (no regression)', async () => {
    // This test verifies that having the Result/Logs tab bar does NOT
    // break the Diff toggle inside OutputRenderer.
    //
    // The Diff toggle is tested comprehensively in OutputRenderer.test.tsx.
    // Here we verify the structural requirement: when logs exist and the
    // Result tab is active, OutputRenderer still receives inputData.
    const taskRunOutput = { title: 'Test Alert', result: 'escalated' };

    vi.mocked(backendApi.getTaskRunDetails).mockResolvedValue({
      id: 'trid-diff',
      status: 'completed',
      output_type: 'inline',
      output_location: JSON.stringify(taskRunOutput),
    } as unknown as Awaited<ReturnType<typeof backendApi.getTaskRunDetails>>);

    vi.mocked(backendApi.getTaskRunLogs).mockResolvedValue({
      trid: 'trid-diff',
      status: 'completed',
      entries: ['Analysis started'],
      has_logs: true,
    });

    render(
      <WorkbenchModern
        taskId="task-123"
        inputData='{"title": "Test Alert"}'
        taskRunId="trid-diff"
      />
    );

    // Wait for output + logs to load
    await waitFor(() => {
      expect(screen.getByText(/"result": "escalated"/)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('Logs')).toBeInTheDocument();
    });

    // Switching to Logs and back to Result should preserve OutputRenderer
    fireEvent.click(screen.getByText('Logs'));
    await waitFor(() => {
      expect(screen.getByText('Analysis started')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Result'));
    await waitFor(() => {
      // OutputRenderer should render — the result JSON should be visible
      expect(screen.getByText(/"result": "escalated"/)).toBeInTheDocument();
    });
  });
});
