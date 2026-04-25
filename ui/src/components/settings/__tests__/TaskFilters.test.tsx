import React from 'react';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

import type { FunctionFilters, ScopeFilters, StatusFilters } from '../../../store/taskStore';
import { TaskFilters } from '../TaskFilters';

// Default filter values (all selected)
const defaultFunctionFilters: FunctionFilters = {
  summarization: true,
  data_conversion: true,
  extraction: true,
  decision_making: true,
  planning: true,
  visualization: true,
  search: true,
};

const defaultScopeFilters: ScopeFilters = {
  input: true,
  processing: true,
  output: true,
};

const defaultStatusFilters: StatusFilters = {
  active: true,
  deprecated: true,
  experimental: true,
};

// Constants for repeated text
const FUNCTION_LABEL = 'Function';
const SCOPE_LABEL = 'Scope';
const STATUS_LABEL = 'Status';
const CLEAR_ALL_TEXT = 'Clear All';
const SELECT_ALL_TEXT = 'Select All';

const makeProps = (
  overrides: Partial<React.ComponentProps<typeof TaskFilters>> = {}
): React.ComponentProps<typeof TaskFilters> => ({
  functionFilters: defaultFunctionFilters,
  scopeFilters: defaultScopeFilters,
  statusFilters: defaultStatusFilters,
  setFunctionFilters: vi.fn<(filters: Partial<FunctionFilters>) => void>(),
  setScopeFilters: vi.fn<(filters: Partial<ScopeFilters>) => void>(),
  setStatusFilters: vi.fn<(filters: Partial<StatusFilters>) => void>(),
  resetFilters: vi.fn<() => void>(),
  ...overrides,
});

describe('TaskFilters', () => {
  it('renders all filter categories (Function, Scope, Status)', () => {
    render(<TaskFilters {...makeProps()} />);

    expect(screen.getByText(FUNCTION_LABEL)).toBeInTheDocument();
    expect(screen.getByText(SCOPE_LABEL)).toBeInTheDocument();
    expect(screen.getByText(STATUS_LABEL)).toBeInTheDocument();

    // Check specific filter buttons exist
    expect(screen.getByText('Summarization')).toBeInTheDocument();
    expect(screen.getByText('Input')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('shows "Clear All" when all filters in a category are selected', () => {
    render(<TaskFilters {...makeProps()} />);

    // When all function filters are selected, the button should say "Clear All"
    const clearAllButtons = screen.getAllByText(CLEAR_ALL_TEXT);
    expect(clearAllButtons).toHaveLength(3); // One per category
  });

  it('shows "Select All" when not all filters in a category are selected', () => {
    const partialFunctionFilters: FunctionFilters = {
      ...defaultFunctionFilters,
      summarization: false,
    };

    render(<TaskFilters {...makeProps({ functionFilters: partialFunctionFilters })} />);

    // Function category should show "Select All" since not all are selected
    expect(screen.getByText(SELECT_ALL_TEXT)).toBeInTheDocument();
  });

  it('clicking a filter button calls the correct setter', () => {
    const setFunctionFilters = vi.fn();
    render(<TaskFilters {...makeProps({ setFunctionFilters })} />);

    fireEvent.click(screen.getByText('Summarization'));

    expect(setFunctionFilters).toHaveBeenCalledWith({ summarization: false });
  });

  it('clicking "Clear All" toggles all filters in that category off', () => {
    const setFunctionFilters = vi.fn();
    render(<TaskFilters {...makeProps({ setFunctionFilters })} />);

    // All functions are selected, so button says "Clear All"
    // We need the one in the Function section. The Function section header is first.
    const clearAllButtons = screen.getAllByText(CLEAR_ALL_TEXT);
    fireEvent.click(clearAllButtons[0]); // First "Clear All" is for Function category

    expect(setFunctionFilters).toHaveBeenCalledWith({
      summarization: false,
      data_conversion: false,
      extraction: false,
      decision_making: false,
      planning: false,
      visualization: false,
      search: false,
    });
  });

  it('"Reset All Filters" custom window event calls resetFilters', () => {
    const resetFilters = vi.fn();
    render(<TaskFilters {...makeProps({ resetFilters })} />);

    // Dispatch the custom event that the component listens for
    window.dispatchEvent(new Event('resetFilters'));

    expect(resetFilters).toHaveBeenCalledTimes(1);
  });
});
