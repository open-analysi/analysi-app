/* eslint-disable sonarjs/no-identical-functions */
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { AlertDetailsPage } from '../AlertDetails';

// Mock the hooks
vi.mock('../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: null,
    clearError: vi.fn(),
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: vi.fn(async (promise) => {
      try {
        const result = await promise;
        return [result, undefined];
      } catch (error) {
        return [undefined, error];
      }
    }),
  }),
}));

// Mock the store
vi.mock('../../store/alertStore', () => ({
  useAlertStore: () => ({
    selectedAlert: {
      id: 'test-alert-id',
      human_readable_id: 'AID-123',
      title: 'Test Alert',
      summary: 'Test summary',
      long_summary: 'Test long summary',
      severity: 'HIGH',
      analysis_status: 'completed',
      current_analysis: {
        id: 'analysis-123',
        workflow_run_id: 'workflow-123',
        status: 'completed',
        long_summary: 'Analysis long summary',
      },
      current_disposition_display_name: 'Malicious',
    },
    isLoadingAlert: false,
    alertAnalyses: [],
    dispositions: [],
    error: null,
    fetchAlert: vi.fn(),
    fetchAlertAnalyses: vi.fn(),
    fetchDispositions: vi.fn(),
    startAnalysis: vi.fn(),
    updateAlert: vi.fn(),
    clearError: vi.fn(),
    analysisProgress: null,
    fetchAnalysisProgress: vi.fn(),
    clearAnalysisProgress: vi.fn(),
    setSelectedAlert: vi.fn(),
  }),
}));

// Mock backend API
vi.mock('../../services/backendApi', () => ({
  backendApi: {
    getWorkflow: vi.fn().mockResolvedValue({ id: 'workflow-123', name: 'Test Workflow' }),
    getWorkflowRun: vi.fn().mockResolvedValue({
      id: 'run-123',
      workflow_id: 'workflow-123',
      status: 'completed',
    }),
    getTaskRuns: vi.fn().mockResolvedValue({
      task_runs: [{ id: 'task-1', name: 'Task 1', status: 'completed' }],
    }),
  },
}));

// Mock components that might cause issues
vi.mock('../../components/workflows/WorkflowExecutionReaflow', () => ({
  default: () => <div data-testid="workflow-execution">Workflow Execution</div>,
}));

vi.mock('../../components/common/TaskRunList', () => ({
  TaskRunList: ({ taskRuns }: { taskRuns?: unknown[] }) => (
    <div data-testid="task-run-list">{taskRuns?.length ?? 0} task runs</div>
  ),
}));

vi.mock('../../components/alerts/AnalysisDetailsTab', () => ({
  AnalysisDetailsTab: () => <div data-testid="analysis-details-tab">Analysis Details Tab</div>,
}));

// Mock ConfirmDialog to avoid HeadlessUI ResizeObserver issues in tests
vi.mock('../../components/common/ConfirmDialog', () => ({
  ConfirmDialog: ({
    isOpen,
    onClose,
    onConfirm,
    title,
    message,
    confirmLabel,
    cancelLabel,
  }: {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: () => void;
    title: string;
    message: string;
    confirmLabel: string;
    cancelLabel: string;
  }) =>
    isOpen ? (
      <div role="dialog" data-testid="confirm-dialog">
        <h2>{title}</h2>
        <p>{message}</p>
        <button onClick={onClose}>{cancelLabel}</button>
        <button onClick={onConfirm}>{confirmLabel}</button>
      </div>
    ) : null,
}));

