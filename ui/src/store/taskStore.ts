import { create } from 'zustand';

import { Task } from '../types/knowledge';

export type TaskSortField =
  | 'name'
  | 'description'
  | 'function'
  | 'scope'
  | 'owner'
  | 'status'
  | 'version'
  | 'created_at'
  | 'updated_at';
export type SortDirection = 'asc' | 'desc';

export interface FunctionFilters {
  summarization: boolean;
  data_conversion: boolean;
  extraction: boolean;
  decision_making: boolean;
  planning: boolean;
  visualization: boolean;
  search: boolean;
}

export interface ScopeFilters {
  input: boolean;
  processing: boolean;
  output: boolean;
}

export interface StatusFilters {
  active: boolean;
  deprecated: boolean;
  experimental: boolean;
}

export interface Pagination {
  currentPage: number;
  itemsPerPage: number;
}

export interface TaskStore {
  // Data
  tasks: Task[];
  setTasks: (tasks: Task[]) => void;
  totalCount: number;
  setTotalCount: (count: number) => void;

  // Filters
  filters: {
    function: FunctionFilters;
    scope: ScopeFilters;
    status: StatusFilters;
  };
  setFunctionFilters: (filters: Partial<FunctionFilters>) => void;
  setScopeFilters: (filters: Partial<ScopeFilters>) => void;
  setStatusFilters: (filters: Partial<StatusFilters>) => void;
  resetFilters: () => void;

  // Category filter
  categoryFilter: string[];
  setCategoryFilter: (categories: string[]) => void;
  toggleCategory: (category: string) => void;

  // Search
  searchTerm: string;
  setSearchTerm: (term: string) => void;

  // Sorting
  sortField: TaskSortField;
  sortDirection: SortDirection;
  setSorting: (field: TaskSortField, direction?: SortDirection) => void;

  // Pagination
  pagination: Pagination;
  setPagination: (pagination: Partial<Pagination>) => void;

  // API parameters
  getApiParams: () => Record<string, string | number | boolean | string[]>;
}

export const useTaskStore = create<TaskStore>((set, get) => ({
  // Data
  tasks: [],
  setTasks: (tasks) => set({ tasks }),
  totalCount: 0,
  setTotalCount: (count) => set({ totalCount: count }),

  // Filters
  filters: {
    function: {
      summarization: true,
      data_conversion: true,
      extraction: true,
      decision_making: true,
      planning: true,
      visualization: true,
      search: true,
    },
    scope: {
      input: true,
      processing: true,
      output: true,
    },
    status: {
      active: true,
      deprecated: true,
      experimental: true,
    },
  },
  setFunctionFilters: (filters) =>
    set((state) => ({
      filters: {
        ...state.filters,
        function: { ...state.filters.function, ...filters },
      },
    })),
  setScopeFilters: (filters) =>
    set((state) => ({
      filters: {
        ...state.filters,
        scope: { ...state.filters.scope, ...filters },
      },
    })),
  setStatusFilters: (filters) =>
    set((state) => ({
      filters: {
        ...state.filters,
        status: { ...state.filters.status, ...filters },
      },
    })),
  resetFilters: () =>
    set({
      filters: {
        function: {
          summarization: true,
          data_conversion: true,
          extraction: true,
          decision_making: true,
          planning: true,
          visualization: true,
          search: true,
        },
        scope: {
          input: true,
          processing: true,
          output: true,
        },
        status: {
          active: true,
          deprecated: true,
          experimental: true,
        },
      },
      categoryFilter: [],
      searchTerm: '',
    }),

  // Category filter
  categoryFilter: [],
  setCategoryFilter: (categories) => set({ categoryFilter: categories }),
  toggleCategory: (category) =>
    set((state) => {
      const current = state.categoryFilter;
      const next = current.includes(category)
        ? current.filter((c) => c !== category)
        : [...current, category];
      return { categoryFilter: next };
    }),

  // Search
  searchTerm: '',
  setSearchTerm: (term) => {
    // Only update state if the term has actually changed
    set((state) => {
      if (state.searchTerm === term) return state;
      return { searchTerm: term };
    });
  },

  // Sorting
  sortField: 'created_at' as TaskSortField,
  sortDirection: 'desc' as SortDirection,
  setSorting: (field, direction) => {
    const state = get();
    if (field === state.sortField && !direction) {
      // Toggle direction if clicking same field again
      set({ sortDirection: state.sortDirection === 'asc' ? 'desc' : 'asc' });
    } else {
      // Set new field and direction, default to ascending or provided direction
      set({
        sortField: field,
        sortDirection: direction || 'asc',
      });
    }
  },

  // Pagination
  pagination: {
    currentPage: 1,
    itemsPerPage: 20,
  },
  setPagination: (pagination) =>
    set((state) => ({
      pagination: {
        ...state.pagination,
        ...pagination,
      },
    })),

  // API parameters for fetching data
  getApiParams: () => {
    const state = get();
    const params: Record<string, string | number | boolean | string[]> = {};

    // Add search (backend uses 'q' parameter)
    if (state.searchTerm) {
      params.q = state.searchTerm;
    }

    // Add pagination
    params.limit = state.pagination.itemsPerPage;
    params.offset = (state.pagination.currentPage - 1) * state.pagination.itemsPerPage;

    // Add sorting
    params.sort = state.sortField;
    params.order = state.sortDirection;

    // Function, scope, and status filters are applied client-side
    // (backend does not support multi-value filtering for these fields)

    // Category filter (AND semantics — backend uses repeated query params)
    if (state.categoryFilter.length > 0) {
      params.categories = state.categoryFilter;
    }

    return params;
  },
}));
