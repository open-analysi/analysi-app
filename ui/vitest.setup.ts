import React from 'react';

import '@testing-library/jest-dom';
import * as matchers from '@testing-library/jest-dom/matchers';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, expect, vi } from 'vitest';

// Mock @axa-fr/react-oidc so tests that import components using OIDC hooks
// don't pull in the ServiceWorker registration or OIDC client internals.
vi.mock('@axa-fr/react-oidc', () => ({
  OidcProvider: ({ children }: { children: React.ReactNode }) => children,
  OidcSecure: ({ children }: { children: React.ReactNode }) => children,
  OidcUserStatus: {
    Unauthenticated: 'Unauthenticated',
    Loading: 'Loading user',
    Loaded: 'User loaded',
    LoadingError: 'Error loading user',
  },
  useOidc: () => ({
    login: vi.fn(),
    logout: vi.fn(),
    renewTokens: vi.fn(),
    isAuthenticated: true,
  }),
  useOidcUser: () => ({
    oidcUser: {
      sub: 'test-user',
      email: 'test@analysi.local',
      name: 'Test User',
      tenant_id: 'default',
      roles: ['owner'],
    },
    oidcUserLoadingState: 'User loaded',
    reloadOidcUser: vi.fn(),
  }),
  useOidcAccessToken: () => ({
    accessToken: 'mock-access-token',
    accessTokenPayload: {
      sub: 'test-user',
      tenant_id: 'default',
      roles: ['owner'],
      email: 'test@analysi.local',
    },
  }),
  useOidcIdToken: () => ({
    idToken: 'mock-id-token',
    idTokenPayload: { sub: 'test-user' },
  }),
}));

// Extend vitest's expect with jest-dom matchers
expect.extend(matchers as any);

// Mock ResizeObserver for HeadlessUI Dialog and other components
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

global.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

// Node ≥22 exposes a native `localStorage` global that shadows jsdom's
// implementation. When launched without `--localstorage-file=<path>`, the
// native object exists but its methods (`getItem`, `setItem`, `clear`, etc.)
// are undefined, which breaks any code that uses localStorage at runtime.
// Provide a minimal in-memory Storage polyfill so tests always get a
// working localStorage regardless of the Node version.
if (
  typeof globalThis.localStorage === 'undefined' ||
  typeof globalThis.localStorage.getItem !== 'function'
) {
  const store: Record<string, string> = {};
  globalThis.localStorage = {
    getItem: (key: string) => (key in store ? store[key] : null),
    setItem: (key: string, value: string) => {
      store[key] = String(value);
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      for (const key of Object.keys(store)) delete store[key];
    },
    get length() {
      return Object.keys(store).length;
    },
    key: (index: number) => Object.keys(store)[index] ?? null,
  } as Storage;
}

// Reset before each test to ensure clean state
beforeEach(() => {
  // Clear all mock implementations
  vi.clearAllMocks();
  // Reset all mock state
  vi.resetAllMocks();
});

// Automatically cleanup after each test
afterEach(() => {
  // Clean up React Testing Library
  cleanup();
  // Clear all mocks
  vi.clearAllMocks();
  // Reset modules to clear module-level state
  vi.resetModules();
  // Clear all timers if any were used
  vi.clearAllTimers();
  // Restore all mocks to original implementation
  vi.restoreAllMocks();
});
