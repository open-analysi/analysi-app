import React, { useState, useEffect, useCallback, useMemo } from 'react';

import useErrorHandler from '../../hooks/useErrorHandler';
import { backendApi } from '../../services/backendApi';
import { useKnowledgeUnitStore, SortField } from '../../store/knowledgeUnitStore';
import { KnowledgeUnitQueryParams, KnowledgeUnit } from '../../types/knowledge';
import { ConfirmDialog } from '../common/ConfirmDialog';
import ErrorBoundary from '../common/ErrorBoundary';

import { CategoryFilter } from './CategoryFilter';
import { KnowledgeUnitEditModal } from './KnowledgeUnitEditModal';
import { KnowledgeUnitsTable } from './KnowledgeUnitsTable';
import { UnifiedSearch } from './UnifiedSearch';

export const KnowledgeUnits: React.FC = () => {
  // Use the store for state management
  const {
    knowledgeUnits: storeKnowledgeUnits,
    setKnowledgeUnits,
    removeKnowledgeUnit,
    totalCount,
    setTotalCount,
    searchTerm,
    setSearchTerm,
    sortField,
    sortDirection,
    setSorting,
    pagination,
    setPagination,
    kuTypeFilter,
    setKuTypeFilter,
    categoryFilter,
    toggleCategory,
    setCategoryFilter,
    getApiParams,
  } = useKnowledgeUnitStore();

  const [loading, setLoading] = useState(true);
  const [creatorFilter, setCreatorFilter] = useState<string>('');
  const [editingKnowledgeUnit, setEditingKnowledgeUnit] = useState<KnowledgeUnit | null>(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [deletingKnowledgeUnit, setDeletingKnowledgeUnit] = useState<KnowledgeUnit | null>(null);

  // Use proper error handling
  const { error, clearError, runSafe } = useErrorHandler('KnowledgeUnits');

  const fetchKnowledgeUnits = useCallback(async () => {
    setLoading(true);

    try {
      // Use store's getApiParams to get all filter, sort, and pagination params
      const params = getApiParams();

      // Check if we should return no results due to filter settings
      if (params.no_results) {
        setKnowledgeUnits([]);
        setTotalCount(0);
        return;
      }

      // Use runSafe to handle errors
      const [response] = await runSafe(
        backendApi.getKnowledgeUnits(params as KnowledgeUnitQueryParams),
        'fetchKnowledgeUnits',
        {
          action: 'fetching knowledge units',
          params,
        }
      );

      if (response) {
        // API now returns full response with pagination metadata
        setKnowledgeUnits(response.knowledge_units);
        setTotalCount(response.total);
      }
    } finally {
      setLoading(false);
    }
  }, [getApiParams, runSafe, setKnowledgeUnits, setTotalCount]);

  // Client-side sorting and owner filtering of knowledge units
  const sortedKnowledgeUnits = useMemo(() => {
    const filtered = creatorFilter
      ? storeKnowledgeUnits.filter((ku) => {
          const creator = ku.created_by || '';
          if (creatorFilter === 'system') return creator === 'system' || creator === '';
          if (creatorFilter === 'user') return creator !== 'system' && creator !== '';
          return true;
        })
      : storeKnowledgeUnits;

    if (filtered.length === 0) return filtered;

    return [...filtered].sort((a, b) => {
      let aValue: string | Date = '';
      let bValue: string | Date = '';

      switch (sortField) {
        case 'name': {
          aValue = a.name || '';
          bValue = b.name || '';
          break;
        }
        case 'description': {
          aValue = a.description || '';
          bValue = b.description || '';
          break;
        }
        case 'type': {
          aValue = a.type || '';
          bValue = b.type || '';
          break;
        }
        case 'owner': {
          aValue = a.created_by || '';
          bValue = b.created_by || '';
          break;
        }
        case 'status': {
          aValue = a.status || '';
          bValue = b.status || '';
          break;
        }
        case 'version': {
          aValue = a.version || '';
          bValue = b.version || '';
          break;
        }
        case 'created_at': {
          aValue = new Date(a.created_at || 0);
          bValue = new Date(b.created_at || 0);
          break;
        }
        case 'updated_at': {
          aValue = new Date(a.updated_at || 0);
          bValue = new Date(b.updated_at || 0);
          break;
        }
        default: {
          return 0;
        }
      }

      // Handle string comparison
      if (typeof aValue === 'string' && typeof bValue === 'string') {
        const comparison = aValue.toLowerCase().localeCompare(bValue.toLowerCase());
        return sortDirection === 'asc' ? comparison : -comparison;
      }

      // Handle date comparison
      if (aValue instanceof Date && bValue instanceof Date) {
        const comparison = aValue.getTime() - bValue.getTime();
        return sortDirection === 'asc' ? comparison : -comparison;
      }

      return 0;
    });
  }, [storeKnowledgeUnits, creatorFilter, sortField, sortDirection]);

  // Fetch knowledge units when pagination or search parameters change (but not sort - that's client-side now)
  useEffect(() => {
    void fetchKnowledgeUnits();
  }, [
    pagination.currentPage,
    pagination.itemsPerPage,
    searchTerm,
    kuTypeFilter,
    categoryFilter,
    fetchKnowledgeUnits,
  ]);

  const handleSort = (field: string) => {
    setSorting(field as SortField);
  };

  const handlePageChange = (newPage: number) => {
    setPagination({ currentPage: newPage });
  };

  const handleItemsPerPageChange = (newItemsPerPage: number) => {
    setPagination({ itemsPerPage: newItemsPerPage, currentPage: 1 });
  };

  // More efficient search handler that prevents double API calls
  const handleSearch = useCallback(
    (query: string) => {
      // Directly update the search term without additional checks
      // The store will handle deduplication if needed
      setSearchTerm(query);
    },
    [setSearchTerm]
  );

  const handleRowClick = useCallback((_id: string) => {
    // In the future, this would navigate to a detail view
  }, []);

  const handleEdit = useCallback(
    async (knowledgeUnit: KnowledgeUnit) => {
      // Fetch full knowledge unit details including content
      setLoading(true);

      try {
        let fullKnowledgeUnit;

        // Fetch based on type
        switch (knowledgeUnit.type) {
          case 'directive': {
            const [response] = await runSafe(
              backendApi.getDirective(knowledgeUnit.id),
              'fetchDirective',
              { action: 'fetching directive details', entityId: knowledgeUnit.id }
            );
            fullKnowledgeUnit = response;
            break;
          }
          case 'document': {
            const [response] = await runSafe(
              backendApi.getDocument(knowledgeUnit.id),
              'fetchDocument',
              { action: 'fetching document details', entityId: knowledgeUnit.id }
            );
            fullKnowledgeUnit = response;
            break;
          }
          case 'table': {
            const [response] = await runSafe(backendApi.getTable(knowledgeUnit.id), 'fetchTable', {
              action: 'fetching table details',
              entityId: knowledgeUnit.id,
            });
            fullKnowledgeUnit = response;
            break;
          }
          case 'tool': {
            // Tool detail endpoint not available on backend; use list data directly
            fullKnowledgeUnit = knowledgeUnit;
            break;
          }
          default: {
            fullKnowledgeUnit = knowledgeUnit;
          }
        }

        if (fullKnowledgeUnit) {
          setEditingKnowledgeUnit(fullKnowledgeUnit as KnowledgeUnit);
          setIsEditModalOpen(true);
        }
      } finally {
        setLoading(false);
      }
    },
    [runSafe]
  );

  const handleEditModalClose = useCallback(() => {
    setEditingKnowledgeUnit(null);
    setIsEditModalOpen(false);
  }, []);

  const handleEditSave = useCallback(() => {
    // Refresh the list after successful edit
    void fetchKnowledgeUnits();
  }, [fetchKnowledgeUnits]);

  const handleDelete = useCallback((knowledgeUnit: KnowledgeUnit) => {
    setDeletingKnowledgeUnit(knowledgeUnit);
  }, []);

  const handleConfirmDelete = useCallback(async () => {
    if (!deletingKnowledgeUnit) return;

    const ku = deletingKnowledgeUnit;
    setDeletingKnowledgeUnit(null);

    let apiCall;
    switch (ku.type) {
      case 'directive':
        apiCall = backendApi.deleteDirective(ku.id);
        break;
      case 'document':
        apiCall = backendApi.deleteDocument(ku.id);
        break;
      case 'table':
        apiCall = backendApi.deleteTable(ku.id);
        break;
      default:
        return;
    }

    const [, deleteError] = await runSafe(apiCall, 'deleteKnowledgeUnit', {
      action: `deleting ${ku.type}`,
      entityId: ku.id,
    });

    if (!deleteError) {
      removeKnowledgeUnit(ku.id);
    }
  }, [deletingKnowledgeUnit, runSafe, removeKnowledgeUnit]);

  // Derive available categories from loaded data for filter chips
  const availableCategories = useMemo(() => {
    const cats = new Set(storeKnowledgeUnits.flatMap((ku) => ku.tags || []));
    // Also include any currently-active filter values (they may not be in the current page)
    for (const c of categoryFilter) cats.add(c);
    return Array.from(cats).sort((a, b) => a.localeCompare(b));
  }, [storeKnowledgeUnits, categoryFilter]);

  return (
    <ErrorBoundary component="KnowledgeUnits">
      <div data-testid="knowledge-units-component">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold text-white">Knowledge Units</h1>
              {totalCount > 0 && (
                <span className="px-2.5 py-0.5 rounded-full text-sm font-medium bg-dark-700 text-gray-100">
                  {totalCount} {totalCount === 1 ? 'unit' : 'units'}
                </span>
              )}
            </div>
            <p className="mt-1 text-sm text-gray-400">
              View and manage directives, tables, tools, and documents
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="ku-items-per-page" className="text-sm text-gray-400">
              Show:
            </label>
            <select
              id="ku-items-per-page"
              value={pagination.itemsPerPage}
              onChange={(e) => handleItemsPerPageChange(Number(e.target.value))}
              className="bg-dark-700 border border-gray-600 text-gray-100 text-sm rounded-md px-2 py-1 focus:ring-primary focus:border-primary"
            >
              <option value="10">10</option>
              <option value="25">25</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
            <span className="text-sm text-gray-400">per page</span>
          </div>
        </div>

        {error.hasError && (
          <div className="mb-6 bg-red-900/30 border border-red-700 p-4 rounded-md">
            <div className="flex items-center">
              <div className="flex-1">
                <p className="text-gray-100">{error.message}</p>
              </div>
              <button onClick={clearError} className="text-gray-400 hover:text-gray-100 text-sm">
                Dismiss
              </button>
            </div>
          </div>
        )}

        <div className="mb-6 flex items-center gap-3">
          <div className="flex-1 relative">
            <UnifiedSearch
              onSearch={handleSearch}
              value={searchTerm}
              placeholder="Search knowledge units by name, type, or description..."
            />
            {loading && (
              <div className="absolute right-10 top-1/2 transform -translate-y-1/2 opacity-70">
                <div className="animate-spin h-4 w-4 border-2 border-primary border-t-transparent rounded-full" />
              </div>
            )}
          </div>
          <select
            value={kuTypeFilter}
            onChange={(e) => setKuTypeFilter(e.target.value)}
            className="h-10 rounded-lg border border-gray-600 bg-gray-700 px-3 text-sm text-gray-200 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary"
          >
            <option value="">All Types</option>
            <option value="table">Table</option>
            <option value="document">Document</option>
            <option value="tool">Tool</option>
            <option value="index">Index</option>
          </select>
          <select
            value={creatorFilter}
            onChange={(e) => setCreatorFilter(e.target.value)}
            className="h-10 rounded-lg border border-gray-600 bg-gray-700 px-3 text-sm text-gray-200 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary"
          >
            <option value="">All Creators</option>
            <option value="system">System</option>
            <option value="user">User-Created</option>
          </select>
        </div>

        {/* Category filter: dropdown picker + active chips */}
        {availableCategories.length > 0 && (
          <div className="mb-4">
            <CategoryFilter
              available={availableCategories}
              selected={categoryFilter}
              onToggle={toggleCategory}
              onClear={() => setCategoryFilter([])}
            />
          </div>
        )}

        <div className={`relative ${loading ? 'opacity-75 transition-opacity duration-200' : ''}`}>
          <KnowledgeUnitsTable
            knowledgeUnits={sortedKnowledgeUnits}
            loading={loading}
            totalCount={totalCount}
            currentPage={pagination.currentPage}
            itemsPerPage={pagination.itemsPerPage}
            sortField={sortField}
            sortDirection={sortDirection}
            onPageChange={handlePageChange}
            onSort={handleSort}
            onRowClick={handleRowClick}
            onEdit={(ku) => {
              handleEdit(ku).catch(() => {
                /* handled in handleEdit */
              });
            }}
            onDelete={handleDelete}
          />
        </div>

        <KnowledgeUnitEditModal
          isOpen={isEditModalOpen}
          onClose={handleEditModalClose}
          knowledgeUnit={editingKnowledgeUnit}
          onSave={handleEditSave}
        />

        <ConfirmDialog
          isOpen={!!deletingKnowledgeUnit}
          onClose={() => setDeletingKnowledgeUnit(null)}
          onConfirm={() => void handleConfirmDelete()}
          title="Delete Knowledge Unit?"
          message={`Are you sure you want to delete "${deletingKnowledgeUnit?.name}"? This action cannot be undone.`}
          confirmLabel="Delete"
          cancelLabel="Cancel"
          variant="warning"
        />
      </div>
    </ErrorBoundary>
  );
};
