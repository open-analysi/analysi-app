import { create } from 'zustand';

import { KnowledgeUnit } from '../types/knowledge';

export type SortField =
  | 'name'
  | 'type'
  | 'owner'
  | 'created_at'
  | 'updated_at'
  | 'status'
  | 'version'
  | 'description';
export type SortDirection = 'asc' | 'desc';

export interface TypeFilters {
  directive: boolean;
  table: boolean;
  tool: boolean;
  document: boolean;
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

export interface KnowledgeUnitStore {
  // Data
  knowledgeUnits: KnowledgeUnit[];
  setKnowledgeUnits: (knowledgeUnits: KnowledgeUnit[]) => void;
  updateKnowledgeUnit: (id: string, updatedUnit: KnowledgeUnit) => void;
  removeKnowledgeUnit: (id: string) => void;
  totalCount: number;
  setTotalCount: (count: number) => void;

  // Filters
  filters: {
    type: TypeFilters;
    status: StatusFilters;
  };
  setTypeFilters: (filters: Partial<TypeFilters>) => void;
  setStatusFilters: (filters: Partial<StatusFilters>) => void;
  resetFilters: () => void;

  // KU type filter (backend ku_type value: 'table' | 'document' | 'tool' | 'index' | '')
  kuTypeFilter: string;
  setKuTypeFilter: (kuType: string) => void;

  // Category filter
  categoryFilter: string[];
  setCategoryFilter: (categories: string[]) => void;
  toggleCategory: (category: string) => void;

  // Search
  searchTerm: string;
  setSearchTerm: (term: string) => void;

  // Sorting
  sortField: SortField;
  sortDirection: SortDirection;
  setSorting: (field: SortField, direction?: SortDirection) => void;

  // Pagination
  pagination: Pagination;
  setPagination: (pagination: Partial<Pagination>) => void;

  // API parameters
  getApiParams: () => Record<string, string | number | string[]>;
}

export const useKnowledgeUnitStore = create<KnowledgeUnitStore>((set, get) => ({
  // Data
  knowledgeUnits: [],
  setKnowledgeUnits: (knowledgeUnits) => set({ knowledgeUnits }),
  updateKnowledgeUnit: (id, updatedUnit) =>
    set((state) => ({
      knowledgeUnits: state.knowledgeUnits.map((unit) => (unit.id === id ? updatedUnit : unit)),
    })),
  removeKnowledgeUnit: (id) =>
    set((state) => ({
      knowledgeUnits: state.knowledgeUnits.filter((unit) => unit.id !== id),
      totalCount: state.totalCount - 1,
    })),
  totalCount: 0,
  setTotalCount: (count) => set({ totalCount: count }),

  // Filters
  filters: {
    type: {
      directive: true,
      table: true,
      tool: true,
      document: true,
    },
    status: {
      active: true,
      deprecated: true,
      experimental: true,
    },
  },
  setTypeFilters: (filters) =>
    set((state) => ({
      filters: {
        ...state.filters,
        type: { ...state.filters.type, ...filters },
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
        type: {
          directive: true,
          table: true,
          tool: true,
          document: true,
        },
        status: {
          active: true,
          deprecated: true,
          experimental: true,
        },
      },
      kuTypeFilter: '',
      categoryFilter: [],
      searchTerm: '',
    }),

  // KU type filter
  kuTypeFilter: '',
  setKuTypeFilter: (kuType) => set({ kuTypeFilter: kuType }),

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
  sortField: 'updated_at' as SortField,
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
    itemsPerPage: 25,
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
    const params: Record<string, string | number | string[]> = {};

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

    // Map status filters to backend values (enabled/disabled)
    const enabledStatuses = [];
    if (state.filters.status.active) enabledStatuses.push('enabled');
    if (state.filters.status.deprecated) enabledStatuses.push('enabled'); // Map deprecated to enabled
    if (state.filters.status.experimental) enabledStatuses.push('enabled'); // Map experimental to enabled

    if (enabledStatuses.length > 0 && enabledStatuses.length < 3) {
      params.status = 'enabled'; // Backend uses enabled/disabled values
    }

    // KU type filter (direct backend ku_type value)
    if (state.kuTypeFilter) {
      params.ku_type = state.kuTypeFilter;
    }

    // Category filter (AND semantics — backend uses repeated query params)
    if (state.categoryFilter.length > 0) {
      params.categories = state.categoryFilter;
    }

    return params;
  },
}));
