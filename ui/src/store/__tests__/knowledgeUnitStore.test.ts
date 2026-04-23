import { describe, it, expect, beforeEach } from 'vitest';

import { useKnowledgeUnitStore } from '../knowledgeUnitStore';

describe('knowledgeUnitStore', () => {
  beforeEach(() => {
    // Reset store to initial state
    useKnowledgeUnitStore.setState({
      kuTypeFilter: '',
      searchTerm: '',
      pagination: { currentPage: 1, itemsPerPage: 10 },
      sortField: 'updated_at',
      sortDirection: 'desc',
      filters: {
        type: { directive: true, table: true, tool: true, document: true },
        status: { active: true, deprecated: true, experimental: true },
      },
    });
  });

  describe('kuTypeFilter', () => {
    it('defaults to empty string (all types)', () => {
      const state = useKnowledgeUnitStore.getState();
      expect(state.kuTypeFilter).toBe('');
    });

    it('sets kuTypeFilter value', () => {
      const { setKuTypeFilter } = useKnowledgeUnitStore.getState();
      setKuTypeFilter('tool');
      expect(useKnowledgeUnitStore.getState().kuTypeFilter).toBe('tool');
    });

    it('clears kuTypeFilter when set to empty string', () => {
      const { setKuTypeFilter } = useKnowledgeUnitStore.getState();
      setKuTypeFilter('table');
      expect(useKnowledgeUnitStore.getState().kuTypeFilter).toBe('table');

      setKuTypeFilter('');
      expect(useKnowledgeUnitStore.getState().kuTypeFilter).toBe('');
    });

    it('resets kuTypeFilter when resetFilters is called', () => {
      const { setKuTypeFilter, resetFilters } = useKnowledgeUnitStore.getState();
      setKuTypeFilter('document');
      expect(useKnowledgeUnitStore.getState().kuTypeFilter).toBe('document');

      resetFilters();
      expect(useKnowledgeUnitStore.getState().kuTypeFilter).toBe('');
    });
  });

  describe('getApiParams', () => {
    it('does not include ku_type when kuTypeFilter is empty', () => {
      const params = useKnowledgeUnitStore.getState().getApiParams();
      expect(params).not.toHaveProperty('ku_type');
    });

    it('includes ku_type=table when kuTypeFilter is "table"', () => {
      useKnowledgeUnitStore.getState().setKuTypeFilter('table');
      const params = useKnowledgeUnitStore.getState().getApiParams();
      expect(params.ku_type).toBe('table');
    });

    it('includes ku_type=document when kuTypeFilter is "document"', () => {
      useKnowledgeUnitStore.getState().setKuTypeFilter('document');
      const params = useKnowledgeUnitStore.getState().getApiParams();
      expect(params.ku_type).toBe('document');
    });

    it('includes ku_type=tool when kuTypeFilter is "tool"', () => {
      useKnowledgeUnitStore.getState().setKuTypeFilter('tool');
      const params = useKnowledgeUnitStore.getState().getApiParams();
      expect(params.ku_type).toBe('tool');
    });

    it('includes ku_type=index when kuTypeFilter is "index"', () => {
      useKnowledgeUnitStore.getState().setKuTypeFilter('index');
      const params = useKnowledgeUnitStore.getState().getApiParams();
      expect(params.ku_type).toBe('index');
    });

    it('includes search term as q parameter', () => {
      useKnowledgeUnitStore.getState().setSearchTerm('test');
      const params = useKnowledgeUnitStore.getState().getApiParams();
      expect(params.q).toBe('test');
    });

    it('includes pagination params', () => {
      const params = useKnowledgeUnitStore.getState().getApiParams();
      expect(params.limit).toBe(10);
      expect(params.offset).toBe(0);
    });

    it('combines ku_type and search params', () => {
      const store = useKnowledgeUnitStore.getState();
      store.setKuTypeFilter('tool');
      store.setSearchTerm('splunk');
      const params = useKnowledgeUnitStore.getState().getApiParams();
      expect(params.ku_type).toBe('tool');
      expect(params.q).toBe('splunk');
    });
  });
});
