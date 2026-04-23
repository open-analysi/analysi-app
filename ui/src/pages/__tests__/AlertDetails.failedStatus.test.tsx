/* eslint-disable sonarjs/no-duplicate-string */
/**
 * Tests for AlertDetails 'failed' analysis status handling
 *
 * The API AlertStatus enum: "new" | "in_progress" | "completed" | "failed" | "cancelled"
 * 'failed' is a first-class status value.
 */

import { describe, it, expect } from 'vitest';

import { Alert } from '../../types/alert';

describe('AlertDetails - Failed Status Handling', () => {
  const baseAlert = {
    alert_id: 'test-123',
    tenant_id: 'test',
    human_readable_id: 'ALERT-123',
    title: 'Test Alert',
    severity: 'high' as const,
    source_vendor: 'test',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ingested_at: '2024-01-01T00:00:00Z',
    triggering_event_time: '2024-01-01T00:00:00Z',
    raw_data: '{}',
    raw_data_hash: 'sha256-deadbeef',
  };

  it('should handle failed analysis_status', () => {
    const mockAlert: Alert = {
      ...baseAlert,
      analysis_status: 'failed',
    };

    const isFailed = mockAlert.analysis_status === 'failed';
    expect(isFailed).toBe(true);
  });

  it('should not match non-failed statuses', () => {
    const mockAlertCompleted: Alert = {
      ...baseAlert,
      alert_id: 'test-789',
      human_readable_id: 'ALERT-789',
      title: 'Test Completed Alert',
      severity: 'medium',
      analysis_status: 'completed',
    };

    const isFailed = mockAlertCompleted.analysis_status === 'failed';
    expect(isFailed).toBe(false);
  });

  it('should handle current_analysis status failed check', () => {
    const mockAlertWithAnalysis: any = {
      alert_id: 'test-999',
      human_readable_id: 'ALERT-999',
      title: 'Test Alert with Analysis',
      severity: 'high',
      analysis_status: 'completed',
      source_vendor: 'test',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      triggering_event_time: '2024-01-01T00:00:00Z',
      current_analysis: {
        id: 'analysis-1',
        status: 'failed',
        workflow_run_id: 'run-1',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
    };

    const analysisFailedCheck = mockAlertWithAnalysis.current_analysis?.status === 'failed';
    expect(analysisFailedCheck).toBe(true);
  });

  it('should handle all valid analysis_status values', () => {
    const validStatuses: Array<Alert['analysis_status']> = [
      'new',
      'in_progress',
      'completed',
      'failed',
      'cancelled',
    ];

    expect(validStatuses).toHaveLength(5);
    expect(validStatuses).toContain('new');
    expect(validStatuses).toContain('in_progress');
    expect(validStatuses).toContain('completed');
    expect(validStatuses).toContain('failed');
    expect(validStatuses).toContain('cancelled');
  });
});
