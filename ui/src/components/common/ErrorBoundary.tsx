import { Component, ErrorInfo, ReactNode } from 'react';

import { logger, ErrorContext } from '../../utils/errorHandler';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  component: string; // Component name for context
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | undefined;
}

/**
 * Error boundary component that catches render errors
 * and provides detailed context for debugging
 */
class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      error: undefined,
    };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      error,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Create rich context for error logging
    const context: ErrorContext = {
      component: this.props.component,
      method: 'render',
      action: 'rendering component',
      meta: {
        componentStack: errorInfo.componentStack,
      },
    };

    // Log with full context
    logger.error('React component error', error, context);

    // Call optional error handler
    if (this.props.onError) {
      this.props.onError(error, errorInfo);
    }
  }

  private renderError(): ReactNode {
    if (this.props.fallback) {
      return this.props.fallback;
    }
    return (
      <div className="p-4 border border-red-300 bg-red-50 rounded-sm text-red-800">
        <h3 className="text-lg font-medium mb-2">Something went wrong</h3>
        <p className="mb-2">The component could not be displayed.</p>
        {/* Show technical details only in development mode */}
        {import.meta?.env?.DEV && this.state.error && (
          <details className="mt-2">
            <summary className="cursor-pointer text-sm">Technical details</summary>
            <pre className="mt-2 text-xs overflow-auto p-2 bg-red-100 rounded-sm">
              {this.state.error.toString()}
            </pre>
          </details>
        )}
      </div>
    );
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return this.renderError();
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
