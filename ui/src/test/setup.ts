import '@testing-library/jest-dom';
import * as matchers from '@testing-library/jest-dom/matchers';
import { cleanup } from '@testing-library/react';
import { expect, afterEach, vi } from 'vitest';

// Extend vitest's expect with jest-dom matchers
expect.extend(matchers as any);

// Clean up after each test
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Add window.fetch if needed
global.fetch = vi.fn();

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Add any other global mocks needed
