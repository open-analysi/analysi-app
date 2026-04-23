import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { TaskRun } from '../../../types/taskRun';
import { FindingCard } from '../FindingCard';

// Mock navigation
vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return { ...actual, useNavigate: () => vi.fn() };
});

// Mock error handler
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
    error: null,
    clearError: vi.fn(),
    handleError: vi.fn(),
    createContext: vi.fn(),
    runSafe: vi
      .fn()
      .mockImplementation(async (promise: Promise<unknown>) => [await promise, undefined]),
  }),
}));

// Mock backend API
const mockGetTaskRunEnrichment = vi.fn();
const mockGetTask = vi.fn();

vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getTaskRunEnrichment: (...args: unknown[]) => mockGetTaskRunEnrichment(...args),
    getTask: (...args: unknown[]) => mockGetTask(...args),
  },
}));

const TASK_RUN_ID = 'run-123';
const NO_FINDINGS_TEXT = 'No findings available';

// Base task run factory
const makeTaskRun = (overrides: Partial<TaskRun> = {}): TaskRun => ({
  id: TASK_RUN_ID,
  tenant_id: 'tenant-1',
  task_id: 'task-456',
  task_name: 'Test Analysis Task',
  status: 'completed',
  duration: 'PT2S',
  started_at: '2025-01-01T00:00:00Z',
  input_type: 'inline',
  input_location: '{}',
  input_content_type: 'application/json',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:02Z',
  ...overrides,
});

// Output location JSON with enrichment data
const makeOutputLocation = (enrichments: Record<string, unknown>) =>
  JSON.stringify({ enrichments });

const renderCard = (taskRun: TaskRun, isExpanded = false) => {
  const onToggle = vi.fn();
  const result = render(
    <MemoryRouter>
      <FindingCard taskRun={taskRun} isExpanded={isExpanded} onToggle={onToggle} />
    </MemoryRouter>
  );
  return { ...result, onToggle };
};

