import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import type { TaskFeedback } from '../../../types/taskFeedback';
import TaskFeedbackItem from '../TaskFeedbackItem';

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
    title,
  }: {
    isOpen: boolean;
    onConfirm: () => void;
    onClose: () => void;
    title: string;
  }) =>
    isOpen ? (
      <div data-testid="confirm-dialog">
        <span>{title}</span>
        <button onClick={onConfirm}>Confirm</button>
        <button onClick={onClose}>Cancel Dialog</button>
      </div>
    ) : null,
}));

const MOCK_FEEDBACK_TEXT = 'This task needs better error handling.';
const EDIT_FEEDBACK_TITLE = 'Edit feedback';

const mockFeedback: TaskFeedback = {
  id: 'fb-1',
  tenant_id: 'tenant-1',
  task_component_id: 'task-1',
  title: 'Improve Error Handling',
  feedback: MOCK_FEEDBACK_TEXT,
  metadata: {},
  status: 'enabled',
  created_by: 'user-1',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const longFeedback: TaskFeedback = {
  ...mockFeedback,
  id: 'fb-2',
  feedback:
    'This is a very long feedback message that goes well over 150 characters to test the truncation behavior. ' +
    'It should be truncated when not expanded and fully visible when the user clicks show more to expand it.',
};

describe('TaskFeedbackItem', () => {
  const mockOnUpdate = vi.fn().mockResolvedValue(undefined);
  const mockOnDelete = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders title, feedback text and author', () => {
    render(
      <TaskFeedbackItem
        item={mockFeedback}
        currentUserId="user-1"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    );

    expect(screen.getByText('Improve Error Handling')).toBeInTheDocument();
    expect(screen.getByText(MOCK_FEEDBACK_TEXT)).toBeInTheDocument();
    expect(screen.getByTestId('user-display')).toHaveTextContent('user-1');
  });

  it('shows edit/delete icons only for owner', () => {
    const { rerender } = render(
      <TaskFeedbackItem
        item={mockFeedback}
        currentUserId="user-1"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    );

    // Owner should have edit and delete buttons
    expect(screen.getByTitle(EDIT_FEEDBACK_TITLE)).toBeInTheDocument();
    expect(screen.getByTitle('Delete feedback')).toBeInTheDocument();

    // Non-owner should not
    rerender(
      <TaskFeedbackItem
        item={mockFeedback}
        currentUserId="other-user"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    );

    expect(screen.queryByTitle(EDIT_FEEDBACK_TITLE)).not.toBeInTheDocument();
    expect(screen.queryByTitle('Delete feedback')).not.toBeInTheDocument();
  });

  it('enters edit mode and saves changes', async () => {
    render(
      <TaskFeedbackItem
        item={mockFeedback}
        currentUserId="user-1"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    );

    fireEvent.click(screen.getByTitle(EDIT_FEEDBACK_TITLE));

    const textarea = screen.getByRole('textbox');
    expect(textarea).toHaveValue(MOCK_FEEDBACK_TEXT);

    fireEvent.change(textarea, { target: { value: 'Updated feedback text' } });
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(mockOnUpdate).toHaveBeenCalledWith('fb-1', { feedback: 'Updated feedback text' });
    });
  });

  it('cancels edit mode without saving', () => {
    render(
      <TaskFeedbackItem
        item={mockFeedback}
        currentUserId="user-1"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    );

    fireEvent.click(screen.getByTitle(EDIT_FEEDBACK_TITLE));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'changed text' } });
    fireEvent.click(screen.getByText('Cancel'));

    expect(mockOnUpdate).not.toHaveBeenCalled();
    expect(screen.getByText(MOCK_FEEDBACK_TEXT)).toBeInTheDocument();
  });

  it('shows confirm dialog on delete and calls onDelete on confirm', async () => {
    render(
      <TaskFeedbackItem
        item={mockFeedback}
        currentUserId="user-1"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    );

    fireEvent.click(screen.getByTitle('Delete feedback'));
    expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
    expect(screen.getByText('Delete Feedback?')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Confirm'));

    await waitFor(() => {
      expect(mockOnDelete).toHaveBeenCalledWith('fb-1');
    });
  });

  it('does not call onUpdate when saving with unchanged text', async () => {
    render(
      <TaskFeedbackItem
        item={mockFeedback}
        currentUserId="user-1"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    );

    fireEvent.click(screen.getByTitle(EDIT_FEEDBACK_TITLE));
    // Text is unchanged, click Save
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      // Should exit edit mode without calling onUpdate
      expect(mockOnUpdate).not.toHaveBeenCalled();
      expect(screen.getByText(MOCK_FEEDBACK_TEXT)).toBeInTheDocument();
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    });
  });

  it('disables Save button when edit text is whitespace-only', () => {
    render(
      <TaskFeedbackItem
        item={mockFeedback}
        currentUserId="user-1"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    );

    fireEvent.click(screen.getByTitle(EDIT_FEEDBACK_TITLE));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: '   ' } });

    expect(screen.getByText('Save')).toBeDisabled();
    expect(mockOnUpdate).not.toHaveBeenCalled();
  });

  it('dismissing delete dialog does not call onDelete', () => {
    render(
      <TaskFeedbackItem
        item={mockFeedback}
        currentUserId="user-1"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    );

    fireEvent.click(screen.getByTitle('Delete feedback'));
    expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();

    // Click cancel in the dialog
    fireEvent.click(screen.getByText('Cancel Dialog'));

    expect(mockOnDelete).not.toHaveBeenCalled();
    expect(screen.queryByTestId('confirm-dialog')).not.toBeInTheDocument();
  });

  it('shows "show more" for long feedback and toggles', () => {
    render(
      <TaskFeedbackItem
        item={longFeedback}
        currentUserId="user-1"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    );

    expect(screen.getByText('show more')).toBeInTheDocument();

    fireEvent.click(screen.getByText('show more'));
    expect(screen.getByText('show less')).toBeInTheDocument();

    fireEvent.click(screen.getByText('show less'));
    expect(screen.getByText('show more')).toBeInTheDocument();
  });
});
