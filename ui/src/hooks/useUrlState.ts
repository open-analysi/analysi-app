import { useCallback, useMemo } from 'react';

import { useSearchParams } from 'react-router';

/**
 * Hook for managing state in URL search parameters
 * Provides automatic synchronization with browser history and shareable URLs
 *
 * @param key - The URL parameter key
 * @param defaultValue - Default value when parameter is not present
 * @param options - Configuration options
 * @returns [value, setValue] tuple similar to useState
 *
 * @example
 * const [activeTab, setActiveTab] = useUrlState('tab', 'details');
 * const [page, setPage] = useUrlState('page', '1', { type: 'number' });
 */
export function useUrlState<T extends string | number | boolean>(
  key: string,
  defaultValue: T,
  options?: {
    replace?: boolean; // Whether to replace history entry (default: true)
    type?: 'string' | 'number' | 'boolean'; // Type coercion
  }
): [T, (value: T | ((prev: T) => T)) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const { replace = true, type } = options || {};

  // Parse value from URL
  const value = useMemo(() => {
    const rawValue = searchParams.get(key);

    if (rawValue === null) {
      return defaultValue;
    }

    // Type coercion based on defaultValue type or explicit type option
    const targetType = type || typeof defaultValue;

    switch (targetType) {
      case 'number': {
        const numValue = Number(rawValue);
        return (isNaN(numValue) ? defaultValue : numValue) as T;
      }

      case 'boolean': {
        return (rawValue === 'true') as T;
      }

      default: {
        return rawValue as T;
      }
    }
  }, [searchParams, key, defaultValue, type]);

  // Update value in URL
  const setValue = useCallback(
    (newValue: T | ((prev: T) => T)) => {
      setSearchParams(
        (prev) => {
          // Handle function updates like useState
          const actualValue =
            typeof newValue === 'function' ? (newValue as (prev: T) => T)(value) : newValue;

          // Convert value to string for URL
          const stringValue = String(actualValue);
          const defaultString = String(defaultValue);

          // Remove param if it's the default value (keeps URLs clean)
          if (stringValue === defaultString) {
            prev.delete(key);
          } else {
            prev.set(key, stringValue);
          }

          return prev;
        },
        { replace }
      );
    },
    [setSearchParams, key, defaultValue, value, replace]
  );

  return [value, setValue];
}

/**
 * Hook for managing multiple URL state values at once
 * Useful for complex forms or filters
 *
 * @example
 * const [filters, setFilters] = useUrlStateObject({
 *   status: 'all',
 *   priority: 'any',
 *   search: ''
 * });
 */
export function useUrlStateObject<T extends Record<string, string | number | boolean>>(
  defaults: T,
  options?: { replace?: boolean }
): [T, (updates: Partial<T>) => void, () => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const { replace = true } = options || {};

  // Parse all values from URL
  const values = useMemo(() => {
    const result = { ...defaults };

    for (const [key, defaultValue] of Object.entries(defaults)) {
      const rawValue = searchParams.get(key);
      if (rawValue !== null) {
        const targetType = typeof defaultValue;

        switch (targetType) {
          case 'number': {
            const numValue = Number(rawValue);
            result[key as keyof T] = (isNaN(numValue) ? defaultValue : numValue) as T[keyof T];
            break;
          }

          case 'boolean': {
            result[key as keyof T] = (rawValue === 'true') as T[keyof T];
            break;
          }

          default: {
            result[key as keyof T] = rawValue as T[keyof T];
          }
        }
      }
    }

    return result;
  }, [searchParams, defaults]);

  // Update multiple values at once
  const setValues = useCallback(
    (updates: Partial<T>) => {
      setSearchParams(
        (prev) => {
          for (const [key, value] of Object.entries(updates)) {
            const defaultValue = defaults[key];
            const stringValue = String(value);
            const defaultString = String(defaultValue);

            if (stringValue === defaultString) {
              prev.delete(key);
            } else {
              prev.set(key, stringValue);
            }
          }

          return prev;
        },
        { replace }
      );
    },
    [setSearchParams, defaults, replace]
  );

  // Clear all URL state (reset to defaults)
  const clearValues = useCallback(() => {
    setSearchParams(
      (prev) => {
        for (const key of Object.keys(defaults)) {
          prev.delete(key);
        }
        return prev;
      },
      { replace }
    );
  }, [setSearchParams, defaults, replace]);

  return [values, setValues, clearValues];
}
