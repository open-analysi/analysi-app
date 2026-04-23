/* eslint-disable @typescript-eslint/restrict-template-expressions */
/**
 * Manual test runner for Alert API integration
 * Run with: npx tsx src/services/__tests__/testAlertsApi.ts
 */

import type { Disposition } from '../../types/alert';
import { backendApi } from '../backendApi';

// Color helpers
const colors = {
  reset: '\u001B[0m',
  bright: '\u001B[1m',
  green: '\u001B[32m',
  red: '\u001B[31m',
  yellow: '\u001B[33m',
  blue: '\u001B[34m',
  cyan: '\u001B[36m',
};

function log(message: string, color = colors.reset) {
  console.log(`${color}${message}${colors.reset}`);
}

function logSection(title: string) {
  console.log('');
  log(`${'='.repeat(60)}`, colors.cyan);
  log(title, colors.bright + colors.cyan);
  log(`${'='.repeat(60)}`, colors.cyan);
}

function logSuccess(message: string) {
  log(`✅ ${message}`, colors.green);
}

function logError(message: string) {
  log(`❌ ${message}`, colors.red);
}

function logInfo(message: string) {
  log(`ℹ️  ${message}`, colors.blue);
}

async function testAlertsList() {
  logSection('Testing: GET /alerts - List alerts');

  try {
    // Test 1: Basic fetch
    logInfo('Fetching alerts with default parameters...');
    const response1 = await backendApi.getAlerts();
    logSuccess(`Fetched ${response1.alerts.length} alerts (Total: ${response1.total})`);

    // Test 2: With pagination
    logInfo('Testing pagination (limit: 2, offset: 0)...');
    const response2 = await backendApi.getAlerts({ limit: 2, offset: 0 });
    logSuccess(`Pagination works: ${response2.alerts.length} alerts returned`);

    // Test 3: With severity filter
    logInfo('Testing severity filter (critical, high)...');
    const response3 = await backendApi.getAlerts({ severity: ['critical', 'high'] });
    const severities = new Set(response3.alerts.map((a) => a.severity));
    logSuccess(`Severity filter works: ${[...severities].join(', ')}`);

    // Test 4: With analysis status filter
    logInfo('Testing analysis_status filter (analyzed)...');
    const response4 = await backendApi.getAlerts({ analysis_status: 'completed' });
    const analyzedCount = response4.alerts.filter((a) => a.analysis_status === 'completed').length;
    logSuccess(`Found ${analyzedCount} analyzed alerts`);

    // Display sample alert structure
    if (response1.alerts.length > 0) {
      logInfo('Sample alert structure:');
      const sampleAlert = response1.alerts[0];
      console.log({
        alert_id: sampleAlert.alert_id,
        human_readable_id: sampleAlert.human_readable_id,
        title: sampleAlert.title,
        severity: sampleAlert.severity,
        analysis_status: sampleAlert.analysis_status,
        source_vendor: sampleAlert.source_vendor,
        disposition: sampleAlert.current_disposition_display_name,
        confidence: sampleAlert.current_disposition_confidence,
      });
    }

    return response1.alerts[0]?.alert_id || null;
  } catch (error) {
    logError(`Failed to fetch alerts: ${error}`);
    return null;
  }
}

async function testSingleAlert(alertId: string) {
  logSection(`Testing: GET /alerts/${alertId} - Get single alert`);

  try {
    logInfo(`Fetching alert ${alertId}...`);
    const alert = await backendApi.getAlert(alertId);
    logSuccess(`Fetched alert: ${alert.human_readable_id} - ${alert.title}`);

    // Display detailed info
    console.log({
      id: alert.alert_id,
      human_id: alert.human_readable_id,
      severity: alert.severity,
      analysis_status: alert.analysis_status,
      has_current_analysis: !!alert.current_analysis,
      disposition: alert.current_disposition_display_name,
      confidence: alert.current_disposition_confidence,
      evidences_count: alert.evidences?.length ?? 0,
      observables_count: alert.observables?.length ?? 0,
    });

    if (alert.current_analysis) {
      logInfo('Current analysis details:');
      console.log({
        analysis_id: alert.current_analysis.id,
        status: alert.current_analysis.status,
        workflow_run_id: alert.current_analysis.workflow_run_id,
        confidence: alert.current_analysis.confidence,
      });
    }

    return true;
  } catch (error) {
    logError(`Failed to fetch alert: ${error}`);
    return false;
  }
}

async function testDispositions() {
  logSection('Testing: GET /dispositions - Get all dispositions');

  try {
    logInfo('Fetching dispositions...');
    const dispositions = await backendApi.getDispositions();
    logSuccess(`Fetched ${dispositions.length} dispositions`);

    // Group by category
    const byCategory = dispositions.reduce(
      (acc, d) => {
        if (!acc[d.category]) acc[d.category] = [];
        acc[d.category].push(d);
        return acc;
      },
      {} as Record<string, Disposition[]>
    );

    logInfo('Dispositions by category:');
    for (const [category, items] of Object.entries(byCategory)) {
      console.log(`  ${category}: ${items.length} items`);
      for (const item of items) {
        console.log(
          `    - ${item.display_name} (${item.color_name}, priority: ${item.priority_score})`
        );
      }
    }

    // Check color distribution
    const colorCounts = dispositions.reduce(
      (acc, d) => {
        acc[d.color_name] = (acc[d.color_name] || 0) + 1;
        return acc;
      },
      {} as Record<string, number>
    );

    logInfo('Color distribution:');
    for (const [color, count] of Object.entries(colorCounts)) {
      console.log(`  ${color}: ${count} dispositions`);
    }

    return true;
  } catch (error) {
    logError(`Failed to fetch dispositions: ${error}`);
    return false;
  }
}

