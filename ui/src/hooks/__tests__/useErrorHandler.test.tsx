import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { logger } from '../../utils/errorHandler';
import useErrorHandler from '../useErrorHandler';

// Mock the errorHandler module
vi.mock('../../utils/errorHandler', () => ({
  logger: {
    error: vi.fn(),
  },
  classifyError: vi.fn(() => ({
    type: 'validation',
    userMessage: 'Test error message',
    technicalDetails: 'Error: Test error',
  })),
  safeAsync: vi.fn(),
}));

describe('useErrorHandler', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should initialize with no error', () => {
    const { result } = renderHook(() => useErrorHandler('TestComponent'));

    expect(result.current.error).toEqual({
      hasError: false,
      message: '',
      type: undefined,
    });
  });

  it('should handle errors and update error state', () => {
    const { result } = renderHook(() => useErrorHandler('TestComponent'));

    const testError = new Error('Test error');
    const context = result.current.createContext('testMethod', { action: 'test action' });

    act(() => {
      result.current.handleError(testError, context);
    });

    // Verify error state is updated
    expect(result.current.error).toEqual({
      hasError: true,
      message: 'Test error message',
      type: 'validation',
    });

    // Verify error was logged with context
    expect(logger.error).toHaveBeenCalledWith(
      'Operation failed',
      testError,
      expect.objectContaining({
        component: 'TestComponent',
        method: 'testMethod',
        action: 'test action',
      })
    );
  });

  it('should include technical details when option is enabled', () => {
    const { result } = renderHook(() =>
      useErrorHandler('TestComponent', { showTechnicalDetails: true })
    );

    const testError = new Error('Test error');
    const context = result.current.createContext('testMethod');

    act(() => {
      result.current.handleError(testError, context);
    });

    expect(result.current.error.details).toBe('Error: Test error');
  });

  it('should clear errors', () => {
    const { result } = renderHook(() => useErrorHandler('TestComponent'));

    // Set an error first
    act(() => {
      const context = result.current.createContext('testMethod');
      result.current.handleError(new Error('Test error'), context);
    });

    expect(result.current.error.hasError).toBe(true);

    // Then clear it
    act(() => {
      result.current.clearError();
    });

    expect(result.current.error).toEqual({
      hasError: false,
      message: '',
      type: undefined,
    });
  });

  it('should create context with component name and method', () => {
    const { result } = renderHook(() => useErrorHandler('TestComponent'));

    const context = result.current.createContext('testMethod', { action: 'testing' });

    expect(context).toEqual({
      component: 'TestComponent',
      method: 'testMethod',
      action: 'testing',
    });
  });

  it('should handle async operations safely', async () => {
    const { result } = renderHook(() => useErrorHandler('TestComponent'));

    // Mock a failed promise
    const testError = new Error('Async error');
    const failedPromise = Promise.reject(testError);

    let asyncResult: any;
    await act(async () => {
      asyncResult = await result.current.runSafe(failedPromise, 'asyncMethod', {
        action: 'async operation',
      });
    });

    // Verify the promise result is correctly returned
    expect(asyncResult).toEqual([undefined, testError]);

    // Verify error state is updated
    expect(result.current.error.hasError).toBe(true);

    // Verify error was logged with correct context
    expect(logger.error).toHaveBeenCalledWith(
      'Operation failed',
      testError,
      expect.objectContaining({
        component: 'TestComponent',
        method: 'asyncMethod',
        action: 'async operation',
      })
    );
  });
});
