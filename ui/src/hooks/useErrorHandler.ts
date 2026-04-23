import { useState, useCallback } from 'react';

import { ErrorContext, logger, classifyError } from '../utils/errorHandler';

interface ErrorState {
  hasError: boolean;
  message: string;
  type: 'network' | 'validation' | 'authorization' | 'notFound' | 'server' | 'unknown' | undefined;
  details?: string;
}

interface UseErrorHandlerOptions {
  showTechnicalDetails?: boolean; // Whether to include technical details in the error state
}

/**
 * Hook for consistent error handling in components
 * Provides methods to handle errors with rich context
 */
function useErrorHandler(componentName: string, options: UseErrorHandlerOptions = {}) {
  const [error, setError] = useState<ErrorState>({
    hasError: false,
    message: '',
    type: undefined,
  });

  /**
   * Clear the current error state
   */
  const clearError = useCallback(() => {
    setError({
      hasError: false,
      message: '',
      type: undefined,
    });
  }, []);

  /**
   * Create an error context object with component name
   */
  const createContext = useCallback(
    (methodName: string, contextDetails: Partial<ErrorContext> = {}): ErrorContext => {
      return {
        component: componentName,
        method: methodName,
        ...contextDetails,
      };
    },
    [componentName]
  );

  /**
   * Handle and set an error with context
   */
  const handleError = useCallback(
    (error: unknown, context: ErrorContext) => {
      // Log the error with full context
      logger.error('Operation failed', error, context);

      // Classify the error and get relevant messages
      const { type, userMessage, technicalDetails } = classifyError(error, context);

      // Set the error state
      setError({
        hasError: true,
        message: userMessage,
        type,
        ...(options.showTechnicalDetails ? { details: technicalDetails } : {}),
      });

      return { type, userMessage };
    },
    [options.showTechnicalDetails]
  );

  /**
   * Wrapper for safe async operations with automatic context creation
   */
  const runSafe = useCallback(
    async <T>(
      promise: Promise<T>,
      methodName: string,
      contextDetails: Partial<ErrorContext> = {}
    ): Promise<[T | undefined, Error | undefined]> => {
      const context = createContext(methodName, contextDetails);

      try {
        const result = await promise;
        return [result, undefined];
      } catch (error_) {
        handleError(error_, context);
        return [undefined, error_ instanceof Error ? error_ : new Error(String(error_))];
      }
    },
    [createContext, handleError]
  );

  return {
    error,
    clearError,
    handleError,
    createContext,
    runSafe,
  };
}

export default useErrorHandler;
