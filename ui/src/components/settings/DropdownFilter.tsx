import React, { useState, useEffect, useRef } from 'react';

import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { FunnelIcon } from '@heroicons/react/24/solid';

/** Format a snake_case key into a human-readable label */
const formatLabel = (key: string): string =>
  key
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');

/** Dropdown filter — same design as CategoryFilter. Shows a dropdown with checkboxes and inline chips. */
export const DropdownFilter: React.FC<{
  label: string;
  options: string[];
  selected: string[];
  onToggle: (key: string) => void;
  onClear: () => void;
  onSelectAll: () => void;
}> = ({ label, options, selected, onToggle, onClear, onSelectAll }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const allSelected = selected.length === options.length;
  const noneSelected = selected.length === 0;
  const deselectedCount = options.length - selected.length;

  const getButtonStyle = () => {
    if (noneSelected) return 'border-red-500/40 bg-red-500/10 text-red-400';
    if (!allSelected) return 'border-primary/40 bg-primary/10 text-primary';
    return 'border-gray-600 bg-dark-700 text-gray-400 hover:bg-dark-600 hover:text-gray-200';
  };

  return (
    <div
      className="flex flex-wrap items-center gap-1.5"
      role="group"
      aria-label={`${label} filters`}
    >
      {/* Dropdown trigger */}
      <div className="relative" ref={ref}>
        <button
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-haspopup="listbox"
          className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${getButtonStyle()}`}
        >
          <FunnelIcon className="h-3.5 w-3.5" />
          {label}
          {deselectedCount > 0 && (
            <span className="ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-primary/30 text-primary">
              {deselectedCount}
            </span>
          )}
        </button>

        {/* Dropdown menu */}
        {open && (
          <div className="absolute left-0 top-full mt-1 z-50 w-48 rounded-lg border border-gray-600 bg-dark-800 shadow-xl">
            {/* Select all / Clear all header */}
            <div className="flex items-center justify-between px-3 py-1.5 border-b border-gray-700">
              <button
                onClick={allSelected ? onClear : onSelectAll}
                className="text-[10px] font-medium text-gray-400 hover:text-primary transition-colors"
              >
                {allSelected ? 'Clear all' : 'Select all'}
              </button>
            </div>
            {/* Options list */}
            <div className="max-h-52 overflow-y-auto py-1">
              {options.map((key) => {
                const active = selected.includes(key);
                return (
                  <button
                    key={key}
                    onClick={() => onToggle(key)}
                    role="option"
                    aria-selected={active}
                    className="flex items-center gap-2 w-full px-3 py-1.5 text-xs text-left hover:bg-dark-600 transition-colors"
                  >
                    <span
                      className={`flex items-center justify-center h-4 w-4 rounded border transition-colors shrink-0 ${
                        active
                          ? 'bg-primary border-primary text-white'
                          : 'border-gray-500 bg-transparent'
                      }`}
                    >
                      {active && <CheckIcon className="h-3 w-3" />}
                    </span>
                    <span className={active ? 'text-gray-100' : 'text-gray-400'}>
                      {formatLabel(key)}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Active filter chips — only show when NOT all are selected (i.e., some are excluded) */}
      {!allSelected &&
        selected.map((key) => (
          <button
            key={key}
            onClick={() => onToggle(key)}
            aria-label={`Remove ${formatLabel(key)} filter`}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-primary/20 text-primary border border-primary/40 hover:bg-primary/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary transition-colors"
          >
            {formatLabel(key)}
            <XMarkIcon className="h-3 w-3" />
          </button>
        ))}
    </div>
  );
};
