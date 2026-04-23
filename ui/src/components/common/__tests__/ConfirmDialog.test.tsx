import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { ConfirmDialog } from '../ConfirmDialog';

describe('ConfirmDialog', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onConfirm: vi.fn(),
    title: 'Confirm Action',
    message: 'Are you sure you want to proceed?',
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    render(<ConfirmDialog {...defaultProps} isOpen={false} />);
    expect(screen.queryByText('Confirm Action')).not.toBeInTheDocument();
  });

  it('renders title and message when open', () => {
    render(<ConfirmDialog {...defaultProps} />);
    expect(screen.getByText('Confirm Action')).toBeInTheDocument();
    expect(screen.getByText('Are you sure you want to proceed?')).toBeInTheDocument();
  });

  it('shows default "Confirm" and "Cancel" button labels', () => {
    render(<ConfirmDialog {...defaultProps} />);
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('shows custom confirm/cancel labels when provided', () => {
    render(<ConfirmDialog {...defaultProps} confirmLabel="Delete Forever" cancelLabel="Keep It" />);
    expect(screen.getByRole('button', { name: 'Delete Forever' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Keep It' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
  });

  it('calls onConfirm when confirm button is clicked', async () => {
    const user = userEvent.setup();
    render(<ConfirmDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onClose when cancel button is clicked', async () => {
    const user = userEvent.setup();
    render(<ConfirmDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
  });

  it('does NOT call onClose when confirm is clicked, and vice versa', async () => {
    const user = userEvent.setup();
    const { unmount } = render(<ConfirmDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1);
    expect(defaultProps.onClose).not.toHaveBeenCalled();

    unmount();
    vi.clearAllMocks();

    render(<ConfirmDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    expect(defaultProps.onConfirm).not.toHaveBeenCalled();
  });

  it('renders warning icon for variant="warning"', () => {
    render(<ConfirmDialog {...defaultProps} variant="warning" />);
    const icon = document.querySelector('.text-yellow-400 svg, svg.text-yellow-400');
    expect(icon).toBeInTheDocument();
  });

  it('renders info icon for variant="info"', () => {
    render(<ConfirmDialog {...defaultProps} variant="info" />);
    const icon = document.querySelector('.text-blue-400 svg, svg.text-blue-400');
    expect(icon).toBeInTheDocument();
  });

  it('renders question icon for variant="question" (default)', () => {
    render(<ConfirmDialog {...defaultProps} />);
    const icon = document.querySelector('.text-primary svg, svg.text-primary');
    expect(icon).toBeInTheDocument();
  });
});
