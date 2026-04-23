import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import {
  logger,
  getLogLevel,
  LogLevel,
  safeAsync,
  classifyError,
  formatErrorDetails,
  ErrorContext,
} from '../errorHandler';

describe('errorHandler', () => {
  // Create mocks for console methods
  const errorMock = vi.fn();
  const warnMock = vi.fn();
  const infoMock = vi.fn();
  const debugMock = vi.fn();

  beforeEach(() => {
    // Assign mocks to console methods
    vi.spyOn(console, 'error').mockImplementation(errorMock);
    vi.spyOn(console, 'warn').mockImplementation(warnMock);
    vi.spyOn(console, 'info').mockImplementation(infoMock);
    vi.spyOn(console, 'debug').mockImplementation(debugMock);

    // Mock localStorage
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn(),
        setItem: vi.fn(),
        removeItem: vi.fn(),
      },
      writable: true,
    });
  });

  afterEach(() => {
    // Restore mocks
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  describe('logger', () => {
    const testContext: ErrorContext = {
      component: 'TestComponent',
      method: 'testMethod',
      action: 'testing',
    };

    it('should log errors with context', () => {
      logger.error('Test error', new Error('Error message'), testContext);
      expect(console.error).toHaveBeenCalled();

      // Verify the context is included
      const callArgs = (console.error as any).mock.calls[0];
      expect(callArgs[0]).toContain('[TestComponent:testMethod]');
      expect(callArgs[0]).toContain('Test error');
      expect(callArgs[0]).toContain('Action: testing');
    });

    it('should log warnings with context', () => {
      logger.warn('Test warning', { data: 'test' }, testContext);
      expect(console.warn).toHaveBeenCalled();

      const callArgs = (console.warn as any).mock.calls[0];
      expect(callArgs[0]).toContain('[TestComponent:testMethod]');
    });

    it('should log entity details when provided', () => {
      const contextWithEntity: ErrorContext = {
        ...testContext,
        entityId: '12345',
        entityType: 'Alert',
      };

      logger.error('Entity error', new Error('Error with entity'), contextWithEntity);

      const callArgs = (console.error as any).mock.calls[0];
      expect(callArgs[0]).toContain('Alert ID: 12345');
    });
  });

  describe('getLogLevel', () => {
    it('should use localStorage value if valid', () => {
      (localStorage.getItem as any).mockReturnValue(LogLevel.WARN);
      expect(getLogLevel()).toBe(LogLevel.WARN);
    });

    it('should ignore invalid localStorage values', () => {
      (localStorage.getItem as any).mockReturnValue('INVALID_LEVEL');

      // In tests, we typically run in development mode
      expect(getLogLevel()).toBe(LogLevel.DEBUG);
    });
  });

  describe('safeAsync', () => {
    const testContext: ErrorContext = {
      component: 'TestComponent',
      method: 'testMethod',
      action: 'testing async function',
    };

    it('should return result for successful promise', async () => {
      const promise = Promise.resolve('success');
      const [result, error] = await safeAsync(promise, testContext);

      expect(result).toBe('success');
      expect(error).toBeUndefined();
      expect(console.error).not.toHaveBeenCalled();
    });

    it('should return error for failed promise', async () => {
      const testError = new Error('Test failure');
      const promise = Promise.reject(testError);
      const [result, error] = await safeAsync(promise, testContext);

      expect(result).toBeUndefined();
      expect(error).toBe(testError);
      expect(console.error).toHaveBeenCalled();
    });
  });

  describe('classifyError', () => {
    it('should classify network errors', () => {
      const networkError = new Error('Network connection failed');
      networkError.name = 'NetworkError';

      const result = classifyError(networkError);
      expect(result.type).toBe('network');
      expect(result.userMessage).toContain('Unable to connect');
    });

    it('should add context to user messages', () => {
      const error = new Error('Not found');
      const context: ErrorContext = {
        component: 'TestComponent',
        method: 'testMethod',
        action: 'fetching alert data',
        entityType: 'alert',
      };

      // Mock axios-like response structure
      (error as any).response = { status: 404 };

      const result = classifyError(error, context);
      expect(result.type).toBe('notFound');
      expect(result.userMessage).toContain('alert was not found');
      expect(result.userMessage).toContain('Error fetching alert data');
    });
  });

  describe('formatErrorDetails', () => {
    it('should format Error objects with stack trace', () => {
      const error = new Error('Test error');
      const formatted = formatErrorDetails(error);

      expect(formatted).toContain('Error: Test error');
      expect(formatted).toContain(error.stack);
    });

    it('should handle non-Error objects', () => {
      const nonError = { message: 'Not an error' };
      const formatted = formatErrorDetails(nonError);

      expect(formatted).toBe('[object Object]');
    });
  });
});
