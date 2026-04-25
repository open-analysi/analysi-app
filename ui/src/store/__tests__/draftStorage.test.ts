import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import {
  localStorageAdapter,
  memoryStorageAdapter,
  createStorage,
  STORAGE_KEYS,
} from '../draftStorage';

const TEST_KEY = 'test-key';
const TEST_VALUE = 'test-value';

describe('localStorageAdapter', () => {
  const originalLocalStorage = globalThis.localStorage;

  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    Object.defineProperty(globalThis, 'localStorage', {
      value: originalLocalStorage,
      writable: true,
    });
  });

  it('getItem returns stored value', () => {
    localStorage.setItem(TEST_KEY, TEST_VALUE);
    expect(localStorageAdapter.getItem(TEST_KEY)).toBe(TEST_VALUE);
  });

  it('getItem returns null for missing key', () => {
    expect(localStorageAdapter.getItem('nonexistent')).toBeNull();
  });

  it('setItem stores a value', async () => {
    await localStorageAdapter.setItem(TEST_KEY, TEST_VALUE);
    expect(localStorage.getItem(TEST_KEY)).toBe(TEST_VALUE);
  });

  it('removeItem deletes a value', async () => {
    localStorage.setItem(TEST_KEY, TEST_VALUE);
    await localStorageAdapter.removeItem(TEST_KEY);
    expect(localStorage.getItem(TEST_KEY)).toBeNull();
  });

  it('getItem handles localStorage errors gracefully', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const mockStorage = {
      ...originalLocalStorage,
      getItem: () => {
        throw new Error('Storage full');
      },
    };
    Object.defineProperty(globalThis, 'localStorage', {
      value: mockStorage,
      writable: true,
    });

    expect(localStorageAdapter.getItem(TEST_KEY)).toBeNull();
    expect(warnSpy).toHaveBeenCalledWith('Failed to read from localStorage:', expect.any(Error));
    warnSpy.mockRestore();
  });

  it('setItem handles localStorage errors gracefully', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const mockStorage = {
      ...originalLocalStorage,
      setItem: () => {
        throw new Error('Storage full');
      },
    };
    Object.defineProperty(globalThis, 'localStorage', {
      value: mockStorage,
      writable: true,
    });

    // Should not throw
    await localStorageAdapter.setItem(TEST_KEY, TEST_VALUE);
    expect(warnSpy).toHaveBeenCalledWith('Failed to write to localStorage:', expect.any(Error));
    warnSpy.mockRestore();
  });

  it('removeItem handles localStorage errors gracefully', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const mockStorage = {
      ...originalLocalStorage,
      removeItem: () => {
        throw new Error('Storage error');
      },
    };
    Object.defineProperty(globalThis, 'localStorage', {
      value: mockStorage,
      writable: true,
    });

    // Should not throw
    await localStorageAdapter.removeItem(TEST_KEY);
    expect(warnSpy).toHaveBeenCalledWith('Failed to remove from localStorage:', expect.any(Error));
    warnSpy.mockRestore();
  });
});

describe('memoryStorageAdapter', () => {
  beforeEach(async () => {
    // Clean up any leftover state by removing known keys
    await memoryStorageAdapter.removeItem(TEST_KEY);
    await memoryStorageAdapter.removeItem('key1');
    await memoryStorageAdapter.removeItem('key2');
  });

  it('getItem returns null for missing key', () => {
    expect(memoryStorageAdapter.getItem('nonexistent')).toBeNull();
  });

  it('setItem and getItem round-trip correctly', async () => {
    await memoryStorageAdapter.setItem(TEST_KEY, '{"data": true}');
    expect(memoryStorageAdapter.getItem(TEST_KEY)).toBe('{"data": true}');
  });

  it('removeItem deletes a value', async () => {
    await memoryStorageAdapter.setItem(TEST_KEY, 'value');
    await memoryStorageAdapter.removeItem(TEST_KEY);
    expect(memoryStorageAdapter.getItem(TEST_KEY)).toBeNull();
  });

  it('handles multiple keys independently', async () => {
    await memoryStorageAdapter.setItem('key1', 'val1');
    await memoryStorageAdapter.setItem('key2', 'val2');

    expect(memoryStorageAdapter.getItem('key1')).toBe('val1');
    expect(memoryStorageAdapter.getItem('key2')).toBe('val2');

    await memoryStorageAdapter.removeItem('key1');
    expect(memoryStorageAdapter.getItem('key1')).toBeNull();
    expect(memoryStorageAdapter.getItem('key2')).toBe('val2');
  });
});

describe('createStorage', () => {
  it('returns a Zustand-compatible PersistStorage object', () => {
    const storage = createStorage(memoryStorageAdapter);
    expect(storage).toBeDefined();
    expect(storage).toHaveProperty('getItem');
    expect(storage).toHaveProperty('setItem');
    expect(storage).toHaveProperty('removeItem');
  });
});

describe('STORAGE_KEYS', () => {
  it('has expected storage key constants', () => {
    expect(STORAGE_KEYS.WORKFLOW_BUILDER).toBe('workflow-builder-draft');
    expect(STORAGE_KEYS.CY_EDITOR).toBe('cy-editor-drafts');
  });
});
