import React, { useState, useEffect } from 'react';

import { Switch } from '@headlessui/react';
import { FunnelIcon, ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline';

interface TypeFilters {
  directive: boolean;
  table: boolean;
  tool: boolean;
  document: boolean;
}

interface StatusFilters {
  active: boolean;
  deprecated: boolean;
  experimental: boolean;
}

interface KnowledgeUnitFiltersProps {
  typeFilters: TypeFilters;
  setTypeFilters: (filters: Partial<TypeFilters>) => void;
  statusFilters: StatusFilters;
  setStatusFilters: (filters: Partial<StatusFilters>) => void;
  resetFilters: () => void;
}

const FilterGroup: React.FC<{
  title: string;
  children: React.ReactNode;
}> = ({ title, children }) => {
  return (
    <div className="p-4 bg-dark-800 rounded-sm">
      <h3 className="text-sm font-semibold text-gray-300 mb-2">{title}</h3>
      <div className="space-y-2">{children}</div>
    </div>
  );
};

const FilterSwitch: React.FC<{
  label: string;
  enabled: boolean;
  onChange: () => void;
}> = ({ label, enabled, onChange }) => (
  <div className="flex items-center justify-between">
    <span className="text-sm text-gray-400">{label}</span>
    <Switch
      checked={enabled}
      onChange={onChange}
      className={`${
        enabled ? 'bg-primary' : 'bg-dark-700'
      } relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-hidden`}
    >
      <span
        className={`${
          enabled ? 'translate-x-5' : 'translate-x-1'
        } inline-block h-3 w-3 transform rounded-full bg-white transition-transform`}
      />
    </Switch>
  </div>
);

export const KnowledgeUnitFilters: React.FC<KnowledgeUnitFiltersProps> = ({
  typeFilters,
  setTypeFilters,
  statusFilters,
  setStatusFilters,
  resetFilters,
}) => {
  const [showFilters, setShowFilters] = useState(false);

  // Listen for the resetFilters event
  useEffect(() => {
    const handleResetFilters = () => {
      resetFilters();
      // Also show the filters after reset
      setShowFilters(true);
    };

    window.addEventListener('resetFilters', handleResetFilters);

    return () => {
      window.removeEventListener('resetFilters', handleResetFilters);
    };
  }, [resetFilters]);

  // Get count of active filters (filters that are turned off)
  // We only count if at least one filter is still selected, otherwise we don't show the count
  // because it's misleading to show "7" when they've turned off all filters
  const typeFilterCount = Object.values(typeFilters).filter((value) => !value).length;
  const statusFilterCount = Object.values(statusFilters).filter((value) => !value).length;

  // Only count filters if at least one type and one status is still selected
  const anyTypeSelected = Object.values(typeFilters).some(Boolean);
  const anyStatusSelected = Object.values(statusFilters).some(Boolean);

  // Count how many filters are active
  const activeFilterCount = typeFilterCount + statusFilterCount;

  // Show count only if at least one filter is active and at least one option is still selected
  const showFilterCount = activeFilterCount > 0 && (anyTypeSelected || anyStatusSelected);

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="flex items-center text-gray-300 hover:text-gray-100 focus:outline-hidden"
            aria-expanded={showFilters}
            aria-controls="filters-panel"
          >
            <FunnelIcon className="h-5 w-5 text-gray-400 mr-2" />
            <h2 className="text-lg font-semibold text-gray-300">Filters</h2>
            {showFilterCount && (
              <span className="ml-2 px-2 py-0.5 bg-primary text-white text-xs rounded-full">
                {activeFilterCount}
              </span>
            )}
            {showFilters ? (
              <ChevronUpIcon className="ml-2 h-4 w-4" />
            ) : (
              <ChevronDownIcon className="ml-2 h-4 w-4" />
            )}
          </button>
        </div>

        <button
          onClick={resetFilters}
          className="px-3 py-1 text-sm bg-dark-700 hover:bg-dark-600 text-gray-300 rounded-sm"
        >
          Reset All Filters
        </button>
      </div>

      {showFilters && (
        <div
          id="filters-panel"
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 animate-fadeIn"
        >
          <FilterGroup title="Type">
            <FilterSwitch
              label="Directive"
              enabled={typeFilters.directive}
              onChange={() => setTypeFilters({ directive: !typeFilters.directive })}
            />
            <FilterSwitch
              label="Table"
              enabled={typeFilters.table}
              onChange={() => setTypeFilters({ table: !typeFilters.table })}
            />
            <FilterSwitch
              label="Tool"
              enabled={typeFilters.tool}
              onChange={() => setTypeFilters({ tool: !typeFilters.tool })}
            />
            <FilterSwitch
              label="Document"
              enabled={typeFilters.document}
              onChange={() => setTypeFilters({ document: !typeFilters.document })}
            />
          </FilterGroup>

          <FilterGroup title="Status">
            <FilterSwitch
              label="Active"
              enabled={statusFilters.active}
              onChange={() => setStatusFilters({ active: !statusFilters.active })}
            />
            <FilterSwitch
              label="Deprecated"
              enabled={statusFilters.deprecated}
              onChange={() => setStatusFilters({ deprecated: !statusFilters.deprecated })}
            />
            <FilterSwitch
              label="Experimental"
              enabled={statusFilters.experimental}
              onChange={() => setStatusFilters({ experimental: !statusFilters.experimental })}
            />
          </FilterGroup>
        </div>
      )}
    </div>
  );
};
