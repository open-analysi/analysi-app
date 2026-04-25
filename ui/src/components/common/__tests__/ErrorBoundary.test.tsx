import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { logger } from '../../../utils/errorHandler';
import ErrorBoundary from '../ErrorBoundary';

// Mock the logger
vi.mock('../../../utils/errorHandler', () => ({
  logger: {
    error: vi.fn(),
  },
  ErrorContext: vi.fn(),
}));

// Component that throws an error
const ErrorComponent = ({ shouldThrow = true }: { shouldThrow?: boolean }) => {
  if (shouldThrow) {
    throw new Error('Test error');
  }
  return <div>Normal component</div>;
};

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Silence React's error boundary console messages for cleaner test output
    const originalConsoleError = console.error;
    console.error = (...args: any[]) => {
      if (
        typeof args[0] === 'string' &&
        args[0].includes('Error boundaries should implement getDerivedStateFromError')
      ) {
        return;
      }
      originalConsoleError(...args);
    };
  });

  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary component="TestComponent">
        <div>Test content</div>
      </ErrorBoundary>
    );

    expect(screen.getByText('Test content')).toBeInTheDocument();
    expect(logger.error).not.toHaveBeenCalled();
  });

  it('renders fallback UI when an error occurs', () => {
    // Using Error Boundary Test utils from React Testing Library
    const spy = vi.spyOn(console, 'error');
    spy.mockImplementation(() => {});

    render(
      <ErrorBoundary component="TestComponent">
        <ErrorComponent />
      </ErrorBoundary>
    );

    // Verify fallback UI is shown
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    // Verify logger was called with context
    expect(logger.error).toHaveBeenCalledTimes(1);
    expect(logger.error).toHaveBeenCalledWith(
      'React component error',
      expect.any(Error),
      expect.objectContaining({
        component: 'TestComponent',
        method: 'render',
      })
    );

    spy.mockRestore();
  });

  it('uses custom fallback when provided', () => {
    const spy = vi.spyOn(console, 'error');
    spy.mockImplementation(() => {});

    render(
      <ErrorBoundary component="TestComponent" fallback={<div>Custom error UI</div>}>
        <ErrorComponent />
      </ErrorBoundary>
    );

    expect(screen.getByText('Custom error UI')).toBeInTheDocument();
    spy.mockRestore();
  });

  it('calls onError callback when provided', () => {
    const spy = vi.spyOn(console, 'error');
    spy.mockImplementation(() => {});

    const handleError = vi.fn();

    render(
      <ErrorBoundary component="TestComponent" onError={handleError}>
        <ErrorComponent />
      </ErrorBoundary>
    );

    expect(handleError).toHaveBeenCalledTimes(1);
    expect(handleError).toHaveBeenCalledWith(
      expect.any(Error),
      expect.objectContaining({
        componentStack: expect.any(String),
      })
    );

    spy.mockRestore();
  });
});
