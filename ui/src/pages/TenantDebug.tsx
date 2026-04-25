import { useState } from 'react';

import { backendApi } from '../services/backendApi';
import { useAuthStore } from '../store/authStore';

interface EnvInfo {
  VITE_BACKEND_API_URL: string;
}

interface TestResultSuccess {
  success: true;
  data: unknown;
  timestamp: string;
}

interface TestResultError {
  success: false;
  error: string;
  response?: unknown;
  status?: number;
  timestamp: string;
}

type TestResult = TestResultSuccess | TestResultError;

/**
 * Diagnostic page to verify tenant configuration
 */
export default function TenantDebug() {
  const tenantId = useAuthStore((s) => s.tenant_id);

  // Get environment info directly from import.meta.env (static data)
  const envInfo: EnvInfo = {
    VITE_BACKEND_API_URL: (import.meta.env.VITE_BACKEND_API_URL as string) || '',
  };

  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [loading, setLoading] = useState(false);

  const testConnection = () => {
    setLoading(true);
    backendApi
      .getTasks({ limit: 1 })
      .then((response) => {
        setTestResult({
          success: true,
          data: response,
          timestamp: new Date().toISOString(),
        });
      })
      .catch((error: unknown) => {
        const err = error as { message?: string; response?: { data?: unknown; status?: number } };
        setTestResult({
          success: false,
          error: err.message || 'Unknown error',
          response: err.response?.data,
          status: err.response?.status,
          timestamp: new Date().toISOString(),
        });
      })
      .finally(() => {
        setLoading(false);
      });
  };

  return (
    <div className="p-8 bg-gray-50 min-h-screen">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Tenant Configuration Debug</h1>

        {/* Environment Variables */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Environment Variables (Browser)</h2>
          <div className="font-mono text-sm space-y-2">
            <div>
              <span className="text-gray-600">VITE_BACKEND_API_URL:</span>{' '}
              <span className="font-bold">{envInfo?.VITE_BACKEND_API_URL || '(not set)'}</span>
            </div>
            <div>
              <span className="text-gray-600">Tenant (from JWT):</span>{' '}
              <span className="font-bold text-blue-600">{tenantId || '(not resolved yet)'}</span>
            </div>
          </div>
        </div>

        {/* Expected Behavior */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Expected Behavior</h2>
          <div className="font-mono text-sm space-y-2">
            <div className="text-gray-600">Browser requests to:</div>
            <div className="pl-4 text-blue-600 font-bold">/api/tasks</div>
            <div className="text-gray-600 mt-2">Should be proxied to:</div>
            <div className="pl-4 text-green-600 font-bold">
              {envInfo?.VITE_BACKEND_API_URL || 'http://localhost:8001'}/v1/
              {tenantId || 'default'}/tasks
            </div>
          </div>
        </div>

        {/* Test Connection */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Test Connection</h2>
          <button
            onClick={testConnection}
            disabled={loading}
            className="bg-blue-600 text-white px-6 py-2 rounded-sm hover:bg-blue-700 disabled:bg-gray-400"
          >
            {loading ? 'Testing...' : 'Test API Connection'}
          </button>

          {testResult && (
            <div className="mt-4">
              <div
                className={`p-4 rounded-sm ${testResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}
              >
                <div className="font-semibold mb-2">
                  {testResult.success ? '✅ Success' : '❌ Failed'}
                </div>
                <pre className="text-xs overflow-auto max-h-96 bg-gray-100 p-3 rounded-sm">
                  {JSON.stringify(testResult, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* Instructions */}
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Troubleshooting</h2>
          <ol className="list-decimal list-inside space-y-2 text-sm">
            <li>
              Check that <code className="bg-gray-200 px-1 rounded-sm">.env</code> has the correct
              tenant
            </li>
            <li>
              Restart the dev server:{' '}
              <code className="bg-gray-200 px-1 rounded-sm">npm run dev</code>
            </li>
            <li>
              <strong>Hard refresh</strong> the browser:{' '}
              <code className="bg-gray-200 px-1 rounded-sm">Cmd+Shift+R</code> (Mac) or{' '}
              <code className="bg-gray-200 px-1 rounded-sm">Ctrl+Shift+R</code> (Windows)
            </li>
            <li>Check browser console for tenant logs</li>
            <li>Check Network tab to see actual request URLs</li>
            <li>
              Open browser DevTools → Network → find a request to{' '}
              <code className="bg-gray-200 px-1 rounded-sm">/api/tasks</code> → check headers
            </li>
          </ol>
        </div>
      </div>
    </div>
  );
}
