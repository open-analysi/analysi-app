/* eslint-disable sonarjs/deprecation */
import React from 'react';

import { Listbox } from '@headlessui/react';
import { CheckIcon, ChevronUpDownIcon } from '@heroicons/react/24/outline';
import moment from 'moment-timezone';

import { useTimezoneStore } from '../../store/timezoneStore';
import { AlertAnalysis } from '../../types/alert';

interface AnalysisRunSelectorProps {
  analyses: AlertAnalysis[];
  selectedId: string;
  onSelect: (id: string) => void;
  disabled?: boolean;
}

const getStatusColor = (status: string): string => {
  switch (status.toLowerCase()) {
    case 'completed':
      return 'text-green-400';
    case 'failed':
      return 'text-red-400';
    case 'running':
    case 'analyzing':
      return 'text-blue-400';
    default:
      return 'text-gray-400';
  }
};

const getStatusLabel = (status: string): string => {
  switch (status.toLowerCase()) {
    case 'completed':
      return 'Completed';
    case 'failed':
      return 'Failed';
    case 'running':
    case 'analyzing':
      return 'Running';
    case 'pending':
      return 'Pending';
    default:
      return status;
  }
};

export const AnalysisRunSelector: React.FC<AnalysisRunSelectorProps> = ({
  analyses,
  selectedId,
  onSelect,
  disabled = false,
}) => {
  const { timezone } = useTimezoneStore();

  // Sort analyses by created_at descending (newest first)
  const sortedAnalyses = [...analyses].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  const selectedAnalysis = sortedAnalyses.find((a) => a.id === selectedId);

  const formatRelativeTime = (dateStr: string): string => {
    return moment(dateStr).tz(timezone).fromNow();
  };

  const formatTimestamp = (dateStr: string): string => {
    return moment(dateStr).tz(timezone).format('MMM D, YYYY h:mm A');
  };

  const getDisplayLabel = (analysis: AlertAnalysis, index: number): string => {
    const isLatest = index === 0;
    const prefix = isLatest ? 'Latest' : `Run ${sortedAnalyses.length - index}`;
    return `${prefix} - ${getStatusLabel(analysis.status)}`;
  };

  if (sortedAnalyses.length === 0) {
    return (
      <div className="text-sm text-gray-400 px-3 py-2 bg-gray-800 border border-gray-700 rounded-md">
        No analysis runs available
      </div>
    );
  }

  return (
    <Listbox value={selectedId} onChange={onSelect} disabled={disabled}>
      <div className="relative">
        <Listbox.Button className="relative w-full min-w-[280px] cursor-pointer rounded-md bg-gray-800 border border-gray-700 py-2 pl-3 pr-10 text-left text-sm text-gray-100 focus:outline-hidden focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed">
          {selectedAnalysis ? (
            <div className="flex items-center justify-between">
              <span className="block truncate">
                {getDisplayLabel(
                  selectedAnalysis,
                  sortedAnalyses.findIndex((a) => a.id === selectedAnalysis.id)
                )}
              </span>
              <span className={`ml-2 text-xs ${getStatusColor(selectedAnalysis.status)}`}>
                {formatRelativeTime(selectedAnalysis.created_at)}
              </span>
            </div>
          ) : (
            <span className="block truncate text-gray-400">Select an analysis run</span>
          )}
          <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
            <ChevronUpDownIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
          </span>
        </Listbox.Button>

        <Listbox.Options className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md bg-gray-800 border border-gray-700 py-1 text-sm shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-hidden">
          {sortedAnalyses.map((analysis, index) => (
            <Listbox.Option
              key={analysis.id}
              value={analysis.id}
              className={({ active }) =>
                `relative cursor-pointer select-none py-2 pl-10 pr-4 ${
                  active ? 'bg-gray-700 text-white' : 'text-gray-100'
                }`
              }
            >
              {({ selected }) => (
                <>
                  <div className="flex flex-col">
                    <div className="flex items-center justify-between">
                      <span
                        className={`block truncate ${selected ? 'font-medium' : 'font-normal'}`}
                      >
                        {getDisplayLabel(analysis, index)}
                      </span>
                      <span className={`text-xs ${getStatusColor(analysis.status)}`}>
                        {getStatusLabel(analysis.status)}
                      </span>
                    </div>
                    <span className="text-xs text-gray-400 mt-0.5">
                      {formatTimestamp(analysis.created_at)}
                    </span>
                  </div>
                  {selected && (
                    <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-blue-400">
                      <CheckIcon className="h-5 w-5" aria-hidden="true" />
                    </span>
                  )}
                </>
              )}
            </Listbox.Option>
          ))}
        </Listbox.Options>
      </div>
    </Listbox>
  );
};