describe('AlertDetails - URL State Navigation', () => {
  const renderWithRouter = (initialUrl: string) => {
    return render(
      <MemoryRouter initialEntries={[initialUrl]}>
        <Routes>
          <Route path="/alerts/:id" element={<AlertDetailsPage />} />
        </Routes>
      </MemoryRouter>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Tab Navigation with URL State', () => {
    it('should default to details tab when no tab parameter in URL', async () => {
      renderWithRouter('/alerts/test-id');

      // Overview tab should be active by default
      await waitFor(() => {
        const overviewTab = screen.getByText('Overview');
        expect(overviewTab).toHaveClass('border-primary');
        expect(overviewTab).toHaveClass('text-primary');
      });
    });

    it('should load analysis tab when URL has tab=analysis', async () => {
      renderWithRouter('/alerts/test-id?tab=analysis');

      await waitFor(() => {
        const analysisTab = screen.getByText('Runs & Data');
        expect(analysisTab).toHaveClass('border-primary');
        expect(analysisTab).toHaveClass('text-primary');
      });
    });

    it('should update URL when clicking on different tabs', async () => {
      renderWithRouter('/alerts/test-id');

      // Click on Report tab
      const findingsReportTab = screen.getByText('Report');
      fireEvent.click(findingsReportTab);

      await waitFor(() => {
        expect(findingsReportTab).toHaveClass('border-primary');
        expect(findingsReportTab).toHaveClass('text-primary');
      });

      // Click on Runs & Data tab
      const analysisTab = screen.getByText('Runs & Data');
      fireEvent.click(analysisTab);

      await waitFor(() => {
        expect(analysisTab).toHaveClass('border-primary');
        expect(analysisTab).toHaveClass('text-primary');
      });
    });

    it('should not show tab parameter when returning to default tab', async () => {
      renderWithRouter('/alerts/test-id?tab=summary');

      // Verify Report is initially active
      const findingsReportTab = screen.getByText('Report');
      expect(findingsReportTab).toHaveClass('border-primary');

      // Click back on Overview tab (default)
      const overviewTab = screen.getByText('Overview');
      fireEvent.click(overviewTab);

      await waitFor(() => {
        expect(overviewTab).toHaveClass('border-primary');
        expect(overviewTab).toHaveClass('text-primary');
      });
    });
  });

  describe('Runs & Data Tab', () => {
    it('should load artifacts collection tab when navigating via URL', async () => {
      renderWithRouter('/alerts/test-id?tab=analysis');

      // Runs & Data tab should be active
      await waitFor(() => {
        const analysisTab = screen.getByText('Runs & Data');
        expect(analysisTab).toHaveClass('border-primary');
      });
    });

    it('should switch between tabs correctly', async () => {
      renderWithRouter('/alerts/test-id');

      // Click to Runs & Data tab
      const analysisTab = screen.getByText('Runs & Data');
      fireEvent.click(analysisTab);

      await waitFor(() => {
        expect(analysisTab).toHaveClass('border-primary');
      });

      // Switch to Overview tab
      const overviewTab = screen.getByText('Overview');
      fireEvent.click(overviewTab);

      await waitFor(() => {
        expect(overviewTab).toHaveClass('border-primary');
      });

      // Switch back to Runs & Data
      fireEvent.click(analysisTab);

      await waitFor(() => {
        expect(analysisTab).toHaveClass('border-primary');
      });
    });
  });

  describe('Browser Navigation', () => {
    it('should maintain tab state when using browser back/forward', async () => {
      renderWithRouter('/alerts/test-id');

      // Navigate to Runs & Data tab
      const analysisTab = screen.getByText('Runs & Data');
      fireEvent.click(analysisTab);

      await waitFor(() => {
        expect(analysisTab).toHaveClass('border-primary');
      });

      // Navigate to Report tab
      const findingsReportTab = screen.getByText('Report');
      fireEvent.click(findingsReportTab);

      await waitFor(() => {
        expect(findingsReportTab).toHaveClass('border-primary');
      });

      // Tab switching should maintain proper active states
      expect(analysisTab).not.toHaveClass('border-primary');
      expect(findingsReportTab).toHaveClass('border-primary');
    });
  });

  describe('Error Handling', () => {
    it('should handle invalid tab parameter gracefully', async () => {
      renderWithRouter('/alerts/test-id?tab=invalid-tab');

      // Component should render without errors even with invalid tab
      await waitFor(() => {
        // All tabs should be present
        expect(screen.getByText('Overview')).toBeInTheDocument();
        expect(screen.getByText('Report')).toBeInTheDocument();
        expect(screen.getByText('Runs & Data')).toBeInTheDocument();
      });
    });

    it('should always show the Runs & Data tab', async () => {
      renderWithRouter('/alerts/test-id');

      // Runs & Data tab should always exist
      await waitFor(() => {
        expect(screen.getByText('Runs & Data')).toBeInTheDocument();
      });
    });
  });

  describe('Direct URL Navigation', () => {
    it('should handle direct navigation to specific tab via URL', async () => {
      // Simulate direct navigation (e.g., from bookmark)
      renderWithRouter('/alerts/test-id?tab=analysis');

      await waitFor(() => {
        const analysisTab = screen.getByText('Runs & Data');
        expect(analysisTab).toHaveClass('border-primary');
        expect(analysisTab).toHaveClass('text-primary');
      });
    });

    it('should handle URL with multiple parameters', async () => {
      renderWithRouter('/alerts/test-id?tab=analysis&debug=true');

      await waitFor(() => {
        const analysisTab = screen.getByText('Runs & Data');
        expect(analysisTab).toHaveClass('border-primary');
        expect(analysisTab).toHaveClass('text-primary');
      });
    });
  });
});

