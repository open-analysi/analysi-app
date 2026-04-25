import React, { useState, useEffect, useCallback, useRef } from 'react';

import { MagnifyingGlassIcon, XMarkIcon, InformationCircleIcon } from '@heroicons/react/24/outline';

import { useDebounce } from '../../hooks/useDebounce';

interface SearchBarProps {
  onSearch: (query: string) => void;
  value: string;
}

export const KnowledgeUnitSearch: React.FC<SearchBarProps> = ({ onSearch, value }) => {
  // Use a ref to track if this is the first render
  const isFirstRender = useRef(true);
  const [localSearchTerm, setLocalSearchTerm] = useState(value);
  const [showTooltip, setShowTooltip] = useState(false);
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
        className="block w-full rounded-md border-0 bg-dark-700 py-2 pl-10 pr-10 text-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-primary text-sm leading-6"
        placeholder="Search knowledge units by name, type, or description..."
        aria-label="Search knowledge units"
      />
      <div className="absolute inset-y-0 right-0 flex items-center pr-3 space-x-1">
        {localSearchTerm && (
          <button
            onClick={handleClear}
            className="text-gray-400 hover:text-gray-200"
            aria-label="Clear search"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        )}
        <button
          type="button"
          className="text-gray-400 hover:text-gray-300"
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
          onClick={() => setShowTooltip(!showTooltip)}
          aria-label="Search help"
        >
          <InformationCircleIcon className="h-5 w-5" />
        </button>

        {showTooltip && (
          <div className="absolute right-0 top-full mt-2 w-64 bg-dark-800 rounded-md shadow-lg z-10 p-3 text-sm text-gray-300 border border-dark-600">
            <p className="mb-2">
              <strong>Search includes:</strong>
            </p>
            <ul className="list-disc pl-4 space-y-1">
              <li>Knowledge unit names</li>
              <li>Descriptions</li>
              <li>Types (directive, table, tool, document)</li>
              <li>Status values</li>
              <li>Creator information</li>
              <li>Tags</li>
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};
