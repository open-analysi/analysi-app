import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { UnsavedChangesDialog } from '../UnsavedChangesDialog';

describe('UnsavedChangesDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onSave: vi.fn(),
    onSaveAs: vi.fn(),
    onDiscard: vi.fn(),
    canSave: true,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    render(<UnsavedChangesDialog {...defaultProps} isOpen={false} />);
    expect(screen.queryByText('Unsaved Changes')).not.toBeInTheDocument();
  });

  it('renders the dialog title when open', () => {
    render(<UnsavedChangesDialog {...defaultProps} />);
    expect(screen.getByText('Unsaved Changes')).toBeInTheDocument();
  });

  it('shows generic description when no taskName provided', () => {
    render(<UnsavedChangesDialog {...defaultProps} />);
    expect(
      screen.getByText('You have unsaved changes. What would you like to do?')
    ).toBeInTheDocument();
  });

  it('shows task name in description when taskName provided', () => {
    render(<UnsavedChangesDialog {...defaultProps} taskName="My Task" />);
    expect(screen.getByText('My Task')).toBeInTheDocument();
    expect(screen.getByText(/You have unsaved changes to/)).toBeInTheDocument();
    expect(screen.getByText(/What would you like to do\?/)).toBeInTheDocument();
  });

  it('shows Save Changes button when canSave is true', () => {
    render(<UnsavedChangesDialog {...defaultProps} canSave={true} />);
    expect(screen.getByRole('button', { name: 'Save Changes' })).toBeInTheDocument();
  });

  it('hides Save Changes button when canSave is false', () => {
    render(<UnsavedChangesDialog {...defaultProps} canSave={false} />);
    expect(screen.queryByRole('button', { name: 'Save Changes' })).not.toBeInTheDocument();
  });

  it('always shows Save As New Task button regardless of canSave', () => {
    const { rerender } = render(<UnsavedChangesDialog {...defaultProps} canSave={true} />);
    expect(screen.getByRole('button', { name: 'Save As New Task...' })).toBeInTheDocument();

    rerender(<UnsavedChangesDialog {...defaultProps} canSave={false} />);
    expect(screen.getByRole('button', { name: 'Save As New Task...' })).toBeInTheDocument();
  });

  it('always shows Discard Changes button', () => {
    render(<UnsavedChangesDialog {...defaultProps} />);
    expect(screen.getByRole('button', { name: 'Discard Changes' })).toBeInTheDocument();
  });

  it('always shows Cancel button', () => {
    render(<UnsavedChangesDialog {...defaultProps} />);
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('calls onSave when Save Changes is clicked', async () => {
    const user = userEvent.setup();
    render(<UnsavedChangesDialog {...defaultProps} canSave={true} />);
    await user.click(screen.getByRole('button', { name: 'Save Changes' }));
    expect(defaultProps.onSave).toHaveBeenCalledTimes(1);
    expect(defaultProps.onSaveAs).not.toHaveBeenCalled();
    expect(defaultProps.onDiscard).not.toHaveBeenCalled();
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  it('calls onSaveAs when Save As New Task is clicked', async () => {
    const user = userEvent.setup();
    render(<UnsavedChangesDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: 'Save As New Task...' }));
    expect(defaultProps.onSaveAs).toHaveBeenCalledTimes(1);
    expect(defaultProps.onSave).not.toHaveBeenCalled();
    expect(defaultProps.onDiscard).not.toHaveBeenCalled();
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  it('calls onDiscard when Discard Changes is clicked', async () => {
    const user = userEvent.setup();
    render(<UnsavedChangesDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: 'Discard Changes' }));
    expect(defaultProps.onDiscard).toHaveBeenCalledTimes(1);
    expect(defaultProps.onSave).not.toHaveBeenCalled();
    expect(defaultProps.onSaveAs).not.toHaveBeenCalled();
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup();
    render(<UnsavedChangesDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    expect(defaultProps.onSave).not.toHaveBeenCalled();
    expect(defaultProps.onSaveAs).not.toHaveBeenCalled();
    expect(defaultProps.onDiscard).not.toHaveBeenCalled();
  });

  it('renders warning icon', () => {
    render(<UnsavedChangesDialog {...defaultProps} />);
    // The ExclamationTriangleIcon renders as an SVG
    const icon = document.querySelector('.text-yellow-500 svg, svg.text-yellow-500');
    expect(icon).toBeInTheDocument();
  });
});
