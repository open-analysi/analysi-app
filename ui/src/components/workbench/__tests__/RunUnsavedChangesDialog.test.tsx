import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { RunUnsavedChangesDialog } from '../RunUnsavedChangesDialog';

describe('RunUnsavedChangesDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onSaveAndRun: vi.fn(),
    onSaveAsAndRun: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    render(<RunUnsavedChangesDialog {...defaultProps} isOpen={false} />);
    expect(screen.queryByText('Run with Unsaved Changes?')).not.toBeInTheDocument();
  });

  it('renders the dialog title when open', () => {
    render(<RunUnsavedChangesDialog {...defaultProps} />);
    expect(screen.getByText('Run with Unsaved Changes?')).toBeInTheDocument();
  });

  it('shows generic description when no taskName provided', () => {
    render(<RunUnsavedChangesDialog {...defaultProps} />);
    expect(
      screen.getByText('You have unsaved changes. How would you like to proceed?')
    ).toBeInTheDocument();
  });

  it('shows task name in description when taskName provided', () => {
    render(<RunUnsavedChangesDialog {...defaultProps} taskName="My Task" />);
    expect(screen.getByText('My Task')).toBeInTheDocument();
    expect(screen.getByText(/You have unsaved changes to/)).toBeInTheDocument();
    expect(screen.getByText(/How would you like to proceed\?/)).toBeInTheDocument();
  });

  it('shows all three buttons', () => {
    render(<RunUnsavedChangesDialog {...defaultProps} />);
    expect(screen.getByRole('button', { name: 'Save and Run' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save As New Task and Run...' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('calls onSaveAndRun when Save and Run is clicked', async () => {
    const user = userEvent.setup();
    render(<RunUnsavedChangesDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: 'Save and Run' }));
    expect(defaultProps.onSaveAndRun).toHaveBeenCalledTimes(1);
    expect(defaultProps.onSaveAsAndRun).not.toHaveBeenCalled();
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  it('calls onSaveAsAndRun when Save As New Task and Run... is clicked', async () => {
    const user = userEvent.setup();
    render(<RunUnsavedChangesDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: 'Save As New Task and Run...' }));
    expect(defaultProps.onSaveAsAndRun).toHaveBeenCalledTimes(1);
    expect(defaultProps.onSaveAndRun).not.toHaveBeenCalled();
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup();
    render(<RunUnsavedChangesDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    expect(defaultProps.onSaveAndRun).not.toHaveBeenCalled();
    expect(defaultProps.onSaveAsAndRun).not.toHaveBeenCalled();
  });

  it('renders warning icon', () => {
    render(<RunUnsavedChangesDialog {...defaultProps} />);
    // The ExclamationTriangleIcon renders as an SVG
    const icon = document.querySelector('.text-yellow-500 svg, svg.text-yellow-500');
    expect(icon).toBeInTheDocument();
  });
});
