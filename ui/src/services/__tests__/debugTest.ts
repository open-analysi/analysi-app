// Debug script to test the complex query
import { backendApi } from '../backendApi';

async function debugComplexQuery() {
  console.log('Testing complex query with multiple filters...\n');

  try {
    const response = await backendApi.getAlerts({
      severity: ['high', 'critical'],
      analysis_status: 'completed',
      min_confidence: 50,
      limit: 10,
      sort: 'severity',
      order: 'desc',
    });

    console.log('Response received:');
    console.log('Total alerts:', response.total);
    console.log('Returned alerts:', response.alerts.length);

    console.log('\nAlert details:');
    for (const [index, alert] of response.alerts.entries()) {
      console.log(`\nAlert ${index + 1}:`);
      console.log('  ID:', alert.human_readable_id);
      console.log('  Severity:', alert.severity);
      console.log('  Analysis Status:', alert.analysis_status);
      console.log('  Confidence:', alert.current_disposition_confidence);
      console.log('  Title:', alert.title);

      // Check our test conditions
      const severityCheck = ['high', 'critical'].includes(alert.severity);
      const statusCheck = alert.analysis_status === 'completed';
      const confidenceCheck =
        !alert.current_disposition_confidence || alert.current_disposition_confidence >= 50;

      console.log('  ✓ Severity check:', severityCheck ? 'PASS' : 'FAIL');
      console.log('  ✓ Status check:', statusCheck ? 'PASS' : 'FAIL');
      console.log('  ✓ Confidence check:', confidenceCheck ? 'PASS' : 'FAIL');
    }
  } catch (error: any) {
    console.error('Error:', error.message);
    if (error.response) {
      console.error('Response status:', error.response.status);
      console.error('Response data:', error.response.data);
    }
  }
}

void debugComplexQuery();
