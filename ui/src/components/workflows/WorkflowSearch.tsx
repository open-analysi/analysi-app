import React, { useState, useEffect } from 'react';

import { MagnifyingGlassIcon, XMarkIcon, ArrowPathIcon } from '@heroicons/react/24/outline';

import { useDebounce } from '../../hooks/useDebounce';

interface WorkflowSearchProps {
  searchTerm: string;
  onSearchChange: (term: string) => void;
  onRefresh: () => void;
  loading: boolean;
}

export const WorkflowSearch: React.FC<WorkflowSearchProps> = ({
  searchTerm,
  onSearchChange,
  onRefresh,
  loading,
}) => {
  const [localSearchTerm, setLocalSearchTerm] = useState(searchTerm);

  // Debounce the search to avoid too many API calls
  const debouncedSearchTerm = useDebounce(localSearchTerm, 300);

  // When the debounced value changes, call the parent's onSearchChange
  useEffect(() => {
    onSearchChange(debouncedSearchTerm);
  }, [debouncedSearchTerm, onSearchChange]);

  useEffect(() => {
    if (searchTerm !== localSearchTerm) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- equality-guarded
      setLocalSearchTerm(searchTerm);
    }
  }, [searchTerm]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setLocalSearchTerm(e.target.value);
  };

  const handleClear = () => {
    setLocalSearchTerm('');
  };

  return (
    <div className="flex items-center space-x-4">
      {/* Search Input */}
      <div className="flex-1 relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
        </div>

        <input
          type="text"
          className="block w-full pl-10 pr-10 py-2 border border-gray-300 dark:border-gray-700 rounded-md leading-5 bg-white dark:bg-gray-800 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-hidden focus:ring-primary dark:focus:ring-primary-light focus:border-primary dark:focus:border-primary-light text-sm"
          placeholder="Search workflows by name, description, creator..."
          value={localSearchTerm}
          onChange={handleChange}
        />

        {localSearchTerm && (
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center">
            <button
              type="button"
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              onClick={handleClear}
            >
              <XMarkIcon className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
        )}
      </div>

      {/* Refresh Button */}
      <button
        onClick={onRefresh}
        disabled={loading}
        className="inline-flex items-center px-3 py-2 border border-gray-300 dark:border-gray-700 shadow-xs text-sm leading-4 font-medium rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 focus:outline-hidden focus:ring-2 focus:ring-offset-2 focus:ring-primary dark:focus:ring-primary-light disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <ArrowPathIcon className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        <span className="ml-2">Refresh</span>
      </button>
    </div>
  );
};
