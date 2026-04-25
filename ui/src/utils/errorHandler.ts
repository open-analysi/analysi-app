/**
 * Centralized error handling utility with rich context preservation
 */

export enum LogLevel {
  ERROR = 'error',
  WARN = 'warn',
  INFO = 'info',
  DEBUG = 'debug',
}

// Default log level based on environment (development or production)
const DEFAULT_LOG_LEVEL = import.meta?.env?.DEV ? LogLevel.DEBUG : LogLevel.ERROR;

// Get log level from env or localStorage for debugging flexibility
export const getLogLevel = (): LogLevel => {
  // Check if localStorage is available (browser environment)
  if (typeof localStorage !== 'undefined') {
    const storedLevel = localStorage.getItem('log_level');
    if (storedLevel && Object.values(LogLevel).includes(storedLevel as LogLevel)) {
      return storedLevel as LogLevel;
    }
  }
  return DEFAULT_LOG_LEVEL;
};

// Log levels as numeric values for comparison
const LOG_LEVEL_VALUES: Record<LogLevel, number> = {
  [LogLevel.ERROR]: 0,
  [LogLevel.WARN]: 1,
  [LogLevel.INFO]: 2,
  [LogLevel.DEBUG]: 3,
};

/**
 * Rich context object for detailed error reporting
 */
export interface ErrorContext {
  // Source identification
  component: string; // Component/module name
  method: string; // Method/function name

  // Action context
  action?: string; // Action being attempted (e.g., "fetching alerts")
  trigger?: string; // What triggered this (e.g., "user click", "initial load")

  // Data context
  params?: Record<string, unknown>; // Function parameters or inputs
  entityId?: string | number; // ID of relevant entity (alertId, userId, etc.)
  entityType?: string; // Type of entity (alert, user, etc.)

  // UI context
  route?: string; // Current route
  view?: string; // Current view or page

  // Additional custom context
  meta?: Record<string, unknown>; // Any additional context
}

/**
 * Standard logger function with emphasis on context
 */
export const logger = {
  error: (message: string, error: unknown, context: ErrorContext) =>
    logMessage(LogLevel.ERROR, message, error, context),

  warn: (message: string, error: unknown, context: ErrorContext) =>
    logMessage(LogLevel.WARN, message, error, context),

  info: (message: string, data: unknown, context: ErrorContext) =>
    logMessage(LogLevel.INFO, message, data, context),

  debug: (message: string, data: unknown, context: ErrorContext) =>
    logMessage(LogLevel.DEBUG, message, data, context),
};

/**
 * Core logging function that preserves and formats rich context
 */
function logMessage(level: LogLevel, message: string, data: unknown, context: ErrorContext): void {
  const currentLevel = getLogLevel();

  // Only log if the level is appropriate
  if (LOG_LEVEL_VALUES[level] <= LOG_LEVEL_VALUES[currentLevel]) {
    // Create context prefix for quick scan in console
    const contextPrefix = `[${context.component}:${context.method}]`;

    // Format full contextual message
    const actionInfo = context.action ? `Action: ${context.action}` : '';
    const triggerInfo = context.trigger ? `Trigger: ${context.trigger}` : '';
    const entityInfo = context.entityId
      ? `${context.entityType || 'Entity'} ID: ${context.entityId}`
      : '';

    // Build the detailed context for clear debugging
    const contextDetails = [actionInfo, triggerInfo, entityInfo].filter(Boolean).join(' | ');

    // Primary message format with context prefix
    const primaryMessage = `${contextPrefix} ${message}${
      contextDetails ? ` (${contextDetails})` : ''
    }`;

    // Include full context for detailed debugging
    const contextObject = {
      ...context,
      level,
      timestamp: new Date().toISOString(),
    };

    // Optionally, log to console during development
    // if (process.env.NODE_ENV === 'development') {
    //   console.error('[Error Handling]', message, { error, context: finalContext });
    // }

    switch (level) {
      case LogLevel.ERROR: {
        console.error(primaryMessage, data, contextObject);
        break;
      }
      case LogLevel.WARN: {
        console.warn(primaryMessage, data, contextObject);
        break;
      }
      case LogLevel.INFO: {
        console.info(primaryMessage, data, contextObject);
        break;
      }
      case LogLevel.DEBUG: {
        // eslint-disable-next-line no-console
        console.debug(primaryMessage, data, contextObject);
        break;
      }
      default: {
        // eslint-disable-next-line no-console
        console.log(primaryMessage, data, contextObject);
        break;
      }
    }
  }
}

/**
 * Format error with full stack trace and context
 */
export function formatErrorDetails(error: unknown): string {
  if (error instanceof Error) {
    const stack = error.stack ? '\n' + error.stack : '';
    return `${error.name}: ${error.message}${stack}`;
  }
  return String(error);
}

/**
 * Standard try/catch wrapper for async functions with rich context preservation
 * Returns [result, error] tuple
 */
export async function safeAsync<T>(
  promise: Promise<T>,
  context: ErrorContext
): Promise<[T | undefined, Error | undefined]> {
  try {
    const result = await promise;
    return [result, undefined];
  } catch (error) {
    // Log the error with full context
    logger.error(`Failed: ${context.action || 'operation'}`, error, context);
    return [undefined, error instanceof Error ? error : new Error(String(error))];
  }
}

/**
 * Classification of common error types with contextual user messages
 */
// Common error types
type ErrorType = 'network' | 'validation' | 'authorization' | 'notFound' | 'server' | 'unknown';

// Handle HTTP status codes
function getErrorTypeFromStatus(status: number): { type: ErrorType; message: string } {
  // Client errors
  if (status >= 400 && status < 500) {
    if (status === 401 || status === 403) {
      return {
        type: 'authorization',
        message: 'You do not have permission to perform this action',
      };
    }

    if (status === 404) {
      return {
        type: 'notFound',
        message: 'The requested resource was not found',
      };
    }

    if (status === 422) {
      return {
        type: 'validation',
        message: 'Some provided information is invalid',
      };
    }

    return {
      type: 'validation',
      message: 'There was an issue with your request',
    };
  }

  // Server errors
  if (status >= 500) {
    return {
      type: 'server',
      message: 'The server encountered an error',
    };
  }

  // Unknown status code
  return {
    type: 'unknown',
    message: 'An unexpected error occurred',
  };
}

export function classifyError(
  error: unknown,
  context?: ErrorContext
): {
  type: ErrorType;
  userMessage: string;
  technicalDetails: string;
} {
  let type: ErrorType = 'unknown';
  let userMessage = 'An unexpected error occurred';
  let technicalDetails = '';

  if (error instanceof Error) {
    technicalDetails = formatErrorDetails(error);

    // Axios errors
    const axiosError = error as Error & { response?: { status: number } };
    if (axiosError.response) {
      const result = getErrorTypeFromStatus(axiosError.response.status);
      type = result.type;
      userMessage = result.message;

      // Add entity context if available
      if (type === 'notFound' && context?.entityType) {
        userMessage = `The requested ${context.entityType} was not found`;
      }
    }
    // Network errors
    else if (
      error.name === 'NetworkError' ||
      error.message.includes('network') ||
      error.message.includes('connection')
    ) {
      type = 'network';
      userMessage = 'Unable to connect to the server';
    }
  }

  // Add action context if available
  if (context?.action && type !== 'unknown') {
    userMessage = `Error ${context.action}: ${userMessage.toLowerCase()}`;
  }

  return { type, userMessage, technicalDetails };
}
