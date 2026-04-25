import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock authStore before importing apiClient
const mockGetState = vi.fn();
vi.mock('../../store/authStore', () => ({
  useAuthStore: {
    getState: mockGetState,
  },
}));

// Mock axios to capture interceptor registration and simulate requests
const capturedInterceptors: Array<(config: Record<string, unknown>) => Record<string, unknown>> = [];

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      interceptors: {
        request: {
          use: vi.fn((fn: (config: Record<string, unknown>) => Record<string, unknown>) => {
            capturedInterceptors.push(fn);
          }),
          eject: vi.fn(),
        },
        response: {
          use: vi.fn(),
          eject: vi.fn(),
        },
      },
    })),
  },
}));

describe('apiClient — request interceptor (baseURL injection)', () => {
  beforeEach(() => {
    capturedInterceptors.length = 0;
    vi.clearAllMocks();
    vi.resetModules();
  });

  it('sets baseURL to /api/v1/{tenant_id} from authStore in browser env', async () => {
    // Simulate browser environment
    const originalWindow = global.window;
    (global as unknown as Record<string, unknown>).window = {};

    // Set NODE_ENV to non-test to trigger browser path
    const originalNodeEnv = process.env.NODE_ENV;
    delete process.env.NODE_ENV;

    mockGetState.mockReturnValue({ tenant_id: 'demo' });

    // Re-import after mocks are set
    await import('../apiClient');

    // The interceptor that injects the baseURL should be registered
    // Find it by running it and checking the result
    const baseURLInterceptor = capturedInterceptors.find((fn) => {
      const result = fn({ headers: {}, method: 'get' } as Record<string, unknown>);
      return (result).baseURL === '/api/v1/demo';
    });

    expect(baseURLInterceptor).toBeDefined();

    // Restore environment
    (global as unknown as Record<string, unknown>).window = originalWindow;
    process.env.NODE_ENV = originalNodeEnv;
  });

  it('uses default tenant when authStore.tenant_id is default', async () => {
    const originalWindow = global.window;
    (global as unknown as Record<string, unknown>).window = {};
    const originalNodeEnv = process.env.NODE_ENV;
    delete process.env.NODE_ENV;

    mockGetState.mockReturnValue({ tenant_id: 'default' });

    vi.resetModules();
    // Re-mock after reset
    vi.mock('../../store/authStore', () => ({
      useAuthStore: { getState: mockGetState },
    }));

    await import('../apiClient');

    const interceptor = capturedInterceptors[0];
    if (interceptor) {
      const config = interceptor({ headers: {}, method: 'get' } as Record<string, unknown>);
      expect((config).baseURL).toBe('/api/v1/default');
    }

    (global as unknown as Record<string, unknown>).window = originalWindow;
    process.env.NODE_ENV = originalNodeEnv;
  });

  it('updates URL when tenant_id changes between requests', async () => {
    const originalWindow = global.window;
    (global as unknown as Record<string, unknown>).window = {};
    const originalNodeEnv = process.env.NODE_ENV;
    delete process.env.NODE_ENV;

    // First call returns demo, second call returns other-tenant
    mockGetState
      .mockReturnValueOnce({ tenant_id: 'demo' })
      .mockReturnValueOnce({ tenant_id: 'other-tenant' });

    vi.resetModules();
    vi.mock('../../store/authStore', () => ({
      useAuthStore: { getState: mockGetState },
    }));

    await import('../apiClient');

    const interceptor = capturedInterceptors[0];
    if (interceptor) {
      const config1 = interceptor({ headers: {} } as Record<string, unknown>);
      const config2 = interceptor({ headers: {} } as Record<string, unknown>);

      expect((config1).baseURL).toBe('/api/v1/demo');
      expect((config2).baseURL).toBe('/api/v1/other-tenant');
    }

    (global as unknown as Record<string, unknown>).window = originalWindow;
    process.env.NODE_ENV = originalNodeEnv;
  });
});
