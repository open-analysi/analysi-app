import { describe, it, expect } from 'vitest';

import { WorkflowRun } from '../../types/workflow';

/**
 * Unit tests for the paused status behavior in ExecutionHistory.
 * These test the pure logic extracted from the component.
 */

// Mirror the component's getStatusBadge logic
function getStatusBadge(status: WorkflowRun['status']): string {
  const baseClasses = 'px-2 py-1 text-xs font-medium rounded-full';
  switch (status) {
    case 'completed':
      return `${baseClasses} bg-green-100 text-green-800 dark:bg-green-800 dark:text-green-200`;
    case 'failed':
      return `${baseClasses} bg-red-100 text-red-800 dark:bg-red-800 dark:text-red-200`;
    case 'running':
      return `${baseClasses} bg-blue-100 text-blue-800 dark:bg-blue-800 dark:text-blue-200`;
    case 'pending':
      return `${baseClasses} bg-yellow-100 text-yellow-800 dark:bg-yellow-800 dark:text-yellow-200`;
    case 'cancelled':
      return `${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200`;
    case 'paused':
      return `${baseClasses} bg-amber-100 text-amber-800 dark:bg-amber-800 dark:text-amber-200`;
    default:
      return `${baseClasses} bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200`;
  }
}

// Mirror the component's getStatusIcon logic
function getStatusIcon(status: WorkflowRun['status']): string {
  switch (status) {
    case 'completed':
      return '✓';
    case 'failed':
      return '✗';
    case 'running':
      return '↻';
    case 'pending':
      return '⏱';
    case 'cancelled':
      return '⊘';
    case 'paused':
      return '⏸';
    default:
      return '?';
  }
}

// Mirror the component's hasRunningExecutions logic for workflows
function hasRunningWorkflows(runs: Pick<WorkflowRun, 'status'>[]): boolean {
  return runs.some(
    (run) => run.status === 'running' || run.status === 'pending' || run.status === 'paused'
  );
}

describe('ExecutionHistory - Paused Status', () => {
  describe('getStatusBadge', () => {
    it('returns amber badge classes for paused status', () => {
      const badge = getStatusBadge('paused');
      expect(badge).toContain('bg-amber-100');
      expect(badge).toContain('text-amber-800');
      expect(badge).toContain('dark:bg-amber-800');
      expect(badge).toContain('dark:text-amber-200');
    });

    it('returns distinct classes from cancelled status', () => {
      const pausedBadge = getStatusBadge('paused');
      const cancelledBadge = getStatusBadge('cancelled');
      expect(pausedBadge).not.toEqual(cancelledBadge);
    });
  });

  describe('getStatusIcon', () => {
    it('returns pause emoji for paused status', () => {
      expect(getStatusIcon('paused')).toBe('⏸');
    });

    it('returns distinct icon from cancelled status', () => {
      expect(getStatusIcon('paused')).not.toEqual(getStatusIcon('cancelled'));
    });
  });

  describe('hasRunningWorkflows (polling)', () => {
    it('returns true when a workflow run is paused', () => {
      expect(hasRunningWorkflows([{ status: 'paused' }])).toBe(true);
    });

    it('returns true when mix of completed and paused', () => {
      expect(hasRunningWorkflows([{ status: 'completed' }, { status: 'paused' }])).toBe(true);
    });

    it('returns false when all workflows are terminal', () => {
      expect(
        hasRunningWorkflows([
          { status: 'completed' },
          { status: 'failed' },
          { status: 'cancelled' },
        ])
      ).toBe(false);
    });

    it('returns true for running status (existing behavior preserved)', () => {
      expect(hasRunningWorkflows([{ status: 'running' }])).toBe(true);
    });

    it('returns true for pending status (existing behavior preserved)', () => {
      expect(hasRunningWorkflows([{ status: 'pending' }])).toBe(true);
    });
  });
});