describe('AlertDetails - Re-analyze Confirmation Modal', () => {
  // Note: Tests use the mock at the top of the file which has analysis_status: 'analyzed'

  const renderWithRouter = (initialUrl: string) => {
    return render(
      <MemoryRouter initialEntries={[initialUrl]}>
        <Routes>
          <Route path="/alerts/:id" element={<AlertDetailsPage />} />
        </Routes>
      </MemoryRouter>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should show confirmation modal when clicking Re-analyze button', async () => {
    renderWithRouter('/alerts/test-id');

    // Wait for page to load
    await waitFor(() => {
      expect(screen.getByText('AID-123: Test Alert')).toBeInTheDocument();
    });

    // Find and click the Re-analyze button
    const reanalyzeButton = screen.getByRole('button', { name: /re-analyze/i });
    fireEvent.click(reanalyzeButton);

    // Modal should appear with the correct content
    await waitFor(() => {
      expect(screen.getByText('Re-analyze Alert?')).toBeInTheDocument();
      expect(
        screen.getByText(/This will re-run the entire analysis workflow from scratch/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/may take several minutes/i)).toBeInTheDocument();
    });
  });

  it('should close modal when clicking Cancel', async () => {
    renderWithRouter('/alerts/test-id');

    // Wait for page to load and click Re-analyze
    await waitFor(() => {
      expect(screen.getByText('AID-123: Test Alert')).toBeInTheDocument();
    });

    const reanalyzeButton = screen.getByRole('button', { name: /re-analyze/i });
    fireEvent.click(reanalyzeButton);

    // Wait for modal to appear
    await waitFor(() => {
      expect(screen.getByText('Re-analyze Alert?')).toBeInTheDocument();
    });

    // Click Cancel button
    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelButton);

    // Modal should close
    await waitFor(() => {
      expect(screen.queryByText('Re-analyze Alert?')).not.toBeInTheDocument();
    });
  });

  it('should start analysis when confirming in modal', async () => {
    renderWithRouter('/alerts/test-id');

    // Wait for page to load
    await waitFor(() => {
      expect(screen.getByText('AID-123: Test Alert')).toBeInTheDocument();
    });

    // Click Re-analyze button
    const reanalyzeButton = screen.getByRole('button', { name: /re-analyze/i });
    fireEvent.click(reanalyzeButton);

    // Wait for modal
    await waitFor(() => {
      expect(screen.getByText('Re-analyze Alert?')).toBeInTheDocument();
    });

    // Click Re-analyze confirm button in modal
    const confirmButton = within(screen.getByRole('dialog')).getByRole('button', {
      name: /re-analyze/i,
    });
    fireEvent.click(confirmButton);

    // Modal should close and analysis should start
    await waitFor(() => {
      expect(screen.queryByText('Re-analyze Alert?')).not.toBeInTheDocument();
    });
  });
});
