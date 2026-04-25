import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { backendApi } from '../../services/backendApi';
import { Workflow, WorkflowRun } from '../../types/workflow';

// Mock useErrorHandler
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

// Mock backendApi
vi.mock('../../services/backendApi', () => ({
  backendApi: {
    getWorkflowRun: vi.fn(),
    getWorkflow: vi.fn(),
  },
}));

// Lazy import after mocks
const { default: WorkflowRunPage } = await import('../WorkflowRunPage');

function renderWithRoute(runId: string) {
  return render(
    <MemoryRouter initialEntries={[`/workflow-runs/${runId}`]}>
      <Routes>
        <Route path="/workflow-runs/:runId" element={<WorkflowRunPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const MOCK_RUN_ID = '550e8400-e29b-41d4-a716-446655440000';
const MOCK_WORKFLOW_ID = '660e8400-e29b-41d4-a716-446655440000';

const mockWorkflowRun: WorkflowRun = {
  workflow_run_id: MOCK_RUN_ID,
  workflow_id: MOCK_WORKFLOW_ID,
  status: 'completed',
  input_data: {},
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:01:00Z',
  started_at: '2025-01-01T00:00:00Z',
  completed_at: '2025-01-01T00:01:00Z',
};

const mockWorkflow: Workflow = {
  id: MOCK_WORKFLOW_ID,
  tenant_id: 'test-tenant',
  name: 'Test Workflow',
  description: '',
  is_dynamic: false,
  io_schema: { input: {}, output: {} },
  status: 'enabled',
  created_by: 'test-user',
  created_at: '2025-01-01T00:00:00Z',
  planner_id: null,
  nodes: [],
  edges: [],
};

describe('WorkflowRunPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not call getWorkflow when workflow_id is null', async () => {
    const runWithNullWorkflowId: WorkflowRun = {
      ...mockWorkflowRun,
      workflow_id: null as unknown as string, // Simulate backend returning null
    };

    vi.mocked(backendApi.getWorkflowRun).mockResolvedValue(runWithNullWorkflowId);
    vi.mocked(backendApi.getWorkflow).mockResolvedValue(mockWorkflow);

    renderWithRoute(MOCK_RUN_ID);

    await waitFor(() => {
      expect(backendApi.getWorkflowRun).toHaveBeenCalledWith(MOCK_RUN_ID);
    });

    // getWorkflow should NOT be called with null
    expect(backendApi.getWorkflow).not.toHaveBeenCalled();
  });

  it('does not call getWorkflow when workflow_id is undefined', async () => {
    const runWithUndefinedWorkflowId: WorkflowRun = {
      ...mockWorkflowRun,
      workflow_id: undefined as unknown as string, // Simulate backend returning undefined
    };

    vi.mocked(backendApi.getWorkflowRun).mockResolvedValue(runWithUndefinedWorkflowId);
    vi.mocked(backendApi.getWorkflow).mockResolvedValue(mockWorkflow);

    renderWithRoute(MOCK_RUN_ID);

    await waitFor(() => {
      expect(backendApi.getWorkflowRun).toHaveBeenCalledWith(MOCK_RUN_ID);
    });

    expect(backendApi.getWorkflow).not.toHaveBeenCalled();
  });

  it('fetches workflow when workflow_id is valid', async () => {
    vi.mocked(backendApi.getWorkflowRun).mockResolvedValue(mockWorkflowRun);
    vi.mocked(backendApi.getWorkflow).mockResolvedValue(mockWorkflow);

    renderWithRoute(MOCK_RUN_ID);

    await waitFor(() => {
      expect(backendApi.getWorkflow).toHaveBeenCalledWith(MOCK_WORKFLOW_ID);
    });

    await waitFor(() => {
      expect(screen.getByText('Test Workflow')).toBeInTheDocument();
    });
  });

  it('shows error when workflow run is not found', async () => {
    vi.mocked(backendApi.getWorkflowRun).mockResolvedValue(null as unknown as WorkflowRun);

    renderWithRoute(MOCK_RUN_ID);

    await waitFor(() => {
      expect(screen.getByText('Workflow run not found.')).toBeInTheDocument();
    });

    expect(backendApi.getWorkflow).not.toHaveBeenCalled();
  });

  it('shows workflow_name from run when workflow_id is null', async () => {
    const adHocRun: WorkflowRun = {
      ...mockWorkflowRun,
      workflow_id: null as unknown as string,
      workflow_name: 'Ad Hoc Workflow',
    };

    vi.mocked(backendApi.getWorkflowRun).mockResolvedValue(adHocRun);

    renderWithRoute(MOCK_RUN_ID);

    await waitFor(() => {
      expect(screen.getByText('Ad Hoc Workflow')).toBeInTheDocument();
    });
  });

  it('shows fallback message when no workflow graph is available', async () => {
    const adHocRun: WorkflowRun = {
      ...mockWorkflowRun,
      workflow_id: null as unknown as string,
      workflow_name: 'Ad Hoc Workflow',
    };

    vi.mocked(backendApi.getWorkflowRun).mockResolvedValue(adHocRun);

    renderWithRoute(MOCK_RUN_ID);

    await waitFor(() => {
      expect(screen.getByText('No workflow graph available for this run.')).toBeInTheDocument();
    });
  });

  it('renders paused status with amber color', async () => {
    const pausedRun: WorkflowRun = {
      ...mockWorkflowRun,
      status: 'paused',
      completed_at: undefined,
    };

    vi.mocked(backendApi.getWorkflowRun).mockResolvedValue(pausedRun);
    vi.mocked(backendApi.getWorkflow).mockResolvedValue(mockWorkflow);

    renderWithRoute(MOCK_RUN_ID);

    await waitFor(() => {
      const statusEl = screen.getByText('paused');
      expect(statusEl).toBeInTheDocument();
      expect(statusEl.className).toContain('text-amber-400');
    });
  });
});
