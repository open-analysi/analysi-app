import React, { useState, useEffect } from 'react';

import { MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline';

import { useDebounce } from '../../hooks/useDebounce';

interface TaskSearchProps {
  onSearch: (term: string) => void;
  value: string;
}

export const TaskSearch: React.FC<TaskSearchProps> = ({ onSearch, value }) => {
  const [searchTerm, setSearchTerm] = useState(value);

  // Debounce the search to avoid too many API calls
  const debouncedSearchTerm = useDebounce(searchTerm, 300);

  // When the debounced value changes, call the parent's onSearch
  useEffect(() => {
    onSearch(debouncedSearchTerm);
  }, [debouncedSearchTerm, onSearch]);

  // Update local state when parent value changes
  useEffect(() => {
    if (value !== searchTerm) {
      setSearchTerm(value);
    }
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(e.target.value);
  };

  const handleClear = () => {
    setSearchTerm('');
  };

  return (
    <div className="relative w-full">
      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
        <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
      </div>

      <input
        type="text"
        className="block w-full pl-10 pr-10 py-2 border border-gray-300 dark:border-gray-700 rounded-md leading-5 bg-white dark:bg-gray-800 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-hidden focus:ring-primary dark:focus:ring-primary-light focus:border-primary dark:focus:border-primary-light text-sm"
        placeholder="Search tasks by name, description, function..."
        value={searchTerm}
        onChange={handleChange}
      />

      {searchTerm && (
        <button
          type="button"
          className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          onClick={handleClear}
        >
          <XMarkIcon className="h-5 w-5" aria-hidden="true" />
        </button>
      )}
    </div>
  );
};
