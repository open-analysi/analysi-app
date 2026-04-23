import React, { useState, useEffect, useRef } from 'react';

import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { FunnelIcon } from '@heroicons/react/24/solid';

/** Dropdown category picker — shows selected chips inline, full list in a searchable popover. */
export const CategoryFilter: React.FC<{
  available: string[];
  selected: string[];
  onToggle: (cat: string) => void;
  onClear: () => void;
}> = ({ available, selected, onToggle, onClear }) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (open) searchRef.current?.focus();
  }, [open]);

  const filtered = search
    ? available.filter((cat) => cat.toLowerCase().includes(search.toLowerCase()))
    : available;

  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Category filters">
      {/* Dropdown trigger */}
      <div className="relative" ref={ref}>
        <button
          onClick={() => {
            setOpen(!open);
            setSearch('');
          }}
          aria-expanded={open}
          aria-haspopup="listbox"
          className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border text-xs font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${
            selected.length > 0
              ? 'border-primary/40 bg-primary/10 text-primary'
              : 'border-gray-600 bg-dark-700 text-gray-400 hover:bg-dark-600 hover:text-gray-200'
          }`}
        >
          <FunnelIcon className="h-3.5 w-3.5" />
          Categories
          {selected.length > 0 && (
            <span className="ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-primary/30 text-primary">
              {selected.length}
            </span>
          )}
        </button>

        {/* Dropdown menu */}
        {open && (
          <div className="absolute left-0 top-full mt-1 z-50 w-56 rounded-lg border border-gray-600 bg-dark-800 shadow-xl">
            {/* Search input */}
            <div className="p-2 border-b border-gray-700">
              <input
                ref={searchRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search categories..."
                className="w-full px-2 py-1 text-xs rounded bg-dark-700 border border-gray-600 text-gray-200 placeholder-gray-500 focus:outline-none focus:border-primary"
              />
            </div>
            {/* Options list */}
            <div className="max-h-52 overflow-y-auto py-1">
              {filtered.length === 0 ? (
                <p className="px-3 py-2 text-xs text-gray-500">No categories match</p>
              ) : (
                filtered.map((cat) => {
                  const active = selected.includes(cat);
                  return (
                    <button
                      key={cat}
                      onClick={() => onToggle(cat)}
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
                      <span className={active ? 'text-gray-100' : 'text-gray-400'}>{cat}</span>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        )}
      </div>

      {/* Active filter chips — only selected ones shown inline */}
      {selected.map((cat) => (
        <button
          key={cat}
          onClick={() => onToggle(cat)}
          aria-label={`Remove ${cat} filter`}
          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-primary/20 text-primary border border-primary/40 hover:bg-primary/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary transition-colors"
        >
          {cat}
          <XMarkIcon className="h-3 w-3" />
        </button>
      ))}

      {/* Clear all */}
      {selected.length > 1 && (
        <button
          onClick={onClear}
          aria-label="Clear all category filters"
          className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          Clear all
        </button>
      )}
    </div>
  );
};
