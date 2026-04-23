/* eslint-disable @typescript-eslint/await-thenable, no-undef */
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { AlertAnalysis } from '../../../types/alert';
import { AnalysisDetailsTab } from '../AnalysisDetailsTab';

// Mock dependencies
vi.mock('../../../store/timezoneStore', () => ({
  useTimezoneStore: () => ({
    timezone: 'UTC',
  }),
}));

// Mock useUrlState to return first analysis ID when analyses exist
let mockUrlStateValue = '';
const mockSetUrlState = vi.fn((newValue: string) => {
  mockUrlStateValue = newValue;
});
vi.mock('../../../hooks/useUrlState', () => ({
  useUrlState: (_key: string, defaultValue: string) => {
    // Return the mock value or default
    return [mockUrlStateValue || defaultValue, mockSetUrlState];
  },
}));

vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: null,
    clearError: vi.fn(),
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: vi.fn().mockImplementation(() => {
      return Promise.resolve([null, undefined]);
    }),
  }),
}));

vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getWorkflow: vi.fn().mockResolvedValue(null),
    getWorkflowRun: vi.fn().mockResolvedValue(null),
    getTaskRuns: vi.fn().mockResolvedValue({ task_runs: [] }),
  },
}));

vi.mock('../../workflows/WorkflowExecutionReaflow', () => ({
  default: () => <div data-testid="workflow-execution">Workflow Execution</div>,
}));

vi.mock('../../common/TaskRunList', () => ({
  TaskRunList: ({ taskRuns }: { taskRuns?: unknown[] }) => (
    <div data-testid="task-run-list">{taskRuns?.length ?? 0} task runs</div>
  ),
}));

const mockAnalyses: AlertAnalysis[] = [
  {
    id: 'analysis-1',
    alert_id: 'alert-123',
    tenant_id: 'tenant-1',
    status: 'completed',
    started_at: '2025-01-15T10:00:00Z',
    completed_at: '2025-01-15T10:05:00Z',
    created_at: '2025-01-15T10:00:00Z',
    updated_at: '2025-01-15T10:05:00Z',
    steps_progress: {},
    workflow_run_id: 'workflow-run-1',
  },
  {
    id: 'analysis-2',
    alert_id: 'alert-123',
    tenant_id: 'tenant-1',
    status: 'failed',
    started_at: '2025-01-14T10:00:00Z',
    created_at: '2025-01-14T10:00:00Z',
    updated_at: '2025-01-14T10:05:00Z',
    steps_progress: {},
    error_message: 'Analysis failed due to timeout',
  },
];

const renderWithRouter = (component: React.ReactElement) => {
  return render(<MemoryRouter>{component}</MemoryRouter>);
};

// Tests skipped due to memory issues with vitest worker when loading heavy dependencies
// The component is tested via AlertDetails.test.tsx integration tests
describe.skip('AnalysisDetailsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUrlStateValue = '';
  });

  it('should render empty state when no analyses', () => {
    renderWithRouter(
      <AnalysisDetailsTab alertId="alert-123" alertAnalyses={[]} onAnalyze={vi.fn()} />
    );

    expect(screen.getByText('No Analysis Runs')).toBeInTheDocument();
    expect(screen.getByText('This alert has not been analyzed yet.')).toBeInTheDocument();
  });

  it('should show Start Analysis button when no analyses', () => {
    const onAnalyze = vi.fn();
    renderWithRouter(
      <AnalysisDetailsTab alertId="alert-123" alertAnalyses={[]} onAnalyze={onAnalyze} />
    );

    const button = screen.getByText('Start Analysis');
    expect(button).toBeInTheDocument();
  });

  it('should render with analyses and show selector', async () => {
    // Pre-set the selected analysis ID (simulating auto-select)
    mockUrlStateValue = 'analysis-1';

    await act(() => {
      renderWithRouter(
        <AnalysisDetailsTab alertId="alert-123" alertAnalyses={mockAnalyses} onAnalyze={vi.fn()} />
      );
    });

    // Should show the analysis run selector
    expect(screen.getByText('Analysis Run')).toBeInTheDocument();
    expect(screen.getByText(/Latest/)).toBeInTheDocument();
  });

  it('should show workflow execution section', async () => {
    mockUrlStateValue = 'analysis-1';

    await act(() => {
      renderWithRouter(
        <AnalysisDetailsTab alertId="alert-123" alertAnalyses={mockAnalyses} onAnalyze={vi.fn()} />
      );
    });

    expect(screen.getByText('Workflow Execution')).toBeInTheDocument();
  });

  it('should show task runs section', async () => {
    mockUrlStateValue = 'analysis-1';

    await act(() => {
      renderWithRouter(
        <AnalysisDetailsTab alertId="alert-123" alertAnalyses={mockAnalyses} onAnalyze={vi.fn()} />
      );
    });

    expect(screen.getByText('Task Runs')).toBeInTheDocument();
  });

  it('should show error message for failed analysis', async () => {
    const failedAnalysis: AlertAnalysis[] = [
      {
        id: 'analysis-failed',
        alert_id: 'alert-123',
        tenant_id: 'tenant-1',
        status: 'failed',
        started_at: '2025-01-15T10:00:00Z',
        created_at: '2025-01-15T10:00:00Z',
        updated_at: '2025-01-15T10:05:00Z',
        steps_progress: {},
        error_message: 'Analysis failed due to network timeout',
      },
    ];

    mockUrlStateValue = 'analysis-failed';

    await act(() => {
      renderWithRouter(
        <AnalysisDetailsTab
          alertId="alert-123"
          alertAnalyses={failedAnalysis}
          onAnalyze={vi.fn()}
        />
      );
    });

    expect(screen.getByText('Analysis failed due to network timeout')).toBeInTheDocument();
  });
});
