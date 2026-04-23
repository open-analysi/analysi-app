import React from 'react';

interface EmptyStateProps {
  /**
   * Optional icon component to display above the title
   */
  icon?: React.ComponentType<{ className?: string }>;
  /**
   * Main title text (bold, larger)
   */
  title: string;
  /**
   * Descriptive message text (smaller, muted)
   */
  message: string;
  /**
   * Optional action button label
   */
  actionLabel?: string;
  /**
   * Optional action button click handler
   */
  onAction?: () => void;
}

/**
 * EmptyState Component
 *
 * A standardized component for displaying empty states across the application.
 * Uses dark theme styling consistent with the design system.
 *
 * @example
 * ```tsx
 * <EmptyState
 *   icon={InboxIcon}
 *   title="No tasks found"
 *   message="Create your first task to get started"
 *   actionLabel="Create Task"
 *   onAction={() => setShowCreateModal(true)}
 * />
 * ```
 */
export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon,
  title,
  message,
  actionLabel,
  onAction,
}) => {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      {Icon && (
        <div className="mb-4">
          <Icon className="h-12 w-12 text-gray-500 dark:text-gray-600" />
        </div>
      )}

      <h3 className="text-lg font-semibold text-gray-700 dark:text-gray-300 mb-2">{title}</h3>

      <p className="text-sm text-gray-500 dark:text-gray-400 text-center max-w-md mb-6">
        {message}
      </p>

      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary hover:bg-primary/90 transition-colors focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
};
