import React, { useState, useEffect, useCallback, useRef } from 'react';

import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline';

import { useDebounce } from '../../hooks/useDebounce';

interface UnifiedSearchProps {
  onSearch: (query: string) => void;
  value: string;
  placeholder: string;
}

export const UnifiedSearch: React.FC<UnifiedSearchProps> = ({ onSearch, value, placeholder }) => {
  // Use a ref to track if this is the first render
  const isFirstRender = useRef(true);
  const [localSearchTerm, setLocalSearchTerm] = useState(value);
  const debouncedSearchTerm = useDebounce(localSearchTerm, 500); // 500ms debounce

  // Track if the current update is from internal state change
  const isInternalUpdate = useRef(false);

  // When debounced search term changes, call the search function
  useEffect(() => {
    // Skip first render to prevent initial double-fetch
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }

    // Set this flag to avoid the value sync effect from reacting
    isInternalUpdate.current = true;
    onSearch(debouncedSearchTerm);

    // Reset flag after a short delay
    const timer = setTimeout(() => {
      isInternalUpdate.current = false;
    }, 50);

    return () => clearTimeout(timer);
  }, [debouncedSearchTerm, onSearch]);

  // Only sync from external value if not currently handling an internal update
  useEffect(() => {
    if (!isInternalUpdate.current && value !== localSearchTerm) {
      setLocalSearchTerm(value);
    }
  }, [value, localSearchTerm]);

  const handleClear = useCallback(() => {
    isInternalUpdate.current = true;
    setLocalSearchTerm('');
    onSearch('');

    // Reset flag after a short delay
    setTimeout(() => {
      isInternalUpdate.current = false;
    }, 50);
  }, [onSearch]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    isInternalUpdate.current = true;
    setLocalSearchTerm(newValue);

    // Let the debounce effect handle the search call
  }, []);

  return (
    <div className="relative w-full">
      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
        <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
      </div>
      <input
        type="text"
        value={localSearchTerm}
        onChange={handleChange}
        className="block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 py-2 pl-10 pr-10 text-gray-900 dark:text-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-primary focus:border-primary text-sm leading-6"
        placeholder={placeholder}
        aria-label="Search"
      />
      <div className="absolute inset-y-0 right-0 flex items-center pr-3">
        {localSearchTerm && (
          <button
            onClick={handleClear}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            aria-label="Clear search"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        )}
      </div>
    </div>
  );
};
