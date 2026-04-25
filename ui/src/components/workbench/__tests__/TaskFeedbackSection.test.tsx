import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { backendApi } from '../../../services/backendApi';
import type { TaskFeedback } from '../../../types/taskFeedback';
import TaskFeedbackSection from '../TaskFeedbackSection';

// Mock the backend API
vi.mock('../../../services/backendApi', () => ({
  backendApi: {
    getTaskFeedback: vi.fn(),
    createTaskFeedback: vi.fn(),
    updateTaskFeedback: vi.fn(),
    deleteTaskFeedback: vi.fn(),
  },
}));

// Mock the error handler
vi.mock('../../../hooks/useErrorHandler', () => ({
  default: () => ({
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

// Mock the user cache store
vi.mock('../../../store/userCacheStore', () => ({
  useUserCacheStore: (selector: (s: { currentUser: { id: string } }) => unknown) =>
    selector({ currentUser: { id: 'current-user-id' } }),
}));

// Mock UserDisplayName
vi.mock('../../common/UserDisplayName', () => ({
  default: ({ userId }: { userId: string }) => <span data-testid="user-display">{userId}</span>,
}));

// Mock ConfirmDialog
vi.mock('../../common/ConfirmDialog', () => ({
  default: ({
    isOpen,
    onConfirm,
    onClose,
  }: {
    isOpen: boolean;
    onConfirm: () => void;
    onClose: () => void;
  }) =>
    isOpen ? (
      <div data-testid="confirm-dialog">
        <button onClick={onConfirm}>Confirm</button>
        <button onClick={onClose}>Cancel Dialog</button>
      </div>
    ) : null,
}));

const FIRST_FEEDBACK_TEXT = 'First feedback item';
const ADD_FEEDBACK_TITLE = 'Add feedback';
const FEEDBACK_PLACEHOLDER = 'Share feedback on this task...';

const mockFeedbacks: TaskFeedback[] = [
  {
    id: 'fb-1',
    tenant_id: 'tenant-1',
    task_component_id: 'task-1',
    title: 'First Feedback Title',
    feedback: FIRST_FEEDBACK_TEXT,
    metadata: {},
    status: 'enabled',
    created_by: 'current-user-id',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 'fb-2',
    tenant_id: 'tenant-1',
    task_component_id: 'task-1',
    title: 'Second Feedback Title',
    feedback: 'Second feedback from someone else',
    metadata: {},
    status: 'enabled',
    created_by: 'other-user',
    created_at: new Date(Date.now() - 86400000).toISOString(),
    updated_at: new Date(Date.now() - 86400000).toISOString(),
  },
];

describe('TaskFeedbackSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(backendApi.getTaskFeedback).mockResolvedValue({
      feedbacks: mockFeedbacks,
      total: 2,
    });
  });

  it('renders section header with feedback count', async () => {
    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText('Feedback')).toBeInTheDocument();
      expect(screen.getByText('(2)')).toBeInTheDocument();
    });
  });

  it('renders feedback items after loading', async () => {
    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(FIRST_FEEDBACK_TEXT)).toBeInTheDocument();
      expect(screen.getByText('Second feedback from someone else')).toBeInTheDocument();
    });
  });

  it('shows empty state when no feedback', async () => {
    vi.mocked(backendApi.getTaskFeedback).mockResolvedValue({
      feedbacks: [],
      total: 0,
    });

    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText('No feedback yet')).toBeInTheDocument();
    });
  });

  it('filters out disabled feedback', async () => {
    vi.mocked(backendApi.getTaskFeedback).mockResolvedValue({
      feedbacks: [{ ...mockFeedbacks[0], status: 'disabled' }, mockFeedbacks[1]],
      total: 2,
    });

    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.queryByText(FIRST_FEEDBACK_TEXT)).not.toBeInTheDocument();
      expect(screen.getByText('Second feedback from someone else')).toBeInTheDocument();
      expect(screen.getByText('(1)')).toBeInTheDocument();
    });
  });

  it('shows inline create form when + Add is clicked', async () => {
    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(FIRST_FEEDBACK_TEXT)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle(ADD_FEEDBACK_TITLE));

    expect(screen.getByPlaceholderText(FEEDBACK_PLACEHOLDER)).toBeInTheDocument();
    expect(screen.getByText('Submit')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('submits new feedback and updates list', async () => {
    const newFeedback: TaskFeedback = {
      id: 'fb-3',
      tenant_id: 'tenant-1',
      task_component_id: 'task-1',
      title: 'New Feedback Title',
      feedback: 'New feedback text',
      metadata: {},
      status: 'enabled',
      created_by: 'current-user-id',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    vi.mocked(backendApi.createTaskFeedback).mockResolvedValue(newFeedback);

    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(FIRST_FEEDBACK_TEXT)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle(ADD_FEEDBACK_TITLE));

    const textarea = screen.getByPlaceholderText(FEEDBACK_PLACEHOLDER);
    fireEvent.change(textarea, { target: { value: 'New feedback text' } });
    fireEvent.click(screen.getByText('Submit'));

    await waitFor(() => {
      expect(backendApi.createTaskFeedback).toHaveBeenCalledWith('task-1', {
        feedback: 'New feedback text',
      });
      expect(screen.getByText('New feedback text')).toBeInTheDocument();
    });
  });

  it('cancels create form and clears text', async () => {
    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(FIRST_FEEDBACK_TEXT)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle(ADD_FEEDBACK_TITLE));
    const textarea = screen.getByPlaceholderText(FEEDBACK_PLACEHOLDER);
    fireEvent.change(textarea, { target: { value: 'Draft text' } });
    fireEvent.click(screen.getByText('Cancel'));

    // Form should be hidden
    expect(screen.queryByPlaceholderText(FEEDBACK_PLACEHOLDER)).not.toBeInTheDocument();
  });

  it('fetches feedback when taskId changes', async () => {
    const { rerender } = render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(backendApi.getTaskFeedback).toHaveBeenCalledWith('task-1');
    });

    rerender(<TaskFeedbackSection taskId="task-2" />);

    await waitFor(() => {
      expect(backendApi.getTaskFeedback).toHaveBeenCalledWith('task-2');
    });
  });

  it('disables submit when textarea is empty', async () => {
    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(FIRST_FEEDBACK_TEXT)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle(ADD_FEEDBACK_TITLE));
    const submitBtn = screen.getByText('Submit');

    expect(submitBtn).toBeDisabled();
  });

  it('disables submit when textarea contains only whitespace', async () => {
    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(FIRST_FEEDBACK_TEXT)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle(ADD_FEEDBACK_TITLE));
    const textarea = screen.getByPlaceholderText(FEEDBACK_PLACEHOLDER);
    fireEvent.change(textarea, { target: { value: '   ' } });

    expect(screen.getByText('Submit')).toBeDisabled();
  });

  it('trims whitespace when submitting feedback', async () => {
    const newFeedback: TaskFeedback = {
      id: 'fb-3',
      tenant_id: 'tenant-1',
      task_component_id: 'task-1',
      title: 'Trimmed Feedback Title',
      feedback: 'Trimmed feedback',
      metadata: {},
      status: 'enabled',
      created_by: 'current-user-id',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    vi.mocked(backendApi.createTaskFeedback).mockResolvedValue(newFeedback);

    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(FIRST_FEEDBACK_TEXT)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle(ADD_FEEDBACK_TITLE));
    const textarea = screen.getByPlaceholderText(FEEDBACK_PLACEHOLDER);
    fireEvent.change(textarea, { target: { value: '  Trimmed feedback  ' } });
    fireEvent.click(screen.getByText('Submit'));

    await waitFor(() => {
      expect(backendApi.createTaskFeedback).toHaveBeenCalledWith('task-1', {
        feedback: 'Trimmed feedback',
      });
    });
  });

  it('renders gracefully when fetch fails', async () => {
    vi.mocked(backendApi.getTaskFeedback).mockRejectedValue(new Error('Network error'));

    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText('Feedback')).toBeInTheDocument();
      expect(screen.getByText('No feedback yet')).toBeInTheDocument();
    });
  });

  it('keeps form open when create fails', async () => {
    vi.mocked(backendApi.createTaskFeedback).mockRejectedValue(new Error('Server error'));

    render(<TaskFeedbackSection taskId="task-1" />);

    await waitFor(() => {
      expect(screen.getByText(FIRST_FEEDBACK_TEXT)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTitle(ADD_FEEDBACK_TITLE));
    const textarea = screen.getByPlaceholderText(FEEDBACK_PLACEHOLDER);
    fireEvent.change(textarea, { target: { value: 'Will fail to submit' } });
    fireEvent.click(screen.getByText('Submit'));

    await waitFor(() => {
      // Form should still be visible with the text preserved
      expect(screen.getByPlaceholderText(FEEDBACK_PLACEHOLDER)).toBeInTheDocument();
      expect(screen.getByDisplayValue('Will fail to submit')).toBeInTheDocument();
    });
  });
});
