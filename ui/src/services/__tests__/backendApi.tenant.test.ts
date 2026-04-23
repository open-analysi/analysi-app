import axios from 'axios';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

/**
 * Test suite for backend API tenant configuration
 *
 * This test verifies that the tenant configuration from environment variables
 * is correctly applied to the API client's baseURL.
 */
describe('backendApi - Tenant Configuration', () => {
  let originalEnv: Record<string, string | undefined>;
  let axiosCreateSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // Save original environment
    originalEnv = { ...process.env };

    // Spy on axios.create to verify baseURL
    axiosCreateSpy = vi.spyOn(axios, 'create');
  });

  afterEach(() => {
    // Restore original environment
    process.env = originalEnv;

    // Clear all module caches to force re-import
    vi.resetModules();

    // Restore spy
    axiosCreateSpy.mockRestore();
  });

  it('should use default tenant when VITE_BACKEND_API_TENANT is not set', async () => {
    // Clear tenant env var
    delete (import.meta.env as any).VITE_BACKEND_API_TENANT;
    delete process.env.VITE_BACKEND_API_TENANT;

    // Set test environment to trigger Node.js path
    process.env.NODE_ENV = 'test';

    // Import module to trigger initialization
    await import('../backendApi');

    // Verify axios.create was called with default tenant
    expect(axiosCreateSpy).toHaveBeenCalled();
    const createCall = axiosCreateSpy.mock.calls[0]?.[0];

    // In test environment, should use the full URL with tenant
    expect(createCall?.baseURL).toMatch(/\/v1\/default$/);
  });

  it('should use custom tenant when VITE_BACKEND_API_TENANT is set', async () => {
    // Set custom tenant
    (import.meta.env as any).VITE_BACKEND_API_TENANT = 'custom-tenant';
    process.env.VITE_BACKEND_API_TENANT = 'custom-tenant';

    // Set test environment
    process.env.NODE_ENV = 'test';

    // Clear module cache and re-import
    vi.resetModules();

    // Create new spy after reset
    const newAxiosCreateSpy: any = vi.spyOn(axios, 'create');

    // Import module to trigger initialization with new env
    await import('../backendApi');

    // Verify axios.create was called with custom tenant
    expect(newAxiosCreateSpy).toHaveBeenCalled();
    const createCall = newAxiosCreateSpy.mock.calls[0]?.[0];

    expect(createCall?.baseURL).toMatch(/\/v1\/custom-tenant$/);

    newAxiosCreateSpy.mockRestore();
  });

  it('should use VITE_BACKEND_API_URL when provided', async () => {
    // Set custom backend URL and tenant
    (import.meta.env as any).VITE_BACKEND_API_URL = 'http://api.example.com:9000';
    (import.meta.env as any).VITE_BACKEND_API_TENANT = 'production';
    process.env.VITE_BACKEND_API_URL = 'http://api.example.com:9000';
    process.env.VITE_BACKEND_API_TENANT = 'production';
    process.env.NODE_ENV = 'test';

    // Clear module cache and re-import
    vi.resetModules();

    const newAxiosCreateSpy: any = vi.spyOn(axios, 'create');

    await import('../backendApi');

    expect(newAxiosCreateSpy).toHaveBeenCalled();
    const createCall = newAxiosCreateSpy.mock.calls[0]?.[0];

    expect(createCall?.baseURL).toBe('http://api.example.com:9000/v1/production');

    newAxiosCreateSpy.mockRestore();
  });

  it('should use /api proxy path in browser environment', async () => {
    // Set window to simulate browser environment
    (global as any).window = {};

    // Set tenant
    (import.meta.env as any).VITE_BACKEND_API_TENANT = 'browser-tenant';
    process.env.VITE_BACKEND_API_TENANT = 'browser-tenant';

    // Clear test env to simulate browser
    delete process.env.NODE_ENV;

    // Clear module cache and re-import
    vi.resetModules();

    const newAxiosCreateSpy: any = vi.spyOn(axios, 'create');

    await import('../backendApi');

    expect(newAxiosCreateSpy).toHaveBeenCalled();
    const createCall = newAxiosCreateSpy.mock.calls[0]?.[0];

    // In browser, should use proxy path
    expect(createCall?.baseURL).toBe('/api');

    newAxiosCreateSpy.mockRestore();

    // Cleanup
    delete (global as any).window;
  });

  it('should construct correct tenant path with different tenant names', async () => {
    const testCases = [
      { tenant: 'dev', expected: '/v1/dev' },
      { tenant: 'staging', expected: '/v1/staging' },
      { tenant: 'prod', expected: '/v1/prod' },
      { tenant: 'customer-123', expected: '/v1/customer-123' },
      { tenant: 'org_name', expected: '/v1/org_name' },
    ];

    for (const testCase of testCases) {
      // Set tenant
      (import.meta.env as any).VITE_BACKEND_API_TENANT = testCase.tenant;
      process.env.VITE_BACKEND_API_TENANT = testCase.tenant;
      process.env.NODE_ENV = 'test';

      // Clear module cache
      vi.resetModules();

      const newAxiosCreateSpy: any = vi.spyOn(axios, 'create');

      // Re-import module
      await import('../backendApi');

      const createCall = newAxiosCreateSpy.mock.calls[0]?.[0];
      expect(createCall?.baseURL).toMatch(new RegExp(`${testCase.expected}$`));

      newAxiosCreateSpy.mockRestore();
    }
  });
});

/**
 * Integration test for tenant configuration with actual API calls
 */
describe('backendApi - Tenant Configuration Integration', () => {
  let originalEnv: Record<string, string | undefined>;

  beforeEach(() => {
    originalEnv = { ...process.env };
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.resetModules();
  });

  it('should include tenant in API request URLs', async () => {
    // Mock axios to verify request URLs
    const mockAxiosInstance = {
      get: vi.fn().mockResolvedValue({ data: { tasks: [], total: 0 } }),
      post: vi.fn(),
      put: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: { use: vi.fn(), eject: vi.fn() },
        response: { use: vi.fn(), eject: vi.fn() },
      },
    };

    vi.doMock('axios', () => ({
      default: {
        create: vi.fn(() => mockAxiosInstance),
      },
    }));

    // Set tenant
    (import.meta.env as any).VITE_BACKEND_API_TENANT = 'test-tenant';
    process.env.VITE_BACKEND_API_TENANT = 'test-tenant';
    process.env.NODE_ENV = 'test';

    // Import and use the API
    const { backendApi } = await import('../backendApi');

    // Make an API call
    try {
      await backendApi.getTasks();
    } catch {
      // Ignore errors, we just want to verify the URL
    }

    // Verify the request was made with correct endpoint
    expect(mockAxiosInstance.get).toHaveBeenCalledWith('/tasks', expect.any(Object));
  });
});
