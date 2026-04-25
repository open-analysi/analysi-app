/**
 * Draft Storage Adapter
 *
 * Provides a pluggable storage layer for persisting drafts.
 * Currently uses localStorage, but can easily be swapped to a REST API.
 *
 * To swap to REST API:
 * 1. Implement the StorageAdapter interface with API calls
 * 2. Replace localStorageAdapter with your apiStorageAdapter
 *
 * Example API implementation:
 * ```typescript
 * const apiStorageAdapter: StorageAdapter = {
 *   getItem: async (name) => {
 *     const response = await backendApi.getDraft(name);
 *     return response ? JSON.stringify(response) : null;
 *   },
 *   setItem: async (name, value) => {
 *     await backendApi.saveDraft(name, JSON.parse(value));
 *   },
 *   removeItem: async (name) => {
 *     await backendApi.deleteDraft(name);
 *   },
 * };
 * ```
 */

import { createJSONStorage } from 'zustand/middleware';
import type { StateStorage, PersistStorage } from 'zustand/middleware';

/**
 * Storage adapter interface - matches Zustand's StateStorage
 */
export interface StorageAdapter extends StateStorage {
  getItem: (name: string) => string | null | Promise<string | null>;
  setItem: (name: string, value: string) => void | Promise<void>;
  removeItem: (name: string) => void | Promise<void>;
}

/**
 * localStorage adapter (current implementation)
 */
export const localStorageAdapter: StorageAdapter = {
  getItem: (name: string): string | null => {
    try {
      return localStorage.getItem(name);
    } catch (error) {
      console.warn('Failed to read from localStorage:', error);
      return null;
    }
  },

  setItem: (name: string, value: string): void => {
    try {
      localStorage.setItem(name, value);
    } catch (error) {
      console.warn('Failed to write to localStorage:', error);
    }
  },

  removeItem: (name: string): void => {
    try {
      localStorage.removeItem(name);
    } catch (error) {
      console.warn('Failed to remove from localStorage:', error);
    }
  },
};

/**
 * In-memory adapter (useful for testing or when localStorage is unavailable)
 */
const memoryStore: Record<string, string> = {};

export const memoryStorageAdapter: StorageAdapter = {
  getItem: (name: string): string | null => {
    return memoryStore[name] ?? null;
  },

  setItem: (name: string, value: string): void => {
    memoryStore[name] = value;
  },

  removeItem: (name: string): void => {
    delete memoryStore[name];
  },
};

/**
 * Default storage adapter - uses localStorage
 * Change this to switch storage backends globally
 */
export const draftStorage: StorageAdapter = localStorageAdapter;

/**
 * Create Zustand-compatible storage from our adapter
 * Uses createJSONStorage to properly handle serialization
 */
export function createStorage<T>(
  adapter: StorageAdapter = draftStorage
): PersistStorage<T> | undefined {
  return createJSONStorage(() => adapter);
}

/**
 * Storage keys for different draft types
 */
export const STORAGE_KEYS = {
  WORKFLOW_BUILDER: 'workflow-builder-draft',
  CY_EDITOR: 'cy-editor-drafts',
} as const;
