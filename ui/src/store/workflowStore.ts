import { create } from 'zustand';

import { Workflow } from '../types/workflow';

export type WorkflowSortField =
  | 'name'
  | 'description'
  | 'nodes'
  | 'edges'
  | 'created_by'
  | 'created_at';
export type SortDirection = 'asc' | 'desc';

export interface Pagination {
  currentPage: number;
  itemsPerPage: number;
}

export interface WorkflowStore {
  // Data
  workflows: Workflow[];
  setWorkflows: (workflows: Workflow[]) => void;
  totalCount: number;
  setTotalCount: (count: number) => void;

  // Search
  searchTerm: string;
  setSearchTerm: (term: string) => void;

  // Sorting
  sortField: WorkflowSortField;
  sortDirection: SortDirection;
  setSorting: (field: WorkflowSortField, direction: SortDirection) => void;

  // Pagination
  pagination: Pagination;
  setPagination: (pagination: Partial<Pagination>) => void;

  // API params builder - uses limit/offset like the backend expects
  getApiParams: () => {
    search?: string;
    sort?: string;
    order?: string;
    limit?: number;
    offset?: number;
  };
}

export const useWorkflowStore = create<WorkflowStore>((set, get) => ({
  // Data
  workflows: [],
  setWorkflows: (workflows) => set({ workflows }),
  totalCount: 0,
  setTotalCount: (totalCount) => set({ totalCount }),

  // Search
  searchTerm: '',
  setSearchTerm: (searchTerm) => set({ searchTerm }),

  // Sorting - default to created_at desc for workflows list
  sortField: 'created_at',
  sortDirection: 'desc',
  setSorting: (sortField, sortDirection) => set({ sortField, sortDirection }),

  // Pagination
  pagination: { currentPage: 1, itemsPerPage: 20 },
  setPagination: (newPagination) =>
    set((state) => ({
      pagination: { ...state.pagination, ...newPagination },
    })),

  // API params builder - uses limit/offset like the backend expects
  getApiParams: () => {
    const { searchTerm, sortField, sortDirection, pagination } = get();

    const params: {
      search?: string;
      sort?: string;
      order?: string;
      limit?: number;
      offset?: number;
    } = {};

    if (searchTerm.trim()) {
      params.search = searchTerm.trim();
    }

    params.sort = sortField;
    params.order = sortDirection;
    params.limit = pagination.itemsPerPage;
    params.offset = (pagination.currentPage - 1) * pagination.itemsPerPage;

    return params;
  },
}));
