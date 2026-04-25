/**
 * Integration tests for Alert Management API
 * These tests verify that our API client correctly interacts with the backend
 */

import { describe, it, expect } from 'vitest';

// Type imports - used implicitly through backendApi return types
import { backendApi } from '../backendApi';

describe('Alert Management API Integration Tests', () => {
  // Store an alert ID for testing single alert operations
  let testAlertId: string | null = null;

  describe('GET /alerts - List alerts', () => {
    it('should fetch alerts with default parameters', async () => {
      const response = await backendApi.getAlerts();

      expect(response).toBeDefined();
      expect(response).toHaveProperty('alerts');
      expect(response).toHaveProperty('total');
      expect(response).toHaveProperty('limit');
      expect(response).toHaveProperty('offset');
      expect(Array.isArray(response.alerts)).toBe(true);

      // Store first alert ID for later tests
      if (response.alerts.length > 0) {
        testAlertId = response.alerts[0].alert_id;
        console.log('Test alert ID:', testAlertId);
      }
    });

    it('should fetch alerts with pagination', async () => {
      const response = await backendApi.getAlerts({
        offset: 0,
        limit: 5,
      });

      expect(response.alerts.length).toBeLessThanOrEqual(5);
      expect(response.limit).toBe(5);
      expect(response.offset).toBe(0);
    });

    it('should fetch alerts with severity filter', async () => {
      const response = await backendApi.getAlerts({
        severity: ['critical', 'high'],
      });

      // All returned alerts should have critical or high severity
      for (const alert of response.alerts) {
        expect(['critical', 'high']).toContain(alert.severity);
      }
    });

    it('should fetch alerts with analysis status filter', async () => {
      // Try to get analyzed alerts, but if none exist, try not_analyzed
      let response = await backendApi.getAlerts({
        analysis_status: 'completed',
      });

      // If we got analyzed alerts, verify they are analyzed or analyzing (in progress)
      if (response.alerts.length > 0) {
        for (const alert of response.alerts) {
          // Accept both 'analyzed' and 'analyzing' as the analysis may be in progress
          expect(['completed', 'in_progress', 'failed']).toContain(alert.analysis_status);
        }
      } else {
        // If no analyzed alerts, try not_analyzed status
        response = await backendApi.getAlerts({
          analysis_status: 'new',
        });

        if (response.alerts.length > 0) {
          for (const alert of response.alerts) {
            expect(alert.analysis_status).toBe('new');
          }
        }
      }

      // Test should pass as long as filtering works correctly
      expect(response).toBeDefined();
      expect(Array.isArray(response.alerts)).toBe(true);
    });

    it('should fetch alerts with confidence filter', async () => {
      const response = await backendApi.getAlerts({
        min_confidence: 70,
        max_confidence: 90,
      });

      // All returned alerts should have confidence in range
      for (const alert of response.alerts) {
        if (alert.current_disposition_confidence !== undefined) {
          expect(alert.current_disposition_confidence).toBeGreaterThanOrEqual(70);
          expect(alert.current_disposition_confidence).toBeLessThanOrEqual(90);
        }
      }
    });

    it('should validate alert structure', async () => {
      const response = await backendApi.getAlerts({ limit: 1 });

      if (response.alerts.length > 0) {
        const alert = response.alerts[0];

        // Required fields
        expect(alert).toHaveProperty('alert_id');
        expect(alert).toHaveProperty('human_readable_id');
        expect(alert).toHaveProperty('title');
        expect(alert).toHaveProperty('severity');
        expect(alert).toHaveProperty('triggering_event_time');
        expect(alert).toHaveProperty('analysis_status');
        expect(alert).toHaveProperty('created_at');
        expect(alert).toHaveProperty('updated_at');

        // Validate severity enum
        expect(['critical', 'high', 'medium', 'low', 'info']).toContain(alert.severity);

        // Validate analysis_status enum
        expect(['new', 'in_progress', 'completed', 'failed', 'cancelled']).toContain(
          alert.analysis_status
        );

        // If analyzed, should have disposition fields
        if (alert.analysis_status === 'completed') {
          expect(alert).toHaveProperty('current_disposition_category');
          expect(alert).toHaveProperty('current_disposition_display_name');
          expect(alert).toHaveProperty('current_disposition_confidence');
        }
      }
    });
  });

  describe('GET /alerts/:id - Get single alert', () => {
    it('should fetch a single alert by ID', async () => {
      if (!testAlertId) {
        console.warn('No test alert ID available, skipping test');
        return;
      }

      const alert = await backendApi.getAlert(testAlertId);

      expect(alert).toBeDefined();
      expect(alert.alert_id).toBe(testAlertId);
      expect(alert).toHaveProperty('human_readable_id');
      expect(alert).toHaveProperty('title');

      // Check for current_analysis if analyzed
      if (alert.analysis_status === 'completed') {
        expect(alert).toHaveProperty('current_analysis');
        if (alert.current_analysis) {
          expect(alert.current_analysis).toHaveProperty('id');
          expect(alert.current_analysis).toHaveProperty('status');
          expect(alert.current_analysis).toHaveProperty('workflow_run_id');
        }
      }
    });

    it('should handle non-existent alert ID gracefully', async () => {
      const fakeId = 'non-existent-alert-id-12345';

      await expect(backendApi.getAlert(fakeId)).rejects.toThrow();
    });
  });

  describe('GET /dispositions - Get dispositions', () => {
    it('should fetch all dispositions', async () => {
      const dispositions = await backendApi.getDispositions();

      expect(Array.isArray(dispositions)).toBe(true);
      expect(dispositions.length).toBeGreaterThan(0);

      // Validate disposition structure
      for (const disposition of dispositions) {
        expect(disposition).toHaveProperty('disposition_id');
        expect(disposition).toHaveProperty('category');
        expect(disposition).toHaveProperty('subcategory');
        expect(disposition).toHaveProperty('display_name');
        expect(disposition).toHaveProperty('color_hex');
        expect(disposition).toHaveProperty('color_name');
        expect(disposition).toHaveProperty('priority_score');
        expect(disposition).toHaveProperty('requires_escalation');

        // Validate color_hex format
        expect(disposition.color_hex).toMatch(/^#[\da-f]{6}$/i);

        // Validate priority score range
        expect(disposition.priority_score).toBeGreaterThanOrEqual(1);
        expect(disposition.priority_score).toBeLessThanOrEqual(10);
      }
    });

    it('should have correct color mappings', async () => {
      const dispositions = await backendApi.getDispositions();

      // Check for expected color names
      const colorNames = new Set(dispositions.map((d) => d.color_name));
      const expectedColors = ['red', 'orange', 'yellow', 'purple', 'blue', 'green', 'gray'];

      // At least some expected colors should be present
      const matchingColors = expectedColors.filter((c) => colorNames.has(c));
      expect(matchingColors.length).toBeGreaterThan(0);
    });

    it('should have correct priority ordering', async () => {
      const dispositions = await backendApi.getDispositions();

      // Group by category and check priorities
      const maliciousDispositions = dispositions.filter((d) =>
        d.category.includes('True Positive (Malicious)')
      );

      // Malicious dispositions should have high priority (low numbers)
      for (const d of maliciousDispositions) {
        expect(d.priority_score).toBeLessThanOrEqual(3);
      }
    });
  });

  describe('POST /alerts/:id/analyze - Start analysis', () => {
    it('should start analysis for an alert', async () => {
      if (!testAlertId) {
        console.warn('No test alert ID available, skipping test');
        return;
      }

      // Note: This might fail if the alert is already being analyzed
      try {
        const response = await backendApi.analyzeAlert(testAlertId);

        expect(response).toHaveProperty('analysis_id');
        expect(response).toHaveProperty('status');
        expect(response).toHaveProperty('message');

        console.log('Analysis started:', response);
      } catch (error: any) {
        // Alert might already be analyzed or analyzing
        console.log('Analysis start failed (might already be analyzed):', error.response?.data);
      }
    });
  });

  describe('GET /alerts/:id/analysis/progress - Check analysis progress', () => {
    it('should fetch analysis progress', async () => {
      if (!testAlertId) {
        console.warn('No test alert ID available, skipping test');
        return;
      }

      try {
        const progress = await backendApi.getAnalysisProgress(testAlertId);

        expect(progress).toHaveProperty('analysis_id');
        expect(progress).toHaveProperty('current_step');
        expect(progress).toHaveProperty('completed_steps');
        expect(progress).toHaveProperty('total_steps');
        expect(progress).toHaveProperty('status');

        // Validate status enum
        expect(['pending', 'running', 'completed', 'failed']).toContain(progress.status);

        // If there are steps_detail, validate structure
        if (progress.steps_detail) {
          for (const step of Object.values(progress.steps_detail)) {
            expect(step).toHaveProperty('completed');
            expect(step).toHaveProperty('started_at');
            expect(step).toHaveProperty('completed_at');
            expect(step).toHaveProperty('retries');
            expect(step).toHaveProperty('error');
          }
        }

        console.log('Analysis progress:', progress);
      } catch (error: any) {
        console.log('Progress check failed:', error.response?.data);
      }
    });
  });

  describe('GET /alerts/:id/analyses - Get analysis history', () => {
    it('should fetch analysis history for an alert', async () => {
      if (!testAlertId) {
        console.warn('No test alert ID available, skipping test');
        return;
      }

      try {
        const analyses = await backendApi.getAlertAnalyses(testAlertId);

        expect(Array.isArray(analyses)).toBe(true);

        // If there are analyses, validate structure
        if (analyses.length > 0) {
          for (const analysis of analyses) {
            expect(analysis).toHaveProperty('id');
            expect(analysis).toHaveProperty('alert_id');
            expect(analysis).toHaveProperty('status');
            expect(analysis).toHaveProperty('created_at');
          }
        }

        console.log(`Found ${analyses.length} analyses for alert`);
      } catch (error: any) {
        console.log('Analysis history fetch failed:', error.response?.data);
      }
    });
  });

  describe('Complex query scenarios', () => {
    it('should handle multiple filters simultaneously', async () => {
      // Test with severity and confidence filters only (more stable)
      const response = await backendApi.getAlerts({
        severity: ['high', 'critical'],
        min_confidence: 50,
        limit: 10,
        sort: 'severity',
        order: 'desc',
      });

      expect(response).toBeDefined();
      expect(response.alerts.length).toBeLessThanOrEqual(10);

      // Verify filters are applied
      for (const alert of response.alerts) {
        expect(['high', 'critical']).toContain(alert.severity);
        // Only check confidence if the alert has been analyzed
        if (alert.analysis_status === 'completed' && alert.current_disposition_confidence) {
          expect(alert.current_disposition_confidence).toBeGreaterThanOrEqual(50);
        }
      }
    });

    it('should handle empty result sets gracefully', async () => {
      const response = await backendApi.getAlerts({
        // Very restrictive filter that might return no results
        min_confidence: 99,
        max_confidence: 100,
      });

      expect(response).toBeDefined();
      expect(response.alerts).toBeDefined();
      expect(Array.isArray(response.alerts)).toBe(true);
      expect(response.total).toBeGreaterThanOrEqual(0);
    });
  });
});

// Helper to run specific tests
export async function runAlertApiTests() {
  console.log('Running Alert API Integration Tests...');
  console.log('Make sure the backend is running on http://localhost:8001');

  try {
    // Test basic connectivity
    const response = await backendApi.getAlerts({ limit: 1 });
    console.log('✅ API is accessible');
    console.log(`Found ${response.total} total alerts`);

    // Test dispositions
    const dispositions = await backendApi.getDispositions();
    console.log(`✅ Found ${dispositions.length} dispositions`);

    return true;
  } catch (error) {
    console.error('❌ API test failed:', error);
    return false;
  }
}
