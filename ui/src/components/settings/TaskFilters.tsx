import React from 'react';

import { FunctionFilters, ScopeFilters, StatusFilters } from '../../store/taskStore';

interface TaskFiltersProps {
  functionFilters: FunctionFilters;
  scopeFilters: ScopeFilters;
  statusFilters: StatusFilters;
  setFunctionFilters: (filters: Partial<FunctionFilters>) => void;
  setScopeFilters: (filters: Partial<ScopeFilters>) => void;
  setStatusFilters: (filters: Partial<StatusFilters>) => void;
  resetFilters: () => void;
}

export const TaskFilters: React.FC<TaskFiltersProps> = ({
  functionFilters,
  scopeFilters,
  statusFilters,
  setFunctionFilters,
  setScopeFilters,
  setStatusFilters,
  resetFilters,
}) => {
  // Listen for custom reset event (when user clicks "Reset All Filters" in the empty table state)
  React.useEffect(() => {
    const handleResetFilters = () => {
      resetFilters();
    };

    window.addEventListener('resetFilters', handleResetFilters);
    return () => window.removeEventListener('resetFilters', handleResetFilters);
  }, [resetFilters]);

  // Compute whether "ALL" buttons should be active
  const allFunctionsSelected = Object.values(functionFilters).every(Boolean);
  const allScopesSelected = Object.values(scopeFilters).every(Boolean);
  const allStatusesSelected = Object.values(statusFilters).every(Boolean);

  // Handle toggling all filters in a category
  const toggleAllFunctions = () => {
    const newValue = !allFunctionsSelected;
    setFunctionFilters({
      summarization: newValue,
      data_conversion: newValue,
      extraction: newValue,
      decision_making: newValue,
      planning: newValue,
      visualization: newValue,
      search: newValue,
    });
  };

  const toggleAllScopes = () => {
    const newValue = !allScopesSelected;
    setScopeFilters({
      input: newValue,
      processing: newValue,
      output: newValue,
    });
  };

  const toggleAllStatuses = () => {
    const newValue = !allStatusesSelected;
    setStatusFilters({
      active: newValue,
      deprecated: newValue,
      experimental: newValue,
    });
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Filters</h3>
        <button
          onClick={resetFilters}
          className="text-xs text-gray-500 dark:text-gray-400 hover:text-primary dark:hover:text-primary-light"
        >
          Reset All
        </button>
      </div>

      <div className="mb-4">
        <div className="flex justify-between items-center mb-2">
          <h4 className="text-xs font-medium text-gray-600 dark:text-gray-400">Function</h4>
          <button
            className={`text-xs ${
              allFunctionsSelected
                ? 'text-primary dark:text-primary-light'
                : 'text-gray-500 dark:text-gray-400'
            }`}
            onClick={toggleAllFunctions}
          >
            {allFunctionsSelected ? 'Clear All' : 'Select All'}
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            className={`px-2 py-1 text-xs rounded ${
              functionFilters.summarization
                ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setFunctionFilters({ summarization: !functionFilters.summarization })}
          >
            Summarization
          </button>
          <button
            className={`px-2 py-1 text-xs rounded ${
              functionFilters.data_conversion
                ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() =>
              setFunctionFilters({ data_conversion: !functionFilters.data_conversion })
            }
          >
            Data Conversion
          </button>
          <button
            className={`px-2 py-1 text-xs rounded ${
              functionFilters.extraction
                ? 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setFunctionFilters({ extraction: !functionFilters.extraction })}
          >
            Extraction
          </button>
          <button
            className={`px-2 py-1 text-xs rounded ${
              functionFilters.decision_making
                ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() =>
              setFunctionFilters({ decision_making: !functionFilters.decision_making })
            }
          >
            Decision Making
          </button>
          <button
            className={`px-2 py-1 text-xs rounded ${
              functionFilters.planning
                ? 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setFunctionFilters({ planning: !functionFilters.planning })}
          >
            Planning
          </button>
          <button
            className={`px-2 py-1 text-xs rounded ${
              functionFilters.visualization
                ? 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setFunctionFilters({ visualization: !functionFilters.visualization })}
          >
            Visualization
          </button>
          <button
            className={`px-2 py-1 text-xs rounded ${
              functionFilters.search
                ? 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setFunctionFilters({ search: !functionFilters.search })}
          >
            Search
          </button>
        </div>
      </div>

      <div className="mb-4">
        <div className="flex justify-between items-center mb-2">
          <h4 className="text-xs font-medium text-gray-600 dark:text-gray-400">Scope</h4>
          <button
            className={`text-xs ${
              allScopesSelected
                ? 'text-primary dark:text-primary-light'
                : 'text-gray-500 dark:text-gray-400'
            }`}
            onClick={toggleAllScopes}
          >
            {allScopesSelected ? 'Clear All' : 'Select All'}
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            className={`px-2 py-1 text-xs rounded ${
              scopeFilters.input
                ? 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setScopeFilters({ input: !scopeFilters.input })}
          >
            Input
          </button>
          <button
            className={`px-2 py-1 text-xs rounded ${
              scopeFilters.processing
                ? 'bg-violet-100 text-violet-800 dark:bg-violet-900 dark:text-violet-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setScopeFilters({ processing: !scopeFilters.processing })}
          >
            Processing
          </button>
          <button
            className={`px-2 py-1 text-xs rounded ${
              scopeFilters.output
                ? 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setScopeFilters({ output: !scopeFilters.output })}
          >
            Output
          </button>
        </div>
      </div>

      <div>
        <div className="flex justify-between items-center mb-2">
          <h4 className="text-xs font-medium text-gray-600 dark:text-gray-400">Status</h4>
          <button
            className={`text-xs ${
              allStatusesSelected
                ? 'text-primary dark:text-primary-light'
                : 'text-gray-500 dark:text-gray-400'
            }`}
            onClick={toggleAllStatuses}
          >
            {allStatusesSelected ? 'Clear All' : 'Select All'}
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button
            className={`px-2 py-1 text-xs rounded ${
              statusFilters.active
                ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setStatusFilters({ active: !statusFilters.active })}
          >
            Active
          </button>
          <button
            className={`px-2 py-1 text-xs rounded ${
              statusFilters.deprecated
                ? 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setStatusFilters({ deprecated: !statusFilters.deprecated })}
          >
            Deprecated
          </button>
          <button
            className={`px-2 py-1 text-xs rounded ${
              statusFilters.experimental
                ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'
            }`}
            onClick={() => setStatusFilters({ experimental: !statusFilters.experimental })}
          >
            Experimental
          </button>
        </div>
      </div>
    </div>
  );
};
