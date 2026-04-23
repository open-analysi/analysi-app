/**
 * Utility functions for workflow execution display.
 */

import { WorkflowExecutionGraph } from '../../types/workflow';

export interface WorkflowStatusDisplay {
  label: string;
  colorClass: string;
}

/**
 * Get the display status and color class for a workflow execution.
 * Centralizes the logic for showing Failed/Cancelled/Completed/Running status.
 */
export function getWorkflowStatusDisplay(
  executionGraph: Pick<WorkflowExecutionGraph, 'status' | 'is_complete'>
): WorkflowStatusDisplay {
  if (executionGraph.status === 'failed') {
    return { label: 'Failed', colorClass: 'text-red' };
  }
  if (executionGraph.status === 'cancelled') {
    return { label: 'Cancelled', colorClass: 'text-yellow' };
  }
  if (executionGraph.is_complete) {
    return { label: 'Completed', colorClass: 'text-green' };
  }
  return { label: 'Running', colorClass: 'text-blue' };
}

/**
 * Get the display status with Tailwind dark mode classes.
 * Use this variant for components that need dark mode support.
 */
export function getWorkflowStatusDisplayWithDarkMode(
  executionGraph: Pick<WorkflowExecutionGraph, 'status' | 'is_complete'>
): WorkflowStatusDisplay {
  if (executionGraph.status === 'failed') {
    return { label: 'Failed', colorClass: 'text-red-600 dark:text-red-400' };
  }
  if (executionGraph.status === 'cancelled') {
    return { label: 'Cancelled', colorClass: 'text-yellow-600 dark:text-yellow-400' };
  }
  if (executionGraph.is_complete) {
    return { label: 'Completed', colorClass: 'text-green-600 dark:text-green-400' };
  }
  return { label: 'Running', colorClass: 'text-blue-600 dark:text-blue-400' };
}
