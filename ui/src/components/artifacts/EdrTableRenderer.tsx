import React, { useState, useMemo } from 'react';

import {
  MagnifyingGlassIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ExclamationTriangleIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';

interface EdrTableRendererProps {
  data: Record<string, unknown> | unknown[];
  subcategory?: string;
  isSummary?: boolean;
}

interface SortConfig {
  key: string;
  direction: 'asc' | 'desc';
}

interface RecordType {
  [key: string]: unknown;
}

// Safe stringification for cell values that may be primitives, null, or
// nested objects/arrays. Object cells fall back to JSON so sort comparisons
// and search filters operate on a real string instead of "[object Object]".
const stringifyCell = (value: unknown): string => {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  // Symbols, functions, and circular structures fall back to an empty string
  // rather than throwing — preserves the prior best-effort behaviour.
  try {
    return JSON.stringify(value) ?? '';
  } catch {
    return '';
  }
};

const formatKey = (key: string): string => {
  return key
    .replaceAll('_', ' ')
    .replaceAll(/([A-Z])/g, ' $1')
    .toLowerCase()
    .split(' ')
    .map((word: string) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
};

const renderValue = (value: unknown): React.JSX.Element => {
  if (value === undefined) return <span className="text-gray-400">undefined</span>;
  if (value === null) return <span className="text-gray-400">null</span>;

  if (typeof value === 'object') {
    // The "[Expand]" button was never wired up. Preserve the count display
    // but drop the dead handler so clicking is a no-op-by-omission rather
    // than a no-op-by-stub.
    if (Array.isArray(value)) {
      return <span className="text-gray-300">{value.length} items</span>;
    }
    return <span className="text-gray-300">{Object.keys(value).length} fields</span>;
  }

  if (typeof value === 'boolean') {
    return (
      <span
        className={`px-2 py-1 rounded-sm text-xs ${value ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}
      >
        {value.toString()}
      </span>
    );
  }

  if (typeof value === 'number') {
    return <span className="text-blue-400">{value}</span>;
  }

  return <span className="text-gray-200">{stringifyCell(value)}</span>;
};

export const EdrTableRenderer: React.FC<EdrTableRendererProps> = ({
  data,
  subcategory,
  isSummary,
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [sortConfig, setSortConfig] = useState<SortConfig | undefined>();

  // Convert data to array of records if it's not already
  const records = useMemo(() => {
    if (!data) return [];
    if (Array.isArray(data)) return data;
    return [data];
  }, [data]);

  // Get all unique keys from the records
  const allKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const record of records) {
      // typeof null === 'object', so an explicit null check is required —
      // checking !== undefined here is always true and lets nulls slip through.
      if (typeof record === 'object' && record !== null) {
        for (const key of Object.keys(record as RecordType)) keys.add(key);
      }
    }
    return [...keys];
  }, [records]);

  // Filter and sort the records
  const filteredAndSortedRecords = useMemo(() => {
    let result = [...records];

    // Apply search filter
    if (searchTerm) {
      const searchLower = searchTerm.toLowerCase();
      result = result.filter((record) => {
        if (typeof record !== 'object' || record === null) return false;
        return Object.entries(record as RecordType).some(([key, value]) => {
          const keyMatch = key.toLowerCase().includes(searchLower);
          const valueMatch = stringifyCell(value).toLowerCase().includes(searchLower);
          return keyMatch || valueMatch;
        });
      });
    }

    // Apply sorting
    if (sortConfig) {
      result.sort((a, b) => {
        if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return 0;

        const aValue = (a as RecordType)[sortConfig.key];
        const bValue = (b as RecordType)[sortConfig.key];

        if (aValue === bValue) return 0;
        if (aValue === undefined) return 1;
        if (bValue === undefined) return -1;

        const comparison = stringifyCell(aValue).localeCompare(stringifyCell(bValue));
        return sortConfig.direction === 'asc' ? comparison : -comparison;
      });
    }

    return result;
  }, [records, searchTerm, sortConfig]);

  const handleSort = (key: string) => {
    setSortConfig((current) => {
      if (current?.key === key) {
        return {
          key,
          direction: current.direction === 'asc' ? 'desc' : 'asc',
        };
      }
      return { key, direction: 'asc' };
    });
  };

  // Check if data is available
  if (!data || (Array.isArray(data) && data.length === 0)) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-400">
        <ExclamationTriangleIcon className="w-12 h-12 mb-4" />
        <p className="text-lg font-medium">No Data Available</p>
        <p className="text-sm mt-2">
          {subcategory
            ? `No ${subcategory} data is available for this alert.`
            : 'No EDR data is available for this alert.'}
        </p>
      </div>
    );
  }

  // Show "Coming Soon" message for summary data
  if (isSummary) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-gray-400">
        <ClockIcon className="w-12 h-12 mb-4" />
        <p className="text-lg font-medium">Summary View Coming Soon</p>
        <p className="text-sm mt-2">
          The summary view for {subcategory || 'EDR'} data is currently under development and will
          be available in the next update.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Search Bar */}
      <div className="relative">
        <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
          <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" />
        </div>
        <input
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="block w-full rounded-md border-0 bg-dark-700 py-2 pl-10 pr-3 text-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-primary sm:text-sm sm:leading-6"
          placeholder="Search fields and values..."
        />
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-gray-200 border-collapse">
          <thead className="bg-dark-700">
            <tr>
              {allKeys.map((key) => (
                <th
                  key={key}
                  className="px-4 py-3 font-medium text-gray-300 border-b border-dark-600 cursor-pointer hover:bg-dark-600"
                  onClick={() => handleSort(key)}
                >
                  <div className="flex items-center">
                    {formatKey(key)}
                    {sortConfig?.key === key &&
                      (sortConfig.direction === 'asc' ? (
                        <ChevronUpIcon className="w-4 h-4 ml-1" />
                      ) : (
                        <ChevronDownIcon className="w-4 h-4 ml-1" />
                      ))}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredAndSortedRecords.map((record, index) => (
              <tr key={index} className="border-b border-dark-600 hover:bg-dark-700/50">
                {allKeys.map((key) => (
                  <td key={key} className="px-4 py-3">
                    {renderValue(
                      typeof record === 'object' && record !== null
                        ? (record as RecordType)[key]
                        : undefined
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Empty State */}
      {filteredAndSortedRecords.length === 0 && (
        <div className="text-center py-8 text-gray-400">No records found matching your search</div>
      )}
    </div>
  );
};

export default EdrTableRenderer;