async function testAnalysisProgress(alertId: string) {
  logSection(`Testing: GET /alerts/${alertId}/analysis/progress`);

  try {
    logInfo('Fetching analysis progress...');
    const progress = await backendApi.getAnalysisProgress(alertId);
    logSuccess('Fetched analysis progress');

    console.log({
      analysis_id: progress.analysis_id,
      status: progress.status,
      current_step: progress.current_step,
      progress: `${progress.completed_steps}/${progress.total_steps}`,
    });

    if (progress.steps_detail) {
      logInfo('Steps detail:');
      for (const [step, details] of Object.entries(progress.steps_detail)) {
        console.log(`  ${step}:`, {
          completed: details.completed,
          retries: details.retries,
          error: details.error,
        });
      }
    }

    return true;
  } catch (error) {
    logError(`Failed to fetch analysis progress: ${error}`);
    return false;
  }
}

async function testAnalysisHistory(alertId: string) {
  logSection(`Testing: GET /alerts/${alertId}/analyses`);

  try {
    logInfo('Fetching analysis history...');
    const analyses = await backendApi.getAlertAnalyses(alertId);
    logSuccess(`Fetched ${analyses.length} analysis records`);

    if (analyses.length > 0) {
      logInfo('Analysis history:');
      analyses.forEach((analysis: any, index: number) => {
        console.log(`  ${index + 1}. Analysis ${analysis.id}:`, {
          status: analysis.status,
          created_at: analysis.created_at,
          workflow_run_id: analysis.workflow_run_id,
        });
      });
    }

    return true;
  } catch (error) {
    logError(`Failed to fetch analysis history: ${error}`);
    return false;
  }
}

async function testComplexQueries() {
  logSection('Testing: Complex queries with multiple filters');

  try {
    // Test 1: Multiple severity + analyzed
    logInfo('Testing: high/critical severity + analyzed status...');
    const response1 = await backendApi.getAlerts({
      severity: ['high', 'critical'],
      analysis_status: 'completed',
      limit: 5,
    });
    logSuccess(`Found ${response1.alerts.length} high/critical analyzed alerts`);

    // Test 2: Confidence range
    logInfo('Testing: confidence range 70-90...');
    const response2 = await backendApi.getAlerts({
      min_confidence: 70,
      max_confidence: 90,
      limit: 5,
    });
    const confidences = response2.alerts
      .map((a) => a.current_disposition_confidence)
      .filter((c): c is number => c != null);
    if (confidences.length > 0) {
      logSuccess(`Confidence range: ${Math.min(...confidences)} - ${Math.max(...confidences)}`);
    } else {
      logInfo('No alerts with confidence in this range');
    }

    // Test 3: Source product filter
    logInfo('Testing: source_product filter (crowdstrike)...');
    const response3 = await backendApi.getAlerts({
      source_product: 'crowdstrike',
      limit: 5,
    });
    const products = new Set(response3.alerts.map((a) => a.source_product).filter(Boolean));
    logSuccess(`Source products found: ${[...products].join(', ')}`);

    // Test 4: Sorting
    logInfo('Testing: sorting by severity (desc)...');
    const response4 = await backendApi.getAlerts({
      sort: 'severity',
      order: 'desc',
      limit: 5,
    });
    const severityOrder = response4.alerts.map((a) => a.severity);
    logSuccess(`Severity order: ${severityOrder.join(' → ')}`);

    return true;
  } catch (error) {
    logError(`Complex query failed: ${error}`);
    return false;
  }
}

async function runAllTests() {
  log('🚀 Starting Alert API Integration Tests', colors.bright + colors.green);
  log(`Testing against: http://localhost:8001`, colors.yellow);

  let allTestsPassed = true;

  try {
    // Test alerts list and get an alert ID for further tests
    const alertId = await testAlertsList();

    if (alertId) {
      // Test single alert fetch
      await testSingleAlert(alertId);

      // Test analysis endpoints
      await testAnalysisProgress(alertId);
      await testAnalysisHistory(alertId);
    } else {
      logInfo('No alerts available for single-alert tests');
    }

    // Test dispositions (doesn't need alert ID)
    await testDispositions();

    // Test complex queries
    await testComplexQueries();
  } catch (error) {
    logError(`Test suite failed: ${error}`);
    allTestsPassed = false;
  }

  logSection('Test Results');
  if (allTestsPassed) {
    logSuccess('All tests completed successfully! 🎉');
  } else {
    logError('Some tests failed. Please check the errors above.');
  }
}

// Run the tests
runAllTests().catch(console.error);