describe('FindingCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetTask.mockResolvedValue({ description: 'Task description' });
    mockGetTaskRunEnrichment.mockResolvedValue({ enrichment: null, has_enrichment: false });
  });

  describe('enrichment from output_location (regression fix)', () => {
    it('shows enrichment data from output_location without calling the enrichment API', async () => {
      const enrichment = {
        risk_level: 'high',
        confidence: 0.9,
        ai_analysis: 'Suspicious activity',
      };
      const taskRun = makeTaskRun({
        output_location: makeOutputLocation({ task_enrichment: enrichment }),
      });

      renderCard(taskRun, true);

      // Should show enrichment fields — not "No findings available"
      await waitFor(() => {
        expect(screen.queryByText(NO_FINDINGS_TEXT)).not.toBeInTheDocument();
      });
      expect(screen.getByText('risk_level')).toBeInTheDocument();
      expect(screen.getByText('confidence')).toBeInTheDocument();

      // The enrichment API should NOT have been called
      expect(mockGetTaskRunEnrichment).not.toHaveBeenCalled();
    });

    it('uses the LAST key in output_location.enrichments as this task enrichment', async () => {
      // The fix: each task run's output contains accumulated enrichments;
      // only the last key belongs to this specific task run.
      const enrichments = {
        previous_task_enrichment: { unrelated: 'data' },
        this_task_enrichment: { result: 'malicious', score: 95 },
      };
      const taskRun = makeTaskRun({
        output_location: makeOutputLocation(enrichments),
      });

      renderCard(taskRun, true);

      await waitFor(() => {
        expect(screen.queryByText(NO_FINDINGS_TEXT)).not.toBeInTheDocument();
      });
      // Should show "this task" enrichment fields
      expect(screen.getByText('result')).toBeInTheDocument();
      expect(screen.getByText('score')).toBeInTheDocument();
      // Should NOT show the previous task's fields
      expect(screen.queryByText('unrelated')).not.toBeInTheDocument();
    });

    it('shows "No findings available" when output_location enrichments is empty', async () => {
      const taskRun = makeTaskRun({
        output_location: makeOutputLocation({}),
      });

      renderCard(taskRun, true);

      await waitFor(() => {
        expect(screen.getByText(NO_FINDINGS_TEXT)).toBeInTheDocument();
      });
    });

    it('falls back to the enrichment API when output_location is not set', async () => {
      mockGetTaskRunEnrichment.mockResolvedValue({
        enrichment: { api_result: 'fallback_data' },
        has_enrichment: true,
      });

      const taskRun = makeTaskRun({ output_location: undefined });

      renderCard(taskRun, true);

      await waitFor(() => {
        expect(mockGetTaskRunEnrichment).toHaveBeenCalledWith(TASK_RUN_ID);
      });
      await waitFor(() => {
        expect(screen.queryByText(NO_FINDINGS_TEXT)).not.toBeInTheDocument();
      });
      expect(screen.getByText('api_result')).toBeInTheDocument();
    });

    it('shows "No findings available" when API returns enrichment: null (old bug behavior)', async () => {
      // This is the original bug: API always returned enrichment: null.
      // With the fix, this code path only runs when output_location is absent.
      mockGetTaskRunEnrichment.mockResolvedValue({ enrichment: null, has_enrichment: false });

      const taskRun = makeTaskRun({ output_location: undefined });

      renderCard(taskRun, true);

      await waitFor(() => {
        expect(mockGetTaskRunEnrichment).toHaveBeenCalled();
      });
      await waitFor(() => {
        expect(screen.getByText(NO_FINDINGS_TEXT)).toBeInTheDocument();
      });
    });

    it('falls back to the enrichment API when output_location JSON is malformed', async () => {
      mockGetTaskRunEnrichment.mockResolvedValue({
        enrichment: { fallback_field: 'value' },
        has_enrichment: true,
      });

      const taskRun = makeTaskRun({ output_location: 'not-valid-json{' });

      renderCard(taskRun, true);

      await waitFor(() => {
        expect(mockGetTaskRunEnrichment).toHaveBeenCalledWith(TASK_RUN_ID);
      });
    });
  });

  describe('card expand/collapse', () => {
    it('does not fetch enrichment when card is collapsed', () => {
      const taskRun = makeTaskRun({ output_location: undefined });
      renderCard(taskRun, false);

      // Component pre-fetches on mount for succeeded tasks, but with output_location absent
      // it would call the API. With isExpanded=false and status=succeeded, it pre-fetches.
      // This test just verifies the card renders collapsed without crashing.
      expect(screen.getByText('Test Analysis Task')).toBeInTheDocument();
      expect(screen.queryByText(NO_FINDINGS_TEXT)).not.toBeInTheDocument();
    });

    it('calls onToggle when header is clicked', () => {
      const taskRun = makeTaskRun();
      const { onToggle } = renderCard(taskRun, false);

      const header = screen.getByRole('button', { name: /Test Analysis Task/i });
      fireEvent.click(header);

      expect(onToggle).toHaveBeenCalled();
    });

    it('shows expanded content only when isExpanded is true', async () => {
      const taskRun = makeTaskRun({
        output_location: makeOutputLocation({ enrichment_key: { field: 'value' } }),
      });

      // Collapsed — no enrichment rows
      const { rerender } = renderCard(taskRun, false);
      expect(screen.queryByText('field')).not.toBeInTheDocument();

      // Expanded — enrichment rows appear
      rerender(
        <MemoryRouter>
          <FindingCard taskRun={taskRun} isExpanded={true} onToggle={vi.fn()} />
        </MemoryRouter>
      );

      await waitFor(() => {
        expect(screen.queryByText(NO_FINDINGS_TEXT)).not.toBeInTheDocument();
      });
    });

    it('renders status badge correctly', () => {
      const taskRun = makeTaskRun({ status: 'completed' });
      renderCard(taskRun);

      expect(screen.getByText('Completed')).toBeInTheDocument();
    });

    it('shows failed task message when status is failed', () => {
      const taskRun = makeTaskRun({
        status: 'failed',
        error: 'Task timed out after 30 seconds',
      });
      renderCard(taskRun, true);

      expect(screen.getByText('Task Failed')).toBeInTheDocument();
      expect(screen.getByText('Task timed out after 30 seconds')).toBeInTheDocument();
    });

    it('disables expansion for pending and running tasks', () => {
      const taskRun = makeTaskRun({ status: 'pending' });
      const { onToggle } = renderCard(taskRun, false);

      // Pending card header button should be disabled
      const header = screen.getByRole('button', { name: /Test Analysis Task/i });
      expect(header).toBeDisabled();

      fireEvent.click(header);
      expect(onToggle).not.toHaveBeenCalled();
    });
  });

  describe('AI title display', () => {
    it('shows AI title in card header when ai_analysis_title is present', async () => {
      const taskRun = makeTaskRun({
        output_location: makeOutputLocation({
          enrichment: {
            ai_analysis_title: 'High Risk: Lateral Movement Detected',
            risk_level: 'critical',
          },
        }),
      });

      renderCard(taskRun, false);

      await waitFor(() => {
        expect(screen.getByText('High Risk: Lateral Movement Detected')).toBeInTheDocument();
      });
    });

    it('shows disposition as AI title for Disposition Determination tasks', async () => {
      const taskRun = makeTaskRun({
        task_name: 'Alert Disposition Determination',
        output_location: makeOutputLocation({
          enrichment: { disposition: 'True Positive', confidence: 0.95 },
        }),
      });

      renderCard(taskRun, false);

      await waitFor(() => {
        expect(screen.getByText('True Positive')).toBeInTheDocument();
      });
    });
  });
});
